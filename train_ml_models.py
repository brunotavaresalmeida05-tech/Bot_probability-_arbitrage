"""
train_ml_models.py
Trains a RandomForest ML predictor per symbol using 90 days of MT5 OHLCV data.

Usage:
    python train_ml_models.py
    python train_ml_models.py --symbols EURUSD AUDUSD --days 90

Models saved to: data/models/{symbol}_ml.pkl
"""

import argparse
import os
import sys
import time
from datetime import datetime

# ── Path setup ─────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

import config.settings as cfg
import src.mt5_connector as mt5c
from src.ml.price_predictor import PricePredictor


# ── Label generation ───────────────────────────────────────

LABEL_HORIZON = 5     # Look N bars ahead to decide label
LABEL_THRESH  = 0.0003  # 3 pips movement threshold (0.03%)


def label_bars(df):
    """
    Assigns labels to each bar based on future price movement.
      1  = price UP by >= LABEL_THRESH in next LABEL_HORIZON bars
     -1  = price DOWN by >= LABEL_THRESH
      0  = neutral / range-bound
    """
    labels = []
    closes = df['close'].values
    for i in range(len(closes) - LABEL_HORIZON):
        future = closes[i + LABEL_HORIZON]
        current = closes[i]
        if current == 0:
            labels.append(0)
            continue
        ret = (future - current) / current
        if ret >= LABEL_THRESH:
            labels.append(1)
        elif ret <= -LABEL_THRESH:
            labels.append(-1)
        else:
            labels.append(0)
    return labels


# ── Training ───────────────────────────────────────────────

def train_symbol(symbol: str, lookback_bars: int = 2000) -> dict:
    """Train ML predictor for one symbol. Returns result dict."""
    print(f"\n[{symbol}] Fetching {lookback_bars} bars...")

    df = mt5c.get_bars(symbol, cfg.TIMEFRAME, lookback_bars)
    if df is None or len(df) < 200:
        return {'symbol': symbol, 'error': f'Insufficient data ({0 if df is None else len(df)} bars)'}

    # Add ATR column needed by engineer_features
    import pandas as pd
    import numpy as np
    h, l, c = df['high'], df['low'], df['close']
    prev_c = c.shift(1)
    tr = pd.concat([h - l, (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    df = df.copy()
    df['atr'] = tr.rolling(cfg.ATR_PERIOD).mean()

    print(f"[{symbol}] Labelling {len(df)} bars (horizon={LABEL_HORIZON}, thresh={LABEL_THRESH:.4%})...")
    labels = label_bars(df)

    # Build training set: pairs (df_slice, label)
    model_path = f'data/models/{symbol.lower()}_ml.pkl'
    os.makedirs('data/models', exist_ok=True)
    predictor = PricePredictor(model_path=model_path)

    historical_data = []
    min_rows = 60  # minimum rows needed for feature engineering
    for i, label in enumerate(labels):
        idx = i + LABEL_HORIZON  # current bar index
        if idx < min_rows:
            continue
        df_slice = df.iloc[idx - min_rows: idx].copy()
        historical_data.append({'df': df_slice, 'label': label})

    print(f"[{symbol}] Training on {len(historical_data)} samples "
          f"(+1:{labels.count(1)}, -1:{labels.count(-1)}, 0:{labels.count(0)})...")

    result = predictor.train(historical_data)
    result['symbol'] = symbol
    result['model_path'] = model_path

    if 'error' not in result:
        print(f"[{symbol}] Accuracy: {result['accuracy']:.1%} | "
              f"Samples: {result['n_samples']} | Saved: {model_path}")
        try:
            imp = predictor.get_feature_importance()
            top3 = list(imp.items())[:3]
            print(f"[{symbol}] Top features: {top3}")
        except Exception:
            pass
    else:
        print(f"[{symbol}] ERROR: {result['error']}")

    return result


# ── Main ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Train ML price predictors')
    parser.add_argument('--symbols', nargs='+',
                        default=getattr(cfg, 'ACTIVE_SYMBOLS', cfg.SYMBOLS[:5]))
    parser.add_argument('--days', type=int, default=90,
                        help='Lookback days (default 90)')
    args = parser.parse_args()

    # Connect to MT5
    print("Connecting to MT5...")
    if not mt5c.connect():
        print("ERROR: Cannot connect to MT5. Is MetaTrader 5 running?")
        sys.exit(1)

    # M5 bars per day ≈ 288
    bars_per_day = 288
    lookback_bars = args.days * bars_per_day
    print(f"\nTraining for {len(args.symbols)} symbols | {args.days} days | ~{lookback_bars} bars each")
    print("=" * 60)

    results = []
    for symbol in args.symbols:
        try:
            result = train_symbol(symbol, lookback_bars)
            results.append(result)
        except Exception as e:
            print(f"[{symbol}] EXCEPTION: {e}")
            results.append({'symbol': symbol, 'error': str(e)})
        time.sleep(0.5)  # rate-limit MT5 requests

    mt5c.disconnect()

    # Summary
    print("\n" + "=" * 60)
    print("TRAINING SUMMARY")
    print("=" * 60)
    ok = [r for r in results if 'error' not in r]
    fail = [r for r in results if 'error' in r]
    for r in ok:
        print(f"  OK  {r['symbol']:8s} accuracy={r['accuracy']:.1%}  samples={r['n_samples']}")
    for r in fail:
        print(f"  ERR {r['symbol']:8s} {r['error']}")
    print(f"\nTrained: {len(ok)}/{len(results)} models")
    print(f"Models saved in: data/models/")


if __name__ == '__main__':
    main()
