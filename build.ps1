<#
.SYNOPSIS
  Compila, testa e publica o Bombinha.

.EXAMPLE
  .\build.ps1                 # build Release + testes + executável em artifacts\
  .\build.ps1 -SkipTests      # só build e publicação
  .\build.ps1 -E2E            # inclui os testes ponta a ponta (usam mouse e teclado reais!)
#>
param(
    [switch]$SkipTests,
    [switch]$E2E,
    [switch]$NoPublish
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_NOLOGO = '1'

# Usa o dotnet do PATH se ele tiver o SDK 10; senão, a instalação por usuário (dotnet-install.ps1).
$dotnet = 'dotnet'
$local = Join-Path $env:LOCALAPPDATA 'Microsoft\dotnet\dotnet.exe'
$hasSdk10 = $false
try { $hasSdk10 = [bool](& dotnet --list-sdks 2>$null | Select-String '^10\.') } catch { $hasSdk10 = $false }
if (-not $hasSdk10) {
    if (-not (Test-Path $local)) { throw 'SDK do .NET 10 não encontrado. Instale em https://dot.net ou com dotnet-install.ps1 -Channel 10.0.' }
    $dotnet = $local
    $env:DOTNET_ROOT = Split-Path $local
}

function Invoke-Step($title, [scriptblock]$body) {
    Write-Host "==> $title" -ForegroundColor Cyan
    & $body
    if ($LASTEXITCODE -ne 0) { throw "Falhou: $title (código $LASTEXITCODE)" }
}

Invoke-Step 'Build (Release)' { & $dotnet build (Join-Path $root 'Bombinha.slnx') -c Release }

if (-not $SkipTests) {
    Invoke-Step 'Testes unitários' { & $dotnet test (Join-Path $root 'tests\Bombinha.Core.Tests') -c Release --no-build }
    if ($E2E) { $env:BOMBINHA_E2E = '1' } else { Remove-Item env:BOMBINHA_E2E -ErrorAction SilentlyContinue }
    Invoke-Step 'Testes de integração com o Windows' { & $dotnet test (Join-Path $root 'tests\Bombinha.App.IntegrationTests') -c Release --no-build }
}

if (-not $NoPublish) {
    $publishDir = Join-Path $root 'artifacts\publish\win-x64'
    if (Test-Path $publishDir) { Remove-Item $publishDir -Recurse -Force }
    Invoke-Step 'Publicação self-contained (win-x64)' {
        & $dotnet publish (Join-Path $root 'src\Bombinha.App\Bombinha.App.csproj') -p:PublishProfile=win-x64
    }
    [xml]$props = Get-Content (Join-Path $root 'Directory.Build.props')
    $version = ($props.Project.PropertyGroup | Where-Object { $_.Version } | Select-Object -First 1).Version
    $zip = Join-Path $root "artifacts\Bombinha-$version-win-x64.zip"
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Compress-Archive -Path (Join-Path $publishDir 'Bombinha.exe') -DestinationPath $zip -CompressionLevel Optimal
    $exe = Get-Item (Join-Path $publishDir 'Bombinha.exe')
    Write-Host ("Executável: {0} ({1:N1} MB)" -f $exe.FullName, ($exe.Length / 1MB)) -ForegroundColor Green
    Write-Host ("Pacote:     {0} ({1:N1} MB)" -f $zip, ((Get-Item $zip).Length / 1MB)) -ForegroundColor Green
}
