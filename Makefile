PYTHON ?= python3
CONDA ?= conda
CONDA_ENV ?= easydesign-core

.PHONY: help env-create env-update check test build

help:
	@echo "make env-create CONDA=/path/to/conda"
	@echo "make env-update CONDA=/path/to/conda"
	@echo "make check PYTHON=/path/to/python3.11"
	@echo "make test  PYTHON=/path/to/python3.11"
	@echo "make build PYTHON=/path/to/python3.11"

env-create:
	$(CONDA) env create --file environment.yml

env-update:
	$(CONDA) env update --name $(CONDA_ENV) --file environment.yml --prune

check:
	$(PYTHON) scripts/check_repository.py
	PYTHONPATH=src $(PYTHON) -c "import easydesign; print(easydesign.__version__)"
	$(PYTHON) -m compileall -q src scripts tests
	$(PYTHON) -m ruff check src scripts tests
	$(PYTHON) -m mypy

test:
	$(PYTHON) -m pytest

build:
	$(PYTHON) -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .
