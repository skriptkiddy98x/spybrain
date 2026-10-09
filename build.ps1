$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw '.venv is missing. Follow README first.' }
& $pythonPath -m pip install -r requirements.txt 'pyinstaller==6.22.3'
if ($LASTEXITCODE -ne 0) { throw 'Installing dependencies failed.' }
& $pythonPath -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
& $pythonPath -m PyInstaller --clean --noconfirm SpyBrain.spec
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
$bundlePath = Join-Path $PSScriptRoot 'dist\SpyBrain'
Copy-Item -LiteralPath QUICKSTART.txt,THIRD_PARTY_NOTICES.md,requirements-lock.txt -Destination $bundlePath -Force
Copy-Item -LiteralPath licenses -Destination $bundlePath -Recurse -Force
$sourcePath = Join-Path $bundlePath 'Source'
New-Item -ItemType Directory -Force $sourcePath | Out-Null
Copy-Item -LiteralPath app.py,osinthub.py,geolocate.py,leaks.py,SpyBrain.spec,build.ps1,requirements.txt,requirements-lock.txt,README.md,CHANGELOG.md,QUICKSTART.txt,THIRD_PARTY_NOTICES.md -Destination $sourcePath -Force
Copy-Item -LiteralPath tests,assets,licenses -Destination $sourcePath -Recurse -Force
# Rebuilding from Source can reuse the PhoneInfoga binary, if bin\ has one (see bin\README.md).
New-Item -ItemType Directory -Force (Join-Path $sourcePath 'bin') | Out-Null
Copy-Item -LiteralPath bin\README.md -Destination (Join-Path $sourcePath 'bin') -Force
if (Test-Path -LiteralPath bin\phoneinfoga.exe) { Copy-Item -LiteralPath bin\phoneinfoga.exe -Destination (Join-Path $sourcePath 'bin') -Force }
Write-Host 'Done: dist\SpyBrain\SpyBrain.exe. Copy the whole SpyBrain folder when moving it.'
