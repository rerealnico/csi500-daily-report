<#
.SYNOPSIS
    创建 Windows 定时任务：每天 15:00（收盘后）自动运行中证500复盘分析
.DESCRIPTION
    以管理员身份运行此脚本，创建每日定时任务。
    任务名: "CSIS500_DailyReport"
    运行时间: 每天 15:00（周一至周五，交易日）
#>

$TaskName = "CSIS500_DailyReport"
$ScriptPath = "D:\qoder workplace\test 1\run_daily.bat"
$TaskPath = "\Qoder\"

# 检查是否以管理员运行
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[ERROR] 请以管理员身份运行此脚本！" -ForegroundColor Red
    Write-Host "        右键 -> 以管理员身份运行" -ForegroundColor Yellow
    exit 1
}

# 检查脚本是否存在
if (-not (Test-Path $ScriptPath)) {
    Write-Host "[ERROR] 找不到脚本: $ScriptPath" -ForegroundColor Red
    exit 1
}

# 创建任务（如果已存在则更新）
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$ScriptPath`""
$Trigger = New-ScheduledTaskTrigger -Daily -At "15:00" -DaysInterval 1
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)

# 只在工作日运行
$Trigger.DaysOfWeek = [Microsoft.PowerShell.ScheduledTask.DaysOfWeek]::Monday -bor
                    [Microsoft.PowerShell.ScheduledTask.DaysOfWeek]::Tuesday -bor
                    [Microsoft.PowerShell.ScheduledTask.DaysOfWeek]::Wednesday -bor
                    [Microsoft.PowerShell.ScheduledTask.DaysOfWeek]::Thursday -bor
                    [Microsoft.PowerShell.ScheduledTask.DaysOfWeek]::Friday

# 注册任务
try {
    # 如果任务已存在则删除重建
    $existing = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Confirm:$false
        Write-Host "[INFO] 已删除旧任务" -ForegroundColor Yellow
    }

    Register-ScheduledTask `
        -TaskName $TaskName `
        -TaskPath $TaskPath `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -RunLevel Limited `
        -User "NT AUTHORITY\SYSTEM" `
        -Force

    Write-Host "[OK] 定时任务创建成功！" -ForegroundColor Green
    Write-Host "    任务名: $TaskName" -ForegroundColor Cyan
    Write-Host "    路径: $TaskPath$TaskName" -ForegroundColor Cyan
    Write-Host "    运行时间: 每个交易日 15:00" -ForegroundColor Cyan
    Write-Host "    脚本: $ScriptPath" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "如需手动测试，请运行: run_daily.bat" -ForegroundColor Yellow
}
catch {
    Write-Host "[ERROR] 创建任务失败: $_" -ForegroundColor Red
    exit 1
}
