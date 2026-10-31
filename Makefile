# OneShot Makefile
.PHONY: test lint format typecheck clean install dev-install

PYTHON ?= python3
PIP ?= pip

install:
	$(PIP) install -r requirements.txt

dev-install:
	$(PIP) install -r requirements-dev.txt

test:
	$(PYTHON) -m pytest tests/ -q

test-verbose:
	$(PYTHON) -m pytest tests/ -v --tb=short

test-cov:
	$(PYTHON) -m pytest tests/ --cov=agent --cov=tools --cov-report=term-missing

lint:
	$(PYTHON) -m ruff check agent/ tools/ tests/ bin/

format:
	$(PYTHON) -m ruff format agent/ tools/ tests/ bin/

typecheck:
	$(PYTHON) -m mypy agent/ tools/

clean:
	rm -rf __pycache__ .pytest_cache .ruff_cache .mypy_cache
	find . -type f -name "*.pyc" -delete
