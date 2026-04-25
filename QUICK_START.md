# Quick Start Guide

Get started with the Trading Research System in 5 minutes!

## Prerequisites

- Python 3.9 or higher
- Infoway API key ([get free tier here](https://infoway.io/))
- 500MB free disk space

## Installation (2 minutes)

### 1. Download and Extract

Extract the `trading-research-system` folder to your desired location.

### 2. Run Setup Script

```bash
cd trading-research-system
python setup.py
```

The setup script will:
- Create virtual environment
- Install dependencies
- Set up configuration files
- Create necessary directories
- Verify installation

### 3. Configure API Key

Edit the `.env` file and add your Infoway API key:

```bash
INFOWAY_API_KEY=your_actual_api_key_here
```

## First Steps (3 minutes)

### Step 1: Verify Installation

```bash
python tests/test_installation.py
```

You should see all tests pass.

### Step 2: Fetch Market Data

```bash
python examples/data_fetch_example.py
```

Choose option 1 to fetch data for major forex pairs and metals.

### Step 3: Run Strategy Examples

```bash
python examples/strategy_example.py
```

Choose option 1 to see backtest results for example strategies.

## Create Your First Strategy

Create a file `my_strategy.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

import asyncio
from engine import Strategy, IndicatorSpec, RuleCond, RuleSet, BacktestParams, backtest_strategy

# Define your strategy
my_strategy = Strategy(
    id="my_first_strategy",
    name="My First Strategy",
    mode="INTRADAY",
    preferredTimeframe="1h",
    description="Simple EMA crossover with RSI filter",
    indicators=[
        IndicatorSpec(id="fast_ema", type="EMA", period=9),
        IndicatorSpec(id="slow_ema", type="EMA", period=21),
        IndicatorSpec(id="rsi", type="RSI", period=14),
    ],
    ruleSet=RuleSet(
        entryLong=[
            RuleCond(op="crossOver", left="fast_ema", right="slow_ema"),
            RuleCond(op="gt", left="rsi", right=50),
        ],
        entryShort=[
            RuleCond(op="crossUnder", left="fast_ema", right="slow_ema"),
            RuleCond(op="lt", left="rsi", right=50),
        ],
    ),
    backtestParams=BacktestParams(
        allowShort=True,
        atrStopMult=1.5,
        atrTakeMult=2.0,
    )
)

# Run backtest
async def main():
    print("Testing my strategy on XAUUSD...")
    result = await backtest_strategy(my_strategy, "XAUUSD")

    stats = result['stats']
    print(f"\nResults:")
    print(f"  Win Rate: {stats['winRate']:.2f}%")
    print(f"  Total Trades: {stats['totalTrades']}")
    print(f"  Net Profit: ${stats['netProfit']:.2f}")
    print(f"  Return: {stats['returnPct']:.2f}%")

    if stats['longTrades'] > 0:
        print(f"  Long Win Rate: {stats['longWinRate']:.2f}%")
    if stats['shortTrades'] > 0:
        print(f"  Short Win Rate: {stats['shortWinRate']:.2f}%")

if __name__ == "__main__":
    asyncio.run(main())
```

Run your strategy:

```bash
python my_strategy.py
```

## What's Next?

### Learn More Strategies

Study the example strategies in `examples/strategy_example.py`:
- MA Crossover Strategy
- RSI Divergence Strategy
- Fibonacci Retracement Strategy

### Explore Indicators

Available indicators:
- **Trend**: SMA, EMA, MACD, ADX
- **Momentum**: RSI, STOCH, CCI
- **Volatility**: BOLL, ATR, ENV
- **Levels**: FIB, PSAR

### Test Different Markets

```python
# Forex
await backtest_strategy(strategy, "EURUSD")
await backtest_strategy(strategy, "GBPUSD")

# Metals
await backtest_strategy(strategy, "XAUUSD")  # Gold
await backtest_strategy(strategy, "XAGUSD")  # Silver

# Crypto (if Binance data available)
await backtest_strategy(strategy, "BTCUSDT")
```

## Common Tasks

### Update Market Data

```bash
python examples/data_fetch_example.py
# Choose option 1
```

### Clear Cache

```python
from engine.data import clear_cache
clear_cache()  # Clear all cached data
```

### Check Cache Status

```python
from engine.data import get_cache_info
info = get_cache_info()
print(f"Symbols: {info['symbols']}")
print(f"Timeframes: {info['timeframes']}")
```

### Save Strategy to JSON

```python
# Save your strategy
import json
strategy_json = my_strategy.model_dump_json(indent=2)
with open('my_strategy.json', 'w') as f:
    f.write(strategy_json)
```

## Tips for Success

1. **Start Simple**: Begin with basic strategies before adding complexity
2. **Test Thoroughly**: Always backtest on multiple timeframes and symbols
3. **Manage Risk**: Use appropriate stop-loss and take-profit settings
4. **Validate Data**: Ensure your cached data is complete and accurate
5. **Keep Logs**: Enable logging to track strategy performance

## Troubleshooting

**Problem**: "No cached data available"
```bash
# Solution: Fetch data first
python examples/data_fetch_example.py
```

**Problem**: "API key not set"
```bash
# Solution: Edit .env file
INFOWAY_API_KEY=your_actual_key_here
```

**Problem**: Import errors
```bash
# Solution: Make sure you're in the project directory
cd trading-research-system
# And virtual environment is activated
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows
```

## Resources

- **Main Documentation**: See `README.md`
- **Installation Guide**: See `VERIFY_INSTALLATION.md`
- **Example Scripts**: Check `examples/` directory
- **Configuration**: Edit `.env` file

## Support

For issues or questions:
1. Check the error messages
2. Review documentation files
3. Study example code
4. Enable debug logging: `LOG_LEVEL=DEBUG`

---

**Happy Trading! 📈**
