param([string]$Python = "", [switch]$SkipTests)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $Python) { $Python = Join-Path $projectRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $Python)) { throw 'Crea .venv e instala requirements-build.txt antes de generar el ejecutable.' }
$Python = (Resolve-Path -LiteralPath $Python).Path
$previousCache = $env:PYINSTALLER_CONFIG_DIR
$env:PYINSTALLER_CONFIG_DIR = Join-Path $projectRoot 'build\pyinstaller-cache'
Push-Location -LiteralPath $projectRoot
try {
    & $Python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Las dependencias instaladas no son compatibles.' }
    if (-not $SkipTests) {
        & $Python -m unittest discover -s tests
        if ($LASTEXITCODE -ne 0) { throw 'Fallaron los tests. No se genero un nuevo ejecutable.' }
    }
    & $Python scripts/generate_icon.py
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo generar el icono.' }
    & $Python -m PyInstaller --noconfirm --clean WiZController.spec
    if ($LASTEXITCODE -ne 0) { throw 'Fallo PyInstaller.' }
    $application = Join-Path $projectRoot 'dist\WiZController\WiZController.exe'
    $hash = (Get-FileHash -LiteralPath $application -Algorithm SHA256).Hash
    Write-Output "Ejecutable: $application"
    Write-Output "SHA256: $hash"
    Write-Output 'Distribui la carpeta dist\WiZController completa, incluido _internal. No se publico ningun binario.'
} finally {
    Pop-Location
    $env:PYINSTALLER_CONFIG_DIR = $previousCache
}
