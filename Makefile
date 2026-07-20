.PHONY: install run test lint format

install:        ## Entwicklungsumgebung aufsetzen
	pip install -e ".[dev]"

run:            ## App lokal starten
	streamlit run streamlit_app.py

test:           ## Test-Suite ausführen
	pytest

lint:           ## Statische Analyse
	ruff check .

format:         ## Auto-Format (ruff)
	ruff check --fix .
	ruff format .
