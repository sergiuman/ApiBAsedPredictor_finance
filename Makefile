.PHONY: run test setup clean backtest ui

setup:
	python -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt
	@echo "Setup complete. Activate with: source .venv/bin/activate"
	@echo "Then copy .env.example to .env and add your keys."

run:
	python -m src.main

test:
	python -m pytest tests/ -v

backtest:
	python -m src.history

ui:
	python -m streamlit run src/app.py

clean:
	rm -rf .venv __pycache__ src/__pycache__ tests/__pycache__ data/last_*.json
