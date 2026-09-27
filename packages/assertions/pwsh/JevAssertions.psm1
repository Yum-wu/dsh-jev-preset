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
    $actual = [Math]::Floor($RawPrice * $factor) / $factor
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
    $ded = ($PositionNotional * 0.02) - $mm
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