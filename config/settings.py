from pathlib import Path
import os
import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
STATE_DIR = BASE_DIR / "state"
LOG_DIR = BASE_DIR / "logs"

FLAT_DEFAULTS = {
    "mode": "paper",
    "health_port": 8080,
    "dashboard_port": 8501,
    "loop_sleep_sec": 5,
    "symbols": ["EURUSD", "GBPUSD", "BTCUSD"],
    "paper": True,
    "write_state_path": str(STATE_DIR / "state.json"),
    "log_file": str(LOG_DIR / "bot.log"),
    "history_file": str(OUTPUT_DIR / "historical_rankings.csv"),
    "config_file": str(CONFIG_DIR / "settings.yaml"),
    "mt5_enabled": False,
    "live_trading_enabled": False,
    "mt5_path": "",
    "mt5_login": 0,
    "mt5_password": "",
    "mt5_server": "",
    "mt5_timeframe": "M5",
    "market_bars": 100,
    "dry_run": True,
    "kill_switch": True,
    "max_spread": 0.0015,
    "min_cash": 100.0,
    "default_qty": 0.01,
    "max_daily_loss": 0.02,
    "max_positions": 1,
}

NESTED_DEFAULTS = {
    "app": {
        "name": "TradingBot",
        "profile": "paper",
    },
    "mode": {
        "dry_run": True,
        "kill_switch": True,
    },
    "risk": {
        "max_spread": 0.0015,
        "max_daily_loss": 0.02,
        "max_positions": 1,
        "default_qty": 0.01,
        "min_cash": 100.0,
    },
    "market": {
        "mt5_timeframe": "M5",
        "market_bars": 100,
        "symbols": ["EURUSD", "GBPUSD"],
    },
    "paths": {
        "state_file": "state/state.json",
        "history_file": "state/state_history.jsonl",
    },
    "live": {
        "enabled": False,
        "broker": "mt5",
        "account_id": None,
    },
}


def flatten_config(nested):
    flat = {}
    flat["mode"] = "live" if nested.get("live", {}).get("enabled", False) else "paper"
    flat["paper"] = nested.get("mode", {}).get("dry_run", True)
    flat["dry_run"] = nested.get("mode", {}).get("dry_run", True)
    flat["kill_switch"] = nested.get("mode", {}).get("kill_switch", True)
    risk = nested.get("risk", {})
    flat["max_spread"] = risk.get("max_spread", 0.0015)
    flat["max_daily_loss"] = risk.get("max_daily_loss", 0.02)
    flat["max_positions"] = risk.get("max_positions", 1)
    flat["default_qty"] = risk.get("default_qty", 0.01)
    flat["min_cash"] = risk.get("min_cash", 100.0)
    market = nested.get("market", {})
    flat["mt5_timeframe"] = market.get("mt5_timeframe", "M5")
    flat["market_bars"] = market.get("market_bars", 100)
    flat["symbols"] = market.get("symbols", ["EURUSD", "GBPUSD"])
    paths = nested.get("paths", {})
    flat["write_state_path"] = paths.get("state_file", "state/state.json")
    flat["history_file"] = paths.get("history_file", "state/state_history.jsonl")
    flat["live_enabled"] = nested.get("live", {}).get("enabled", False)
    flat["broker"] = nested.get("live", {}).get("broker", "mt5")
    flat["account_id"] = nested.get("live", {}).get("account_id")
    flat["profile"] = nested.get("app", {}).get("profile", "paper")
    return flat


def set_profile(cfg, profile="paper"):
    if profile == "paper":
        cfg["mode"]["dry_run"] = True
        cfg["mode"]["kill_switch"] = True
        cfg["live"]["enabled"] = False
    elif profile == "live_safe":
        cfg["mode"]["dry_run"] = True
        cfg["mode"]["kill_switch"] = False
        cfg["live"]["enabled"] = True
    elif profile == "live":
        cfg["mode"]["dry_run"] = False
        cfg["mode"]["kill_switch"] = False
        cfg["live"]["enabled"] = True
    elif profile == "live_demo":
        cfg["mode"]["dry_run"] = True
        cfg["mode"]["kill_switch"] = True
        cfg["live"]["enabled"] = True
    else:
        raise ValueError(f"Unknown profile: {profile}")
    cfg["app"]["profile"] = profile
    return cfg


def deep_merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_yaml(path):
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def load_config():
    cfg = deep_merge(dict(NESTED_DEFAULTS), load_yaml(CONFIG_DIR / "config.yaml"))

    profile = cfg.get("app", {}).get("profile", "paper")
    cfg = set_profile(cfg, profile)

    flat = flatten_config(cfg)
    for k, v in FLAT_DEFAULTS.items():
        flat.setdefault(k, v)

    flat["config_file"] = str(CONFIG_DIR / "config.yaml")
    flat["log_file"] = str(LOG_DIR / "bot.log")
    flat["write_state_path"] = str(STATE_DIR / Path(flat.get("write_state_path", "state.json")).name)
    flat["history_file"] = str(OUTPUT_DIR / Path(flat.get("history_file", "state_history.jsonl")).name)

    env_overrides = {
        "mode": ("BOT_MODE", str),
        "health_port": ("HEALTH_PORT", int),
        "dashboard_port": ("DASHBOARD_PORT", int),
        "loop_sleep_sec": ("LOOP_SLEEP_SEC", int),
        "mt5_enabled": ("MT5_ENABLED", lambda v: v.lower() in ("1", "true", "yes")),
        "mt5_login": ("MT5_LOGIN", int),
        "mt5_password": ("MT5_PASSWORD", str),
        "mt5_server": ("MT5_SERVER", str),
        "mt5_path": ("MT5_PATH", str),
    }
    for key, (env_var, cast) in env_overrides.items():
        val = os.getenv(env_var)
        if val is not None:
            flat[key] = cast(val)

    env_symbols = os.getenv("SYMBOLS")
    if env_symbols:
        flat["symbols"] = [s.strip() for s in env_symbols.split(",") if s.strip()]

    for p in [DATA_DIR, OUTPUT_DIR, STATE_DIR, LOG_DIR]:
        p.mkdir(parents=True, exist_ok=True)

    return flat
