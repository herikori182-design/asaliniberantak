import json
from dataclasses import dataclass, field, asdict, fields
from typing import List, Literal, Optional, Dict, Any, Union

IndicatorType = Literal['SMA', 'EMA', 'ATR', 'RSI', 'BOLL', 'PSAR', 'STOCH', 'CCI', 'FIB', 'ADX', 'ENV', 'MACD']
OpType = Literal[
    'gt', 'lt', 'gte', 'lte', 'between',
    'crossOver', 'crossUnder',
    'touchUpperBand', 'touchLowerBand',
    'fibAtOrAbove', 'fibAtOrBelow',
    'pattern', 'chartPattern',
    'all', 'any'
]

def filter_dict(cls, d: Dict[str, Any]) -> Dict[str, Any]:
    """Filter dict keys to match dataclass fields."""
    if not isinstance(d, dict):
        return {}
    valid_fields = {f.name for f in fields(cls)}
    return {k: v for k, v in d.items() if k in valid_fields}

@dataclass
class IndicatorSpec:
    id: str
    type: IndicatorType
    period: Optional[int] = None
    period2: Optional[int] = None
    periodFast: Optional[int] = None
    periodSlow: Optional[int] = None
    stdDev: Optional[float] = None
    step: Optional[float] = None
    max: Optional[float] = None
    lookback: Optional[int] = None
    percent: Optional[float] = None
    maType: Optional[Literal['SMA', 'EMA']] = None

@dataclass
class RuleCond:
    op: OpType
    left: Optional[str] = None
    right: Optional[Union[str, float, int]] = None
    min: Optional[float] = None
    max: Optional[float] = None
    id: Optional[str] = None
    level: Optional[str] = None
    of: Optional[List['RuleCond']] = None
    type: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'RuleCond':
        # Clean dict
        d_clean = filter_dict(cls, d)

        # Handle nested recursive list
        if 'of' in d and d['of'] and isinstance(d['of'], list):
            # Recursively clean children, ignoring non-dict items
            d_clean['of'] = [cls.from_dict(x) for x in d['of'] if isinstance(x, dict)]

        return cls(**d_clean)

@dataclass
class RuleSet:
    entryLong: Optional[List[RuleCond]] = None
    entryShort: Optional[List[RuleCond]] = None
    exitLong: Optional[List[RuleCond]] = None
    exitShort: Optional[List[RuleCond]] = None
    confirmLong: Optional[List[RuleCond]] = None
    confirmShort: Optional[List[RuleCond]] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'RuleSet':
        d_clean = filter_dict(cls, d)
        for k in ['entryLong', 'entryShort', 'exitLong', 'exitShort', 'confirmLong', 'confirmShort']:
            if k in d and d[k] and isinstance(d[k], list):
                d_clean[k] = [RuleCond.from_dict(x) for x in d[k] if isinstance(x, dict)]
        return cls(**d_clean)

@dataclass
class BacktestParams:
    fast: int = 9
    slow: int = 20
    maType: Literal['SMA', 'EMA'] = 'EMA'
    allowShort: bool = True
    atrStopMult: float = 1.5
    atrTakeMult: float = 2.0
    minRsi: float = 30.0
    maxRsi: float = 70.0
    trendFilter: bool = True

@dataclass
class Strategy:
    id: str
    name: str
    mode: Literal['SCALPING', 'INTRADAY']
    indicators: List[IndicatorSpec]
    ruleSet: RuleSet
    backtestParams: BacktestParams
    description: Optional[str] = None
    notes: Optional[str] = None
    preferredTimeframe: Optional[str] = None
    analysisTimeframe: Optional[str] = None
    confirmTimeframe: Optional[str] = None
    confirmWindowBars: Optional[int] = None
    confirmRuleSet: Optional[RuleSet] = None
    entryType: Optional[Literal['Breakout', 'Pullback']] = None
    psychology: Optional[Dict[str, Any]] = None
    checklist: Optional[List[str]] = None
    optimizationParamMap: Optional[Dict[str, str]] = None

    @classmethod
    def model_validate_json(cls, json_str: str) -> 'Strategy':
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Strategy':
        # Clean main dict
        d_clean = filter_dict(cls, data)

        if 'indicators' in data and isinstance(data['indicators'], list):
            d_clean['indicators'] = [IndicatorSpec(**filter_dict(IndicatorSpec, x)) for x in data['indicators'] if isinstance(x, dict)]

        if 'ruleSet' in data and isinstance(data['ruleSet'], dict):
            d_clean['ruleSet'] = RuleSet.from_dict(data['ruleSet'])
        if 'confirmRuleSet' in data and isinstance(data['confirmRuleSet'], dict):
            d_clean['confirmRuleSet'] = RuleSet.from_dict(data['confirmRuleSet'])

        if 'backtestParams' in data and isinstance(data['backtestParams'], dict):
            d_clean['backtestParams'] = BacktestParams(**filter_dict(BacktestParams, data['backtestParams']))

        return cls(**d_clean)

    def model_dump_json(self, indent=None) -> str:
        return json.dumps(asdict(self), indent=indent)

# Helper to verify validation
def validate_strategy_schema(data: Dict[str, Any]):
    # Basic check
    required = ['id', 'name', 'mode', 'indicators', 'ruleSet', 'backtestParams']
    for r in required:
        if r not in data:
            raise ValueError(f"Missing field: {r}")
    if data['mode'] not in ['SCALPING', 'INTRADAY']:
        raise ValueError("Mode must be SCALPING or INTRADAY")
