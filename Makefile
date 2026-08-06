PYTHON ?= $(CURDIR)/.venv/bin/python
EASYDESIGN ?= $(CURDIR)/.venv/bin/easydesign
UV ?=
CONDA ?= conda
CONDA_ENV ?= easydesign-core
NODE ?=
NPM ?=
PNPM ?=
WEB_DIR ?= web/target-viewer
UI_WEB_DIR ?= web/workbench
RUNTIME_ENV = HOME="$(CURDIR)/runtime/home" \
	TMPDIR="$(CURDIR)/runtime/tmp" \
	PYTHONPYCACHEPREFIX="$(CURDIR)/runtime/cache/dev/pycache" \
	RUFF_CACHE_DIR="$(CURDIR)/runtime/cache/dev/ruff" \
	XDG_CACHE_HOME="$(CURDIR)/runtime/cache/xdg" \
	XDG_DATA_HOME="$(CURDIR)/runtime/state/xdg-data" \
	XDG_STATE_HOME="$(CURDIR)/runtime/state/xdg-state" \
	PIP_CACHE_DIR="$(CURDIR)/runtime/cache/pip" \
	UV_CACHE_DIR="$(CURDIR)/runtime/cache/uv" \
	NPM_CONFIG_CACHE="$(CURDIR)/runtime/cache/npm" \
	COREPACK_HOME="$(CURDIR)/runtime/cache/corepack" \
	PLAYWRIGHT_BROWSERS_PATH="$(CURDIR)/runtime/cache/playwright"

.PHONY: help ensure-venv env-create env-update check test verify-fast \
	verify-integration build-ui-staging build-wheel-staging test-web \
	test-web-chromium release-build-ui release-build build build-ui

help:
	@echo "make verify-fast         # changed-path focused checks"
	@echo "make verify-integration  # complete Python regression"
	@echo "make build-ui-staging    # build only under runtime/"
	@echo "make build-wheel-staging # wheel only under runtime/"
	@echo "make test-web            # Web tests against runtime staging"
	@echo "make release-build RELEASE=1  # publish assets and dist wheel"

ensure-venv:
	@test -x "$(PYTHON)" && test -x "$(EASYDESIGN)" || { \
		echo "ERROR: 缺少仓库 .venv；请运行 uv sync --frozen --extra ui --extra dev" >&2; \
		exit 2; \
	}

env-create: ensure-venv
	$(EASYDESIGN) setup --minimal

env-update: ensure-venv
	$(EASYDESIGN) setup --minimal

check: ensure-venv
	@mkdir -p runtime/tmp runtime/cache/dev/pycache runtime/cache/dev/ruff
	$(RUNTIME_ENV) $(PYTHON) scripts/sync_status_rollup.py --check
	$(RUNTIME_ENV) $(PYTHON) scripts/check_repository.py
	$(RUNTIME_ENV) PYTHONPATH=src $(PYTHON) scripts/check_target_viewer_assets.py
	$(RUNTIME_ENV) PYTHONPATH=src $(PYTHON) scripts/check_browser_pymol_assets.py
	$(RUNTIME_ENV) PYTHONPATH=src $(PYTHON) -c "import easydesign; print(easydesign.__version__)"
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

build-ui-staging: ensure-venv
	@mkdir -p runtime/home runtime/tmp runtime/cache/npm runtime/cache/corepack \
		runtime/cache/playwright runtime/cache/xdg runtime/state/xdg-data \
		runtime/state/xdg-state
	@set -eu; \
		node="$(NODE)"; pnpm="$(PNPM)"; \
		if test -z "$$node"; then node="$$("$(PYTHON)" scripts/dev.py tool-path node)"; fi; \
		if test -z "$$pnpm"; then pnpm="$$("$(PYTHON)" scripts/dev.py tool-path pnpm)"; fi; \
		node_bin="$$(dirname "$$node")"; \
		staging="runtime/tmp/ui-build-staging-$$(date +%s)-$$$$"; \
		test ! -e "$$staging"; \
		mkdir -p "$$staging"; \
		cd "$(CURDIR)/$(UI_WEB_DIR)" && PATH="$$node_bin:$$PATH" $(RUNTIME_ENV) \
			"$$pnpm" install --frozen-lockfile; \
		cd "$(CURDIR)/$(UI_WEB_DIR)" && PATH="$$node_bin:$$PATH" $(RUNTIME_ENV) \
			EASYDESIGN_UI_OUT_DIR="$(CURDIR)/$$staging" "$$pnpm" build; \
		echo "UI staging: $(CURDIR)/$$staging"

build-wheel-staging: ensure-venv
	@mkdir -p runtime/builds runtime/cache/pip runtime/cache/xdg runtime/home runtime/tmp
	@set -eu; \
		uv="$(UV)"; \
		if test -z "$$uv"; then uv="$$("$(PYTHON)" scripts/dev.py tool-path uv)"; fi; \
		version="$$("$(PYTHON)" -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"; \
		staging="runtime/builds/$${version}-$$(git rev-parse --short HEAD)-$$(date +%s)-$$$$"; \
		test ! -e "$$staging"; \
		source="$$staging/source"; \
		mkdir -p "$$source"; \
		git ls-files --cached --others --exclude-standard -z | \
			tar --null --files-from=- --create | tar --extract --directory="$$source"; \
		$(RUNTIME_ENV) "$$uv" build --wheel --offline --no-create-gitignore \
			--python "$(PYTHON)" --out-dir "$$staging" "$$source"; \
		wheel="$$(find "$$staging" -maxdepth 1 -type f -name 'easydesign-*.whl' -print -quit)"; \
		test -n "$$wheel"; \
		$(RUNTIME_ENV) EASYDESIGN_UV="$$uv" PYTHONNOUSERSITE=1 \
			"$(PYTHON)" scripts/check_built_wheel.py --wheel "$$wheel"; \
		echo "Wheel staging: $(CURDIR)/$$wheel"

test-web-chromium: ensure-venv
	@set -eu; \
		node="$(NODE)"; pnpm="$(PNPM)"; \
		if test -z "$$node"; then node="$$("$(PYTHON)" scripts/dev.py tool-path node)"; fi; \
		if test -z "$$pnpm"; then pnpm="$$("$(PYTHON)" scripts/dev.py tool-path pnpm)"; fi; \
		node_bin="$$(dirname "$$node")"; \
		staging="runtime/tmp/ui-test-chromium-$$(date +%s)-$$$$"; \
		test ! -e "$$staging"; \
		mkdir -p "$$staging"; \
		cd "$(CURDIR)/$(UI_WEB_DIR)" && PATH="$$node_bin:$$PATH" $(RUNTIME_ENV) \
			"$$pnpm" install --frozen-lockfile; \
		cd "$(CURDIR)/$(UI_WEB_DIR)" && PATH="$$node_bin:$$PATH" $(RUNTIME_ENV) \
			EASYDESIGN_UI_OUT_DIR="$(CURDIR)/$$staging" "$$pnpm" build; \
		cd "$(CURDIR)/$(UI_WEB_DIR)" && PATH="$$node_bin:$$PATH" $(RUNTIME_ENV) \
			EASYDESIGN_UI_OUT_DIR="$(CURDIR)/$$staging" \
			EASYDESIGN_WEB_DEV_COMMAND="$$pnpm preview" \
			EASYDESIGN_SKIP_FIREFOX=1 EASYDESIGN_SKIP_VISUAL_REGRESSION=1 \
			"$$pnpm" test

test-web: ensure-venv
	@set -eu; \
		node="$(NODE)"; npm="$(NPM)"; pnpm="$(PNPM)"; \
		if test -z "$$node"; then node="$$("$(PYTHON)" scripts/dev.py tool-path node)"; fi; \
		if test -z "$$npm"; then npm="$$("$(PYTHON)" scripts/dev.py tool-path npm)"; fi; \
		if test -z "$$pnpm"; then pnpm="$$("$(PYTHON)" scripts/dev.py tool-path pnpm)"; fi; \
		node_bin="$$(dirname "$$node")"; \
		staging="runtime/tmp/ui-test-$$(date +%s)-$$$$"; \
		test ! -e "$$staging"; \
		mkdir -p "$$staging"; \
		cd "$(CURDIR)/$(WEB_DIR)" && PATH="$$node_bin:$$PATH" $(RUNTIME_ENV) \
			EASYDESIGN_CORE_PYTHON="$(PYTHON)" "$$npm" test; \
		cd "$(CURDIR)/$(UI_WEB_DIR)" && PATH="$$node_bin:$$PATH" $(RUNTIME_ENV) \
			"$$pnpm" install --frozen-lockfile; \
		cd "$(CURDIR)/$(UI_WEB_DIR)" && PATH="$$node_bin:$$PATH" $(RUNTIME_ENV) \
			EASYDESIGN_UI_OUT_DIR="$(CURDIR)/$$staging" "$$pnpm" build; \
		cd "$(CURDIR)/$(UI_WEB_DIR)" && PATH="$$node_bin:$$PATH" $(RUNTIME_ENV) \
			EASYDESIGN_UI_OUT_DIR="$(CURDIR)/$$staging" \
			EASYDESIGN_WEB_DEV_COMMAND="$$pnpm preview" "$$pnpm" test

release-build-ui: ensure-venv
	@test "$(RELEASE)" = "1" || { echo "ERROR: 正式静态资产发布必须显式传 RELEASE=1" >&2; exit 2; }
	@set -eu; \
		node="$(NODE)"; pnpm="$(PNPM)"; \
		if test -z "$$node"; then node="$$("$(PYTHON)" scripts/dev.py tool-path node)"; fi; \
		if test -z "$$pnpm"; then pnpm="$$("$(PYTHON)" scripts/dev.py tool-path pnpm)"; fi; \
		node_bin="$$(dirname "$$node")"; \
		staging="runtime/tmp/ui-release-$$(date +%s)-$$$$"; \
		test ! -e "$$staging"; \
		mkdir -p "$$staging"; \
		cd "$(CURDIR)/$(UI_WEB_DIR)" && PATH="$$node_bin:$$PATH" $(RUNTIME_ENV) \
			"$$pnpm" install --frozen-lockfile; \
		cd "$(CURDIR)/$(UI_WEB_DIR)" && PATH="$$node_bin:$$PATH" $(RUNTIME_ENV) \
			EASYDESIGN_UI_OUT_DIR="$(CURDIR)/$$staging" "$$pnpm" build; \
		cd "$(CURDIR)" && "$(PYTHON)" scripts/publish_ui_build.py "$$staging"

release-build: ensure-venv
	@test "$(RELEASE)" = "1" || { echo "ERROR: 正式构建必须显式传 RELEASE=1" >&2; exit 2; }
	@$(MAKE) release-build-ui RELEASE=1 PYTHON="$(PYTHON)" PNPM="$(PNPM)"
	@mkdir -p dist runtime/cache/pip runtime/cache/xdg runtime/home runtime/tmp
	@set -eu; \
		uv="$(UV)"; \
		if test -z "$$uv"; then uv="$$("$(PYTHON)" scripts/dev.py tool-path uv)"; fi; \
		version="$$("$(PYTHON)" -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"; \
		wheel="dist/easydesign-$${version}-py3-none-any.whl"; \
		test ! -e "$$wheel" || { echo "ERROR: 拒绝覆盖现有正式 wheel: $$wheel" >&2; exit 1; }; \
		source="runtime/tmp/wheel-release-source-$$(date +%s)-$$$$"; \
		test ! -e "$$source"; \
		mkdir -p "$$source"; \
		git ls-files --cached --others --exclude-standard -z | \
			tar --null --files-from=- --create | tar --extract --directory="$$source"; \
		$(RUNTIME_ENV) "$$uv" build --wheel --offline --no-create-gitignore \
			--python "$(PYTHON)" --out-dir dist "$$source"; \
		$(RUNTIME_ENV) EASYDESIGN_UV="$$uv" PYTHONNOUSERSITE=1 \
			"$(PYTHON)" scripts/check_built_wheel.py --wheel "$$wheel"

build:
	@test "$(RELEASE)" = "1" || { \
		echo "ERROR: make build 是正式发布入口；请使用 staging 目标，或显式传 RELEASE=1" >&2; \
		exit 2; \
	}
	@$(MAKE) release-build RELEASE=1 PYTHON="$(PYTHON)" PNPM="$(PNPM)"

build-ui:
	@test "$(RELEASE)" = "1" || { \
		echo "ERROR: make build-ui 会发布正式静态资产；日常开发请用 make build-ui-staging" >&2; \
		exit 2; \
	}
	@$(MAKE) release-build-ui RELEASE=1 PYTHON="$(PYTHON)" PNPM="$(PNPM)"
