$ErrorActionPreference = 'Stop'
$projectFolder = $PSScriptRoot
$logFolder = Join-Path $projectFolder 'outputs\logs'
New-Item -ItemType Directory -Path $logFolder -Force | Out-Null
$logFile = Join-Path $logFolder ('geracao_' + (Get-Date -Format 'yyyy-MM-dd_HHmmss_fff') + '.log')
try {
    $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    $portablePython = Join-Path $projectFolder '_runtime\python.exe'
    $programFile = Join-Path $projectFolder 'bling.py'
    $pythonArguments = @($programFile, 'gerar')
    if (Test-Path -LiteralPath $portablePython) {
        $pythonExecutable = $portablePython
        $pythonArguments = @('-X', 'utf8') + $pythonArguments
    } elseif (Test-Path -LiteralPath $bundledPython) {
        $pythonExecutable = $bundledPython
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        $pythonExecutable = (Get-Command py).Source
        $pythonArguments = @('-3') + $pythonArguments
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $pythonExecutable = (Get-Command python).Source
    } else {
        throw 'Python 3.10 ou superior nao foi encontrado.'
    }
    Push-Location -LiteralPath $projectFolder
    try {
        & $pythonExecutable @pythonArguments 2>&1 | Out-File -LiteralPath $logFile -Encoding utf8
        $programExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    exit $programExitCode
} catch {
    'Nao foi possivel executar a geracao. Confira a instalacao do Python e as permissoes da pasta.' |
        Out-File -LiteralPath $logFile -Encoding utf8 -Append
    exit 1
}
