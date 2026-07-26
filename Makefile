PYTHON ?= python3
CONDA ?= conda
CONDA_ENV ?= easydesign-core
NODE ?= node
NPM ?= npm
PNPM ?= pnpm
WEB_DIR ?= web/target-viewer
UI_WEB_DIR ?= web/workbench

.PHONY: help env-create env-update check test build build-ui test-web

help:
	@echo "make env-create CONDA=/path/to/conda"
	@echo "make env-update CONDA=/path/to/conda"
	@echo "make check PYTHON=/path/to/python3.11"
	@echo "make test  PYTHON=/path/to/python3.11"
	@echo "make build PYTHON=/path/to/python3.11"
	@echo "make build-ui PNPM=/path/to/pnpm"
	@echo "make test-web NPM=/path/to/npm PNPM=/path/to/pnpm"

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

build: build-ui
	$(PYTHON) -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .
	$(PYTHON) scripts/check_built_wheel.py

build-ui:
	cd $(UI_WEB_DIR) && $(PNPM) install --frozen-lockfile
	cd $(UI_WEB_DIR) && $(PNPM) build

test-web: build-ui
	cd $(WEB_DIR) && EASYDESIGN_CORE_PYTHON=$(PYTHON) $(NPM) test
	cd $(UI_WEB_DIR) && $(PNPM) test
