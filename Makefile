.PHONY: install run test test-alle lint format dokumentation

install:        ## Entwicklungsumgebung aufsetzen
	pip install -e ".[dev]"

run:            ## App lokal starten
	streamlit run streamlit_app.py

test:           ## Test-Suite ausführen (ohne die langsamen)
	pytest

test-alle:      ## Test-Suite inkl. lineare Programme – vor jedem Merge
	pytest --langsam

lint:           ## Statische Analyse
	ruff check .

format:         ## Auto-Format (ruff)
	ruff check --fix .
	ruff format .

dokumentation:  ## Rechenweg-Dokumentation als PDF bauen
	python docs/rechenmodell/beispiel.py
	python docs/rechenmodell/build_pdf.py
