PYTHON ?= $(CURDIR)/.venv/bin/python
EASYDESIGN ?= $(CURDIR)/.venv/bin/easydesign
WEB_DIR ?= web/target-viewer
RUNTIME_ENV = HOME="$(CURDIR)/runtime/home" \
	TMPDIR="$(CURDIR)/runtime/tmp" \
	PYTHONDONTWRITEBYTECODE=1 \
	PYTHONPYCACHEPREFIX="$(CURDIR)/runtime/cache/dev/pycache" \
	RUFF_CACHE_DIR="$(CURDIR)/runtime/cache/dev/ruff" \
	XDG_CACHE_HOME="$(CURDIR)/runtime/cache/xdg" \
	PIP_CACHE_DIR="$(CURDIR)/runtime/cache/pip" \
	UV_CACHE_DIR="$(CURDIR)/runtime/cache/uv" \
	NPM_CONFIG_CACHE="$(CURDIR)/runtime/cache/npm" \
	PLAYWRIGHT_BROWSERS_PATH="$(CURDIR)/runtime/cache/playwright" \
	NODE_EXTRA_CA_CERTS="/etc/ssl/certs/ca-certificates.crt"

.PHONY: help ensure-venv check test verify-fast verify-integration test-web build-wheel-staging

help:
	@echo "./scripts/bootstrap.py --index auto"
	@echo "make verify-fast         # structure, Ruff, mypy, focused tests"
	@echo "make verify-integration  # complete Python and Target Viewer regression"
	@echo "make build-wheel-staging # local product wheel under runtime/builds"

ensure-venv:
	@test -x "$(PYTHON)" && test -x "$(EASYDESIGN)" || { \
		echo "ERROR: 缺少仓库 .venv；请运行 ./scripts/bootstrap.py --index auto" >&2; \
		exit 2; \
	}

check: ensure-venv
	@mkdir -p runtime/tmp runtime/cache/dev/pycache runtime/cache/dev/ruff
	$(RUNTIME_ENV) $(PYTHON) scripts/check_repository.py
	$(RUNTIME_ENV) PYTHONPATH=src $(PYTHON) scripts/check_target_viewer_assets.py
	$(RUNTIME_ENV) $(PYTHON) -m compileall -q src scripts tests
	$(RUNTIME_ENV) $(PYTHON) -m ruff check src scripts tests
	$(RUNTIME_ENV) $(PYTHON) -m mypy

test: ensure-venv
	@mkdir -p runtime/tmp runtime/cache/dev/pycache
	$(RUNTIME_ENV) PYTHONPATH=src $(PYTHON) -m pytest --basetemp=runtime/tmp/pytest-$$(date +%s)-$$$$

verify-fast: ensure-venv
	$(PYTHON) scripts/dev.py verify --mode dev-local

verify-integration: ensure-venv
	$(PYTHON) scripts/dev.py verify --mode integration

test-web: ensure-venv
	@set -eu; \
		node="$$($(PYTHON) scripts/dev.py tool-path node)"; \
		npm="$$($(PYTHON) scripts/dev.py tool-path npm)"; \
		chromium="$${EASYDESIGN_PLAYWRIGHT_CHROMIUM:-}"; \
		if [ -z "$$chromium" ]; then \
			for candidate in /usr/bin/google-chrome-stable /usr/bin/google-chrome /usr/bin/chromium /usr/bin/chromium-browser; do \
				if [ -x "$$candidate" ]; then chromium="$$candidate"; break; fi; \
			done; \
		fi; \
		test -n "$$chromium" || { echo "ERROR: 未找到 Chromium/Chrome" >&2; exit 2; }; \
		if [ ! -x "$(WEB_DIR)/node_modules/.bin/playwright" ]; then \
			PATH="$$(dirname "$$node"):$$PATH" $(RUNTIME_ENV) \
				"$$npm" --prefix "$(WEB_DIR)" ci --prefer-offline --no-audit --no-fund; \
		fi; \
		PATH="$$(dirname "$$node"):$$PATH" $(RUNTIME_ENV) \
			"$$npm" --prefix "$(WEB_DIR)" ls --depth=0 --offline >/dev/null; \
		PATH="$$(dirname "$$node"):$$PATH" $(RUNTIME_ENV) \
			EASYDESIGN_CORE_PYTHON="$(PYTHON)" \
			EASYDESIGN_PLAYWRIGHT_CHROMIUM="$$chromium" \
			"$$npm" --prefix "$(WEB_DIR)" test

build-wheel-staging: ensure-venv
	@mkdir -p runtime/builds runtime/cache/uv runtime/tmp
	@set -eu; \
		staging="runtime/builds/local-$$(git rev-parse --short HEAD)-$$(date +%s)"; \
		source="$$(mktemp -d "$(CURDIR)/runtime/tmp/wheel-source.XXXXXXXX")"; \
		trap 'rm -rf -- "$$source"' EXIT; \
		mkdir -p "$$staging"; \
		cp -a pyproject.toml README.md "$$source/"; \
		mkdir -p "$$source/src"; \
		cp -a src/easydesign "$$source/src/"; \
		$(RUNTIME_ENV) $(PYTHON) -m build --wheel --no-isolation \
			--outdir "$$staging" "$$source"; \
		wheel="$$(find "$$staging" -maxdepth 1 -name 'easydesign_local-*.whl' -print -quit)"; \
		test -n "$$wheel"; \
		$(RUNTIME_ENV) $(PYTHON) scripts/check_built_wheel.py --wheel "$$wheel"; \
		echo "Local wheel staging: $(CURDIR)/$$staging"
