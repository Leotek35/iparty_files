.PHONY: install dev test run lint docker ui-test ui-matrix catalog catalog-check concept
install:
	pip install -e ".[dev]"
test:
	pytest -q
run:
	uvicorn iparty.api.app:app --reload --host 0.0.0.0 --port 8000
lint:
	ruff check src tests scripts
catalog:            # regenerate the catalog JSON (and palettes) from scripts/catalog_src/
	python scripts/build_catalog.py
catalog-check:      # CI guard: the committed JSON must match the tables
	python scripts/build_catalog.py --check
concept:            # print the Party Concept for a request: make concept ARGS='"Dino Dig" 6 14 650 home'
	python scripts/concept_debug.py $(ARGS)
ui-test:            # 17-profile browser smoke on desktop + phone (IPARTY_UI_FULL=1 for all 100)
	IPARTY_UI=1 pytest tests/ui -q
ui-matrix:          # full 100-profile UX/UI matrix against a running server (IPARTY_BASE=http://...)
	python scripts/ui_matrix.py --strict
docker:
	docker compose up --build
