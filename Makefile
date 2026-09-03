.PHONY: install dev test run lint docker ui-test ui-matrix
install:
	pip install -e ".[dev]"
test:
	pytest -q
run:
	uvicorn iparty.api.app:app --reload --host 0.0.0.0 --port 8000
lint:
	ruff check src tests scripts
ui-test:            # 17-profile browser smoke on desktop + phone (IPARTY_UI_FULL=1 for all 100)
	IPARTY_UI=1 pytest tests/ui -q
ui-matrix:          # full 100-profile UX/UI matrix against a running server (IPARTY_BASE=http://...)
	python scripts/ui_matrix.py --strict
docker:
	docker compose up --build
