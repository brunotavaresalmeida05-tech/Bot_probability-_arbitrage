"""
live_state_writer.py
Writes bot state to data/live_state.json for Flask dashboard consumption.
"""
import json
import os
from datetime import datetime
from typing import Any


class LiveStateWriter:
    def __init__(self, path: str = "data/live_state.json"):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def _serialize(self, obj: Any) -> Any:
        """Convert MT5 named tuples and other non-serializable objects."""
        if hasattr(obj, '_asdict'):
            return self._serialize(obj._asdict())
        if isinstance(obj, dict):
            return {k: self._serialize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._serialize(i) for i in obj]
        if hasattr(obj, '__dict__'):
            return self._serialize(vars(obj))
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)

    def update(self, account: dict, positions: list, signals: list,
               spreads: dict, prices: dict):
        """Write current bot state to live_state.json."""
        serialized_positions = []
        for pos in (positions or []):
            if hasattr(pos, '_asdict'):
                p = pos._asdict()
            elif hasattr(pos, '__dict__'):
                p = vars(pos)
            elif isinstance(pos, dict):
                p = pos
            else:
                continue
            serialized_positions.append({
                'ticket':        p.get('ticket', 0),
                'symbol':        p.get('symbol', ''),
                'type':          'BUY' if p.get('type') == 0 else 'SELL',
                'volume':        p.get('volume', 0),
                'price_open':    round(float(p.get('price_open', 0)), 6),
                'price_current': round(float(p.get('price_current', 0)), 6),
                'profit':        round(float(p.get('profit', 0)), 2),
                'swap':          round(float(p.get('swap', 0)), 2),
                'sl':            p.get('sl', 0),
                'tp':            p.get('tp', 0),
                'time':          p.get('time', 0),
                'comment':       p.get('comment', ''),
            })

        balance = float(account.get('balance', 0)) if isinstance(account, dict) else 0.0
        equity  = float(account.get('equity', balance)) if isinstance(account, dict) else balance

        state = {
            'timestamp': datetime.now().isoformat(),
            'account': {
                'balance':      round(balance, 2),
                'equity':       round(equity, 2),
                'margin':       round(float(account.get('margin', 0) if isinstance(account, dict) else 0), 2),
                'free_margin':  round(float(account.get('margin_free', 0) if isinstance(account, dict) else 0), 2),
                'margin_level': round(float(account.get('margin_level', 0) if isinstance(account, dict) else 0), 2),
                'profit':       round(float(account.get('profit', 0) if isinstance(account, dict) else 0), 2),
                'currency':     account.get('currency', 'EUR') if isinstance(account, dict) else 'EUR',
            },
            'positions': serialized_positions,
            'signals':   self._serialize(signals) if signals else [],
            'spreads':   {k: round(float(v), 1) for k, v in (spreads or {}).items()},
            'prices':    {k: float(v) for k, v in (prices or {}).items()},
        }

        try:
            tmp = self.path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, default=str)
            os.replace(tmp, self.path)
        except Exception as e:
            print(f"[LiveStateWriter] Error writing state: {e}")
