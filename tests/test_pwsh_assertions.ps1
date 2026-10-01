# JEV PowerShell 断言反向覆盖 + 边界 + 跨实现一致性
#
# 缺口(附录 B2):`JevAssertions.psm1` 有 3 个独立重写实现用 `throw` 报错,
# 而初版 `test_pwsh_assertions.ps1` 只有 3 行正向 —— 「3/3 通过」只证明脚本跑得起来,
# 不证明任何一个 `throw` 会被触发,也不证明算得对。
#
# 判据(预注册,R9):
#   C0 **BOM 自检**:本文件与被测 psm1 都必须带 UTF-8 BOM。
#      无 BOM 时 PS5.1 按 ANSI(GBK)读中文 -> 字符串乱码 -> 报错消息变成
#      `澶辫触` 这类垃圾,报错信息本身不可信。
#      ⚠ 本条是被实测逼出来的(2026-10-01 Round 30):用 `edit` 工具改 psm1 时
#      **BOM 被剥掉**,PS5.1 下 5 项测试因乱码而红,而 PS7 完全正常 ——
#      即「只测 PS7」会漏掉这一整类事故。
#   C1 每个断言都必须有**反向用例**:错误值必须 throw,且消息里带上**是哪一条**判断失败。
#   C2 `Assert-JevTieredMargin` 的三档边界(50k / 250k)两侧都要覆盖 ——
#      只测一档时,一个「永远按第 3 档算」的 mutant 能通过全部用例。
#   C3 **跨实现一致性**:同一组输入,PS 与 Python 必须给出相同结果。
#      persona 把两套面**并列推荐**,不同结果意味着用户按 PS 算、按 Python 校验必错。
#      这是 (甲) 类「承诺 vs 实际」的典型形态。
#
# 期望值来源:Python `jev_assertions` 的 Decimal 实现。档位语义见 benchmarks 的 solve.py
#   deduction 逐档累进 lower*(r - prev_mmr),满档时恰为 N*0.02 - mm。
$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$psm1 = Join-Path $repoRoot 'packages/assertions/pwsh/JevAssertions.psm1'

$script:failures = 0
$script:total = 0

Write-Output "== C0 BOM 自检(无 BOM 时 PS5.1 按 ANSI 读中文,报错信息会变乱码) =="
foreach ($f in @($PSCommandPath, $psm1)) {
    $script:total++
    $bytes = [System.IO.File]::ReadAllBytes($f)[0..2]
    if ($bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191) {
        Write-Output ("  PASS  BOM 存在: {0}" -f (Split-Path $f -Leaf))
    } else {
        $script:failures++
        Write-Output ("  FAIL  BOM 缺失: {0} (首字节 {1},{2},{3})" -f `
            (Split-Path $f -Leaf), $bytes[0], $bytes[1], $bytes[2])
    }
}

Import-Module $psm1 -Force

function Check {
    param([string]$Name, [scriptblock]$Body)
    $script:total++
    try {
        & $Body
        Write-Output ("  PASS  {0}" -f $Name)
    } catch {
        $script:failures++
        Write-Output ("  FAIL  {0}  <- {1}" -f $Name, $_.Exception.Message)
    }
}

function ExpectThrow {
    param([string]$Name, [scriptblock]$Body, [string]$MustContain)
    $script:total++
    try {
        & $Body | Out-Null
        $script:failures++
        Write-Output ("  FAIL  {0}  <- 期望 throw 但没抛(该 throw 永远不会被触发)" -f $Name)
    } catch {
        $msg = $_.Exception.Message
        if ($MustContain -and ($msg -notlike "*$MustContain*")) {
            $script:failures++
            Write-Output ("  FAIL  {0}  <- 抛了,但消息里没有 '{1}': {2}" -f $Name, $MustContain, $msg)
        } else {
            Write-Output ("  PASS  {0}" -f $Name)
        }
    }
}

Write-Output "== C1 反向覆盖:每个 throw 都必须可触发 =="
ExpectThrow 'TickFloor 期望值错' `
    { Assert-JevTickFloor -RawPrice 67432.178 -TickSize 0.01 -Expected 67432.18 } 'TickFloor 失败'
ExpectThrow 'TieredMargin MM 错' `
    { Assert-JevTieredMargin -PositionNotional 400000.0 -ExpectedMM 5251.0 -ExpectedDeduction 2750.0 } 'MM错误'
ExpectThrow 'TieredMargin 扣除数错' `
    { Assert-JevTieredMargin -PositionNotional 400000.0 -ExpectedMM 5250.0 -ExpectedDeduction 2751.0 } '扣除数错误'
ExpectThrow 'SlippageBudget 穿透判断错' `
    { Assert-JevSlippageBudget -OrderVal 500000.0 -Adv 10000000.0 -DailyVol 0.025 -BudgetBps 15.0 -ExpectPenetrated $false } 'SlippageBudget 失败'

Write-Output "== C1b 正向对照:正确值必须通过(防「拒绝一切」也算合格) =="
Check 'TickFloor 正向' { Assert-JevTickFloor -RawPrice 67432.178 -TickSize 0.01 -Expected 67432.17 | Out-Null }
Check 'TieredMargin 正向(满档)' { Assert-JevTieredMargin -PositionNotional 400000.0 -ExpectedMM 5250.0 -ExpectedDeduction 2750.0 | Out-Null }
Check 'SlippageBudget 正向' { Assert-JevSlippageBudget -OrderVal 500000.0 -Adv 10000000.0 -DailyVol 0.025 -BudgetBps 15.0 -ExpectPenetrated $true | Out-Null }

Write-Output "== C2 三档边界:50k / 250k 两侧 =="
Check '档1 边界内 49999' { Assert-JevTieredMargin -PositionNotional 49999.0 -ExpectedMM 249.995 -ExpectedDeduction 0.0 | Out-Null }
Check '档2 下沿 50001' { Assert-JevTieredMargin -PositionNotional 50001.0 -ExpectedMM 250.01 -ExpectedDeduction 250.0 | Out-Null }
Check '档3 下沿 250001' { Assert-JevTieredMargin -PositionNotional 250001.0 -ExpectedMM 2250.02 -ExpectedDeduction 2750.0 | Out-Null }

Write-Output "== C3 跨实现一致性:PS 与 Python 必须同结果 =="
Check 'C3 档1 40000 deduction=0' { Assert-JevTieredMargin -PositionNotional 40000.0 -ExpectedMM 200.0 -ExpectedDeduction 0.0 | Out-Null }
Check 'C3 档2 60000 deduction=250' { Assert-JevTieredMargin -PositionNotional 60000.0 -ExpectedMM 350.0 -ExpectedDeduction 250.0 | Out-Null }
Check 'C3 TickFloor 0.29 不得下取整到 0.28' { Assert-JevTickFloor -RawPrice 0.29 -TickSize 0.01 -Expected 0.29 | Out-Null }

Write-Output ("`n结果: {0}/{1} 通过" -f ($script:total - $script:failures), $script:total)
if ($script:failures -gt 0) { exit 1 }
exit 0
