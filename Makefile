PY ?= .venv/bin/python

setup:
	python3 -m venv .venv
	$(PY) -m pip install -r requirements.txt
	test -f .env || cp .env.example .env
	$(PY) -m app.cli init-db

demo:
	$(PY) -m app.cli demo

serve:
	$(PY) -m app.cli serve

pipeline:
	$(PY) -m app.cli run pipeline

top:
	$(PY) -m app.cli top

test:
	$(PY) -m pytest -q

.PHONY: setup demo serve pipeline top test
