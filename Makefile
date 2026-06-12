.PHONY: install dev test run lint docker
install:
	pip install -e ".[dev]"
test:
	pytest -q
run:
	uvicorn iparty.api.app:app --reload --host 0.0.0.0 --port 8000
lint:
	ruff check src tests
docker:
	docker compose up --build
