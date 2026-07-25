PYTHON ?= python3
CONDA ?= conda
CONDA_ENV ?= easydesign-core
NODE ?= node
NPM ?= npm
WEB_DIR ?= web/target-viewer

.PHONY: help env-create env-update check test build test-web

help:
	@echo "make env-create CONDA=/path/to/conda"
	@echo "make env-update CONDA=/path/to/conda"
	@echo "make check PYTHON=/path/to/python3.11"
	@echo "make test  PYTHON=/path/to/python3.11"
	@echo "make build PYTHON=/path/to/python3.11"
	@echo "make test-web NPM=/path/to/npm"

env-create:
	$(CONDA) env create --file environment.yml

env-update:
	$(CONDA) env update --name $(CONDA_ENV) --file environment.yml --prune

check:
	$(PYTHON) scripts/sync_status_rollup.py --check
	$(PYTHON) scripts/check_repository.py
	PYTHONPATH=src $(PYTHON) scripts/check_target_viewer_assets.py
	PYTHONPATH=src $(PYTHON) -c "import easydesign; print(easydesign.__version__)"
	$(PYTHON) -m compileall -q src scripts tests
	$(PYTHON) -m ruff check src scripts tests
	$(PYTHON) -m mypy

test:
	PYTHONPATH=src $(PYTHON) -m pytest

build:
	$(PYTHON) -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .
	$(PYTHON) scripts/check_built_wheel.py

test-web:
	cd $(WEB_DIR) && EASYDESIGN_CORE_PYTHON=$(PYTHON) $(NPM) test
