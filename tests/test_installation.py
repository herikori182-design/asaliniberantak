#!/usr/bin/env python3
"""
Installation Verification Tests
==============================

This script verifies that the trading research system is properly installed
and configured.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))


def test_imports():
    """Test that all required modules can be imported"""
    print("Testing module imports...")

    try:
        import engine
        print("  ✓ engine module")
    except ImportError as e:
        print(f"  ✗ engine module: {e}")
        return False

    try:
        from engine import (
            backtest_strategy,
            Strategy,
            IndicatorSpec,
            RuleCond,
            RuleSet,
            BacktestParams,
            InfoWayManager,
            ConfigService,
        )
        print("  ✓ Core engine components")
    except ImportError as e:
        print(f"  ✗ Core engine components: {e}")
        return False

    try:
        from engine import data
        print("  ✓ Data module")
    except ImportError as e:
        print(f"  ✗ Data module: {e}")
        return False

    try:
        import config
        print("  ✓ Config module")
    except ImportError as e:
        print(f"  ✗ Config module: {e}")
        return False

    return True


def test_strategy_creation():
    """Test that we can create a simple strategy"""
    print("\nTesting strategy creation...")

    try:
        from engine import Strategy, IndicatorSpec, RuleCond, RuleSet, BacktestParams

        strategy = Strategy(
            id="test_strategy",
            name="Test Strategy",
            mode="INTRADAY",
            preferredTimeframe="1h",
            indicators=[
                IndicatorSpec(id="ema1", type="EMA", period=9),
                IndicatorSpec(id="ema2", type="EMA", period=21),
            ],
            ruleSet=RuleSet(
                entryLong=[RuleCond(op="crossOver", left="ema1", right="ema2")],
                entryShort=[RuleCond(op="crossUnder", left="ema1", right="ema2")],
            ),
            backtestParams=BacktestParams(allowShort=True),
        )

        print(f"  ✓ Created strategy: {strategy.name}")
        print(f"    ID: {strategy.id}")
        print(f"    Mode: {strategy.mode}")
        print(f"    Timeframe: {strategy.preferredTimeframe}")
        print(f"    Indicators: {len(strategy.indicators)}")

        return True

    except Exception as e:
        print(f"  ✗ Strategy creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_configuration():
    """Test configuration loading"""
    print("\nTesting configuration...")

    try:
        from config import load_config, Config

        config = Config()
        print(f"  ✓ Configuration loaded")
        print(f"    Project root: {config.PROJECT_ROOT}")
        print(f"    Cache directory: {config.CACHE_DIR}")
        print(f"    Log level: {config.LOG_LEVEL}")

        # Check for API keys
        has_api_key = bool(config.INFOWAY_API_KEY or config.INFOWAY_COMMON_API_KEY)
        if has_api_key:
            print(f"  ✓ Infoway API key configured")
        else:
            print(f"  ⚠ Infoway API key not configured (set in .env)")

        return True

    except Exception as e:
        print(f"  ✗ Configuration test failed: {e}")
        return False


def test_data_module():
    """Test data module functionality"""
    print("\nTesting data module...")

    try:
        from engine import data
        from engine.data import get_cache_info, TIMEFRAMES

        print(f"  ✓ Data module imported")
        print(f"    Supported timeframes: {', '.join(TIMEFRAMES)}")

        # Check cache info
        cache_info = get_cache_info()
        print(f"    Cache directory: {cache_info['cache_dir']}")
        print(f"    Cached files: {cache_info['total_files']}")

        return True

    except Exception as e:
        print(f"  ✗ Data module test failed: {e}")
        return False


def test_infoway_fetcher():
    """Test Infoway fetcher (requires API key)"""
    print("\nTesting Infoway fetcher...")

    try:
        from tools.infoway_forex_fetcher import InfowayForexFetcher

        fetcher = InfowayForexFetcher()

        if not fetcher.api_key:
            print("  ⚠ Skipping Infoway test (no API key configured)")
            fetcher.close()
            return True

        print(f"  ✓ Infoway fetcher initialized")
        print(f"    API key configured: {'*' * (len(fetcher.api_key) - 4)}{fetcher.api_key[-4:]}")

        # Test symbol mapping
        test_symbol = "XAUUSD"
        mapped = fetcher._get_infoway_symbol(test_symbol)
        print(f"    Symbol mapping: {test_symbol} -> {mapped}")

        fetcher.close()
        return True

    except Exception as e:
        print(f"  ✗ Infoway fetcher test failed: {e}")
        return False


def test_directory_structure():
    """Test that required directories exist"""
    print("\nTesting directory structure...")

    required_dirs = [
        project_root / "engine",
        project_root / "tools",
        project_root / "examples",
        project_root / "config",
        project_root / "tests",
    ]

    all_exist = True
    for directory in required_dirs:
        if directory.exists():
            print(f"  ✓ {directory.name}/")
        else:
            print(f"  ✗ {directory.name}/ (missing)")
            all_exist = False

    return all_exist


def run_all_tests():
    """Run all verification tests"""
    print("=" * 60)
    print("Trading Research System - Installation Verification")
    print("=" * 60)
    print()

    tests = [
        ("Directory Structure", test_directory_structure),
        ("Module Imports", test_imports),
        ("Strategy Creation", test_strategy_creation),
        ("Configuration", test_configuration),
        ("Data Module", test_data_module),
        ("Infoway Fetcher", test_infoway_fetcher),
    ]

    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"\n  ✗ {test_name} crashed: {e}")
            import traceback
            traceback.print_exc()
            results[test_name] = False

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for result in results.values() if result)
    total = len(results)

    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {test_name}")

    print()
    print(f"Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n✓ All tests passed! Installation is complete.")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed. Please check the errors above.")
        return 1


def main():
    """Main entry point"""
    try:
        return run_all_tests()
    except KeyboardInterrupt:
        print("\n\nTests cancelled by user.")
        return 1
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
