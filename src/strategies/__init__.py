"""
Strategies package
"""

from .pairs_trading import PairsTrading
from .trend_following import TrendFollowing
from .breakout import Breakout
from .volatility_arbitrage import VolatilityArbitrage
from .news_trading import NewsTrading

__all__ = [
    'PairsTrading',
    'TrendFollowing',
    'Breakout',
    'VolatilityArbitrage',
    'NewsTrading'
]
