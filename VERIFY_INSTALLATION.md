# Installation Verification Guide

This guide helps you verify that your Trading Research System installation is working correctly.

## Quick Verification

Run the automated test suite:

```bash
python tests/test_installation.py
```

This will check:
- ✓ Directory structure
- ✓ Module imports
- ✓ Strategy creation
- ✓ Configuration loading
- ✓ Data module functionality
- ✓ Infoway fetcher initialization

## Manual Verification Steps

### 1. Check Python Version

```bash
python --version
```

Expected: Python 3.9 or higher

### 2. Verify Virtual Environment

```bash
# Check if venv exists
ls -la venv/

# Activate virtual environment
# Windows:
venv\Scripts\activate

# Linux/Mac:
source venv/bin/activate
```

### 3. Test Module Imports

```python
python -c "import engine; print('✓ Engine module imported')"
python -c "from engine import Strategy; print('✓ Strategy class imported')"
python -c "import config; print('✓ Config module imported')"
```

### 4. Check Configuration

```bash
# Check if .env file exists
ls -la .env

# Verify API key is set (should show actual key)
grep INFOWAY_API_KEY .env
```

### 5. Test Data Fetching

```bash
python examples/data_fetch_example.py
```

Choose option 1 to fetch market data.

### 6. Test Strategy Examples

```bash
python examples/strategy_example.py
```

Choose option 1 to run strategy backtests.

## Common Issues and Solutions

### Issue: "Module not found: engine"

**Solution:**
```bash
# Make sure you're in the project directory
cd trading-research-system

# Try adding current directory to Python path
export PYTHONPATH="${PYTHONPATH}:."
# Or on Windows:
set PYTHONPATH=%PYTHONPATH%;.
```

### Issue: "No cached data available"

**Solution:**
```bash
# Run the data fetch example first
python examples/data_fetch_example.py
```

### Issue: "INFOWAY_API_KEY not set"

**Solution:**
```bash
# Copy example env file
cp .env.example .env

# Edit .env and add your API key
# INFOWAY_API_KEY=your_actual_api_key_here
```

### Issue: "Rate limit exceeded"

**Solution:**
- Reduce `INFOWAY_MAX_RPS` in `.env` file
- Wait a few minutes before retrying
- Consider upgrading your Infoway plan

### Issue: Import errors for backtesting

**Solution:**
The backtesting library is required but not included in requirements.txt.
You need to install it separately or ensure it's available in your Python path.

```bash
# If you have the backtesting package
pip install backtesting

# Or if it's in the parent repository
export PYTHONPATH="${PYTHONPATH}:../backtesting.py-master"
```

## Advanced Verification

### Test Individual Components

#### Test Strategy Creation

```python
from engine import Strategy, IndicatorSpec, RuleCond, RuleSet, BacktestParams

strategy = Strategy(
    id="test",
    name="Test",
    mode="INTRADAY",
    indicators=[IndicatorSpec(id="ema", type="EMA", period=9)],
    ruleSet=RuleSet(),
    backtestParams=BacktestParams()
)

print(f"✓ Strategy created: {strategy.name}")
```

#### Test Data Module

```python
from engine.data import get_cache_info, TIMEFRAMES

info = get_cache_info()
print(f"✓ Cache directory: {info['cache_dir']}")
print(f"✓ Timeframes: {TIMEFRAMES}")
```

#### Test Infoway Integration

```python
from tools.infoway_forex_fetcher import InfowayForexFetcher

fetcher = InfowayForexFetcher()
tick = fetcher.get_tick("XAUUSD")

if tick:
    print(f"✓ Gold price: ${tick['mid']:.2f}")
else:
    print("✗ Failed to fetch tick data")

fetcher.close()
```

## Performance Verification

### Test Backtesting Speed

```python
import asyncio
from engine import backtest_strategy, Strategy, IndicatorSpec, RuleCond, RuleSet, BacktestParams

strategy = Strategy(
    id="perf_test",
    name="Performance Test",
    mode="INTRADAY",
    indicators=[
        IndicatorSpec(id="ema1", type="EMA", period=9),
        IndicatorSpec(id="ema2", type="EMA", period=21),
    ],
    ruleSet=RuleSet(
        entryLong=[RuleCond(op="crossOver", left="ema1", right="ema2")],
    ),
    backtestParams=BacktestParams()
)

import time
start = time.time()
result = asyncio.run(backtest_strategy(strategy, "XAUUSD"))
elapsed = time.time() - start

print(f"✓ Backtest completed in {elapsed:.2f} seconds")
print(f"  Win Rate: {result['stats']['winRate']:.2f}%")
```

## System Requirements Check

### Minimum Requirements

- **Python**: 3.9+
- **Memory**: 4GB RAM
- **Disk**: 500MB free space
- **Network**: Internet connection for data fetching

### Recommended Requirements

- **Python**: 3.10+
- **Memory**: 8GB RAM
- **Disk**: 2GB free space
- **Network**: Stable internet connection

## Next Steps After Verification

Once all tests pass:

1. **Configure your API keys** in `.env` file
2. **Fetch historical data** for your preferred instruments
3. **Study the example strategies** in `examples/` directory
4. **Create your own strategies** using the DSL
5. **Run backtests** to validate your strategies
6. **Optimize parameters** based on results

## Getting Help

If you encounter issues:

1. Check the error messages carefully
2. Review this verification guide
3. Consult the main README.md
4. Check example scripts for reference
5. Enable debug logging: `LOG_LEVEL=DEBUG python your_script.py`

## Success Criteria

Your installation is successful when:

- ✓ All automated tests pass
- ✓ You can import all modules without errors
- ✓ You can create and validate strategies
- ✓ You can fetch market data (with API key)
- ✓ You can run backtests on cached data
- ✓ Configuration is properly loaded

---

**Ready to start trading research! 🚀**
