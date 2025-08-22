Param(
    [Parameter(Position=0)] [string]$Task = 'help'
)

function Show-Help {
    Write-Host "Tareas disponibles:" -ForegroundColor Cyan
    Write-Host "  install    - Instala dependencias (prod + dev)"
    Write-Host "  dev        - Levanta servidor uvicorn (reload)"
    Write-Host "  lint       - Ruff lint"
    Write-Host "  format     - Black format"
    Write-Host "  test       - Ejecuta tests (-q)"
    Write-Host "  openapi    - Genera openapi.json"
    Write-Host "  coverage   - Ejecuta pytest con coverage"
    Write-Host "  clean      - Limpia artefactos (openapi.json, test.db, __pycache__)"
}

switch ($Task) {
  'install' {
    pip install -r requirements.txt
    if (Test-Path requirements-dev.txt) { pip install -r requirements-dev.txt }
  }
  'dev' { uvicorn backend.app.main:app --reload }
  'lint' { ruff check . }
  'format' { black . }
  'test' { pytest -q }
    'openapi' {
      python -c "import json, pathlib; from backend.app.main import app; pathlib.Path('openapi.json').write_text(json.dumps(app.openapi(), indent=2)); print('openapi.json generado')"
    }
    'coverage' { pytest --cov=backend.app --cov-report=term-missing }
    'clean' {
      if (Test-Path openapi.json) { Remove-Item openapi.json }
      if (Test-Path test.db) { Remove-Item test.db }
      Get-ChildItem -Recurse -Directory -Filter __pycache__ | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
    }
    Default { Show-Help }
  }

