Import-Module (Join-Path $PSScriptRoot "../packages/assertions/pwsh/JevAssertions.psm1") -Force

Write-Output "[1] 测试 Assert-JevTickFloor..."
$r1 = Assert-JevTickFloor -RawPrice 67432.178 -TickSize 0.01 -Expected 67432.17
if ($r1) { Write-Output "  PASS Assert-JevTickFloor" }

Write-Output "[2] 测试 Assert-JevTieredMargin..."
$r2 = Assert-JevTieredMargin -PositionNotional 400000.0 -ExpectedMM 5250.0 -ExpectedDeduction 2750.0
if ($r2) { Write-Output "  PASS Assert-JevTieredMargin" }

Write-Output "[3] 测试 Assert-JevSlippageBudget..."
$r3 = Assert-JevSlippageBudget -OrderVal 500000.0 -Adv 10000000.0 -DailyVol 0.025 -BudgetBps 15.0 -ExpectPenetrated $true
if ($r3) { Write-Output "  PASS Assert-JevSlippageBudget" }

Write-Output "PowerShell 断言全部通过！"