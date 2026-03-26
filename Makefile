.PHONY: install install-dev test test-cov lint format typecheck backtest clean \
        docker-build docker-up docker-down shadow-mode shadow-stats \
        download-data run-api run-engine run-telegram run-all test-apns

# ── Setup ──────────────────────────────────────────────────────────────────────
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt
	pip install -e .

# ── Code quality ───────────────────────────────────────────────────────────────
lint:
	ruff check engine/ data/ backtest/ tests/

format:
	black engine/ data/ backtest/ tests/ config/

typecheck:
	mypy engine/ data/ backtest/

# ── Tests ──────────────────────────────────────────────────────────────────────
test:
	pytest tests/ -v

test-cov:
	pytest tests/ --cov=engine --cov=data --cov=backtest --cov-report=term-missing

test-module:
	# Run tests for a specific module: make test-module MODULE=test_market_structure
	pytest tests/$(MODULE).py -v

# ── Backtesting ────────────────────────────────────────────────────────────────
backtest:
	# Full backtest: make backtest PAIR=XAUUSD STYLE=day_trading
	python -m backtest.harness --pair $(PAIR) --style $(STYLE)

backtest-all:
	python -m backtest.harness --pair XAUUSD --style day_trading
	python -m backtest.harness --pair XAUUSD --style scalping
	python -m backtest.harness --pair XAUUSD --style swing_trading
	python -m backtest.harness --pair GBPJPY --style day_trading
	python -m backtest.harness --pair GBPJPY --style scalping
	python -m backtest.harness --pair GBPJPY --style swing_trading

optimize:
	# Optuna weight optimization: make optimize PAIR=XAUUSD TRIALS=1000
	python -m backtest.optimizer --pair $(PAIR) --trials $(TRIALS)

shadow:
	# Run engine in shadow mode (no signals shown to users)
	SHADOW_MODE=true python -m engine.aggregator

# ── Data ───────────────────────────────────────────────────────────────────────
validate-data:
	python -m data.validator --pair XAUUSD
	python -m data.validator --pair GBPJPY

resample:
	# Resample 1m data to all timeframes: make resample PAIR=XAUUSD
	python -m data.resampler --pair $(PAIR)

# ── Clean ──────────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
