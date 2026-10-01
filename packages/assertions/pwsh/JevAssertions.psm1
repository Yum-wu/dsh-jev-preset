<#
.SYNOPSIS
    JEV 工业级量化数学与风控标准断言模块 (PowerShell 版)
.DESCRIPTION
    为 DSH JEV 预设提供统一的客观断言函数，支持 Tick 截断、维持保证金、滑点冲击与对数收益率安全断言。
#>

function Assert-JevTickFloor {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][double]$RawPrice,
        [Parameter(Mandatory=$true)][double]$TickSize,
        [Parameter(Mandatory=$true)][double]$Expected
    )
    $factor = [Math]::Pow(10, (-[Math]::Log10($TickSize)))
    $scaled = $RawPrice * $factor
    # ⚠ double 乘法的表示误差会让「本该整数」的值略小于整数,被 Floor 少算一格。
    #   实测(2026-10-01 Round 29):0.29 * 100.0 = 28.999999999999996 -> 0.28,而正确是 0.29。
    #   Python 侧用 Decimal 无此问题 —— 即同一个 tick 规则,两套实现给出不同结果。
    #   加一个相对 epsilon 把「因表示误差略小于整数」的值拉回整数。
    $eps = [Math]::Abs($scaled) * 1e-9 + 1e-9
    $actual = [Math]::Floor($scaled + $eps) / $factor
    if ([Math]::Abs($actual - $Expected) -gt 0.0000001) {
        throw "[Assert-JevTickFloor 失败] Raw=$RawPrice, Tick=$TickSize, 期望=$Expected, 实际=$actual"
    }
    return $true
}

function Assert-JevTieredMargin {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][double]$PositionNotional,
        [Parameter(Mandatory=$true)][double]$ExpectedMM,
        [Parameter(Mandatory=$true)][double]$ExpectedDeduction
    )
    # 3 档分段计算 (50k @ 0.5%, 200k @ 1.0%, rest @ 2.0%)
    $mm = 0.0
    if ($PositionNotional -gt 250000.0) {
        $mm = (50000.0 * 0.005) + (200000.0 * 0.01) + (($PositionNotional - 250000.0) * 0.02)
    } elseif ($PositionNotional -gt 50000.0) {
        $mm = (50000.0 * 0.005) + (($PositionNotional - 50000.0) * 0.01)
    } else {
        $mm = $PositionNotional * 0.005
    }

    # ⚠⚠ 扣除数必须**逐档累进**,不能写成 `Notional * 0.02 - mm`
    #   (2026-10-01 Round 29 修复;跨实现一致性 C3 实测发现的)
    #
    #   旧式 `N*0.02 - mm` 只在**满档**时恰好等于累进值;中低档两者相差极大:
    #       notional=40000 -> 旧式 600   累进 0
    #       notional=60000 -> 旧式 850   累进 250
    #       notional=400000 -> 旧式 2750 累进 2750  (仅此一档碰巧相同)
    #   而 Python 侧 `jevbench.solve.tiered_mm` 用的正是累进式
    #   (deduction += lower * (r - prev_mmr)),见 benchmarks/accuracy/jevbench/solve.py:46-58。
    #   persona 把 PS 面与 Python 面**并列推荐**,不同结果 = 用户按 PS 算、按 Python 校验必错。
    #
    #   ⚠ 累进项在**档内是常数**:Python 循环里 `deduction += lower*(r-prev_mmr)` 先累加,
    #     `break` 在其后,而 lower 在进入某档时已固定为该档下限。故:
    #       档1: 0 × (0.005-0)               = 0
    #       档2: 50000 × (0.01-0.005)        = 250
    #       档3: 250 + 200000 × (0.02-0.01)  = 2250  ←⚠ 见下,我第一次写成 2750 是错的
    #
    #   (第一版我按「lower 随 notional 变」来写,实测 250001 得到 1250.01,
    #    与 Python 的 2750 不符。逐档手推后才发现:进入档3 时 lower=200000 而不是 250000 ——
    #    因为档2 的上限是 250000,进入档3 的 lower 应是 **该档下限 = 上一档上限 250000**… )
    $ded = 0.0
    if ($PositionNotional -gt 250000.0) {
        # 进入档1 时 lower=0(项 0);进入档2 时 lower=50000(项 250);
        # 进入档3 时 lower=250000(项 250000*0.01=2500) → 合计 2750
        $ded = (50000.0 * (0.01 - 0.005)) + (250000.0 * (0.02 - 0.01))
    } elseif ($PositionNotional -gt 50000.0) {
        $ded = (50000.0 * (0.01 - 0.005))
    }

    if ([Math]::Abs($mm - $ExpectedMM) -gt 0.01) {
        throw "[Assert-JevTieredMargin MM错误] 期望=$ExpectedMM, 实际=$mm"
    }
    if ([Math]::Abs($ded - $ExpectedDeduction) -gt 0.01) {
        throw "[Assert-JevTieredMargin 扣除数错误] 期望=$ExpectedDeduction, 实际=$ded"
    }
    return $true
}

function Assert-JevSlippageBudget {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][double]$OrderVal,
        [Parameter(Mandatory=$true)][double]$Adv,
        [Parameter(Mandatory=$true)][double]$DailyVol,
        [Parameter(Mandatory=$true)][double]$BudgetBps,
        [Parameter(Mandatory=$true)][bool]$ExpectPenetrated
    )
    $impact = $DailyVol * [Math]::Sqrt($OrderVal / $Adv) * 0.5
    $impactBps = $impact * 10000.0
    $isPenetrated = ($impactBps -gt $BudgetBps)
    if ($isPenetrated -ne $ExpectPenetrated) {
        throw "[Assert-JevSlippageBudget 失败] 期望穿透=$ExpectPenetrated, 实际冲击=$impactBps bps, 预算=$BudgetBps bps"
    }
    return $true
}

Export-ModuleMember -Function Assert-JevTickFloor, Assert-JevTieredMargin, Assert-JevSlippageBudget