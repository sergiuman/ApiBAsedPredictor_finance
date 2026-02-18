.PHONY: run test setup clean backtest

setup:
	python -m venv .venv
	. .venv/bin/activate && pip install -r requirements.txt
	@echo "Setup complete. Activate with: source .venv/bin/activate"
	@echo "Then copy .env.example to .env and add your keys."

run:
	python src/main.py

test:
	python -m pytest tests/ -v

backtest:
	python src/history.py

clean:
	rm -rf .venv __pycache__ src/__pycache__ tests/__pycache__ data/last_*.json
