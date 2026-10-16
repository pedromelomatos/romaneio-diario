$ErrorActionPreference = 'Stop'
$taskName = 'RomaneioDiario-GerarRoteiro'
try {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Write-Host 'Ja existe uma tarefa com esse nome. Confira-a no Agendador de Tarefas do Windows.'
        exit 1
    }
    $scriptFile = Join-Path $PSScriptRoot 'executar_agendado.ps1'
    $shellFile = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $taskArguments = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $scriptFile + '"'
    $action = New-ScheduledTaskAction -Execute $shellFile -Argument $taskArguments -WorkingDirectory $PSScriptRoot
    $trigger = New-ScheduledTaskTrigger -Daily -At '13:00'
    $windowsUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $windowsUser -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
        -Description 'Gera o roteiro de notas de saida do dia, somente na situacao Emitida DANFE.' | Out-Null
    Write-Host 'Agendamento criado: todos os dias as 13h, neste usuario Windows.'
    Write-Host 'Mantenha o computador ligado e o usuario conectado no horario.'
    Write-Host 'O agendamento usa a conexao Bling ja autorizada neste usuario.'
} catch {
    Write-Host 'Nao foi possivel cadastrar o agendamento. Confira as permissoes no Agendador de Tarefas.'
    exit 1
}
