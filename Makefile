.PHONY: install install-ml lint format typecheck test seed simulate history train serve dashboard demo clean

VENV ?= .venv
PY := $(VENV)/bin/python
UV := uv

install:
	$(UV) venv $(VENV)
	$(UV) pip install -p $(VENV) -e ".[dev]"

install-ml:
	$(UV) pip install -p $(VENV) -e ".[dev,ml,cv,geo]"

lint:
	$(VENV)/bin/ruff check traffic_os tests

format:
	$(VENV)/bin/black traffic_os tests
	$(VENV)/bin/ruff check --fix traffic_os tests

typecheck:
	$(VENV)/bin/mypy traffic_os

test:
	$(VENV)/bin/pytest -q

seed:
	$(PY) -m traffic_os.cli seed

simulate:
	$(PY) -m traffic_os.cli simulate

history:
	$(PY) -m traffic_os.cli history

train:
	$(PY) -m traffic_os.cli train

serve:
	$(VENV)/bin/uvicorn traffic_os.api.app:app --host 0.0.0.0 --port 8000 --reload

dashboard:
	cd dashboard && pnpm install && pnpm dev

demo:
	bash scripts/run-dev.sh

clean:
	rm -rf data/traffic_os.db data/kuzu data/blobs
