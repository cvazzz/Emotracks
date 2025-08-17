PYTHON=python

.PHONY: install dev lint format test openapi coverage clean

install:
	$(PYTHON) -m pip install -r requirements.txt
	@if [ -f requirements-dev.txt ]; then $(PYTHON) -m pip install -r requirements-dev.txt; fi

dev: install
	uvicorn backend.app.main:app --reload

lint:
	ruff check .

format:
	black .

test:
	pytest -q

openapi:
	$(PYTHON) - <<'PY'
from backend.app.main import app
import json, pathlib
pathlib.Path('openapi.json').write_text(json.dumps(app.openapi(), indent=2))
print('openapi.json generado')
PY

coverage:
	pytest --cov=backend.app --cov-report=term-missing

clean:
	rm -f openapi.json test.db
	find . -type d -name __pycache__ -exec rm -rf {} +
