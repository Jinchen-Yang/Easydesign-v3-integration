PYTHON ?= python3
CONDA ?= conda
CONDA_ENV ?= easydesign-core
NODE ?= node
NPM ?= npm
PNPM ?= pnpm
WEB_DIR ?= web/target-viewer
UI_WEB_DIR ?= web/workbench
RUNTIME_ENV = HOME=$(CURDIR)/runtime/home \
	TMPDIR=$(CURDIR)/runtime/tmp \
	XDG_CACHE_HOME=$(CURDIR)/runtime/cache/xdg \
	XDG_DATA_HOME=$(CURDIR)/runtime/state/xdg-data \
	XDG_STATE_HOME=$(CURDIR)/runtime/state/xdg-state \
	PIP_CACHE_DIR=$(CURDIR)/runtime/cache/pip \
	NPM_CONFIG_CACHE=$(CURDIR)/runtime/cache/npm \
	COREPACK_HOME=$(CURDIR)/runtime/cache/corepack \
	PLAYWRIGHT_BROWSERS_PATH=$(CURDIR)/runtime/cache/playwright

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
	./easydesign setup --minimal

env-update:
	./easydesign setup --minimal

check:
	$(PYTHON) scripts/sync_status_rollup.py --check
	$(PYTHON) scripts/check_repository.py
	PYTHONPATH=src $(PYTHON) scripts/check_target_viewer_assets.py
	PYTHONPATH=src $(PYTHON) scripts/check_browser_pymol_assets.py
	PYTHONPATH=src $(PYTHON) -c "import easydesign; print(easydesign.__version__)"
	$(PYTHON) -m compileall -q src scripts tests
	$(PYTHON) -m ruff check src scripts tests
	$(PYTHON) -m mypy

test:
	@mkdir -p runtime/tmp
	PYTHONPATH=src TMPDIR=$(CURDIR)/runtime/tmp $(PYTHON) -m pytest --basetemp=runtime/tmp/pytest-$$(date +%s)-$$$$

build: build-ui
	@test ! -e dist/easydesign-0.1.0.dev31-py3-none-any.whl || \
		{ echo "拒绝覆盖现有 wheel；请保留它并使用新的版本号"; exit 1; }
	@mkdir -p runtime/cache/pip runtime/cache/xdg runtime/home runtime/tmp
	$(RUNTIME_ENV) \
		PIP_CONFIG_FILE=/dev/null PIP_INDEX_URL=https://pypi.org/simple \
		PYTHONNOUSERSITE=1 \
		$(PYTHON) -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .
	$(RUNTIME_ENV) \
		PIP_CONFIG_FILE=/dev/null PIP_INDEX_URL=https://pypi.org/simple \
		PYTHONNOUSERSITE=1 \
		$(PYTHON) scripts/check_built_wheel.py

build-ui:
	@mkdir -p runtime/home runtime/tmp runtime/cache/npm runtime/cache/corepack \
		runtime/cache/playwright runtime/cache/xdg runtime/state/xdg-data \
		runtime/state/xdg-state
	cd $(UI_WEB_DIR) && $(RUNTIME_ENV) $(PNPM) install --frozen-lockfile
	@mkdir -p runtime/tmp
	@set -eu; \
		staging="runtime/tmp/ui-build-$$(date +%s)-$$$$"; \
		test ! -e "$$staging"; \
		cd $(UI_WEB_DIR) && $(RUNTIME_ENV) \
			EASYDESIGN_UI_OUT_DIR="$(CURDIR)/$$staging" $(PNPM) build; \
		cd "$(CURDIR)" && $(PYTHON) scripts/publish_ui_build.py "$$staging"

test-web: build-ui
	cd $(WEB_DIR) && $(RUNTIME_ENV) EASYDESIGN_CORE_PYTHON=$(PYTHON) $(NPM) test
	cd $(UI_WEB_DIR) && $(RUNTIME_ENV) \
		EASYDESIGN_WEB_DEV_COMMAND="$(PNPM) dev" $(PNPM) test
