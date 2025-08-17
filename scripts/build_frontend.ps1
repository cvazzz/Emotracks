Param(
  [string]$FlutterPath = "flutter",
  [string]$FrontendDir = "frontend",
  [string]$OutDir = "backend/static",
  [string]$DockerImage = "ghcr.io/cirruslabs/flutter:stable"
)

function Test-CommandExists {
  param([string]$cmd)
  $old = $ErrorActionPreference; $ErrorActionPreference = 'SilentlyContinue'
  $null = Get-Command $cmd
  $exists = $?
  $ErrorActionPreference = $old
  return $exists
}

Write-Host "Building Flutter Web..."
if (Test-CommandExists $FlutterPath) {
  Push-Location $FrontendDir
  & $FlutterPath build web --release
  $code = $LASTEXITCODE
  Pop-Location
  if ($code -ne 0) { Write-Error "Flutter build failed ($code)"; exit 1 }
}
else {
  Write-Warning "Flutter no está instalado o no está en PATH. Usando contenedor Docker para compilar."
  $frontendAbs = (Resolve-Path $FrontendDir).Path
  $image = $DockerImage
  Write-Host "Descargando imagen $image si es necesario..."
  docker pull $image | Out-Null
  if ($LASTEXITCODE -ne 0) { Write-Error "No se pudo descargar la imagen de Flutter"; exit 1 }
  Write-Host "Compilando en Docker..."
  docker run --rm -v "${frontendAbs}:/work" -w /work $image flutter build web --release
  if ($LASTEXITCODE -ne 0) { Write-Error "Compilación en Docker falló"; exit 1 }
}

Write-Host "Copiando build a $OutDir ..."
if (!(Test-Path $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }
Copy-Item "$FrontendDir/build/web/*" "$OutDir/" -Recurse -Force
Write-Host "Listo. Archivos estáticos en $OutDir"
