PY ?= python
PIP ?= pip

.PHONY: install dev-install fmt lint type test check probe seed webhook up down logs

install:
	$(PIP) install .

dev-install:
	$(PIP) install -e ".[dev]"

fmt:
	black app tests scripts
	ruff check --fix app tests scripts

lint:
	ruff check app tests scripts
	black --check app tests scripts

type:
	mypy app scripts

test:
	pytest -q

check: lint type test

probe:
	$(PY) scripts/api_probe.py

seed:
	$(PY) scripts/seed_tags.py

webhook:
	$(PY) scripts/set_webhook.py

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f app
