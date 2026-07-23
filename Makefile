PYTHON ?= python3

.PHONY: help check test build

help:
	@echo "make check PYTHON=/path/to/python3.11"
	@echo "make test  PYTHON=/path/to/python3.11"
	@echo "make build PYTHON=/path/to/python3.11"

check:
	$(PYTHON) scripts/check_repository.py
	PYTHONPATH=src $(PYTHON) -c "import easydesign; print(easydesign.__version__)"
	$(PYTHON) -m compileall -q src scripts tests

test:
	$(PYTHON) -m pytest

build:
	$(PYTHON) -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .
