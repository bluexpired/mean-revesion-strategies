import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def dt(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def config():
    cfg = read_json(ROOT / "config.json")
    risk = cfg["risk"]
    for name in ("stop_pct", "take_profit_pct", "max_position_fraction", "account_risk_per_trade"):
        if not 0 < risk[name] < 1:
            raise ValueError("Risk fraction must be between 0 and 1: " + name)
    if risk["max_positions"] < 1 or risk["one_way_cost_bps"] < 0:
        raise ValueError("Invalid risk configuration")
    for weights in cfg["weights"].values():
        if min(weights.values()) < 0 or not math.isclose(sum(weights.values()), 1):
            raise ValueError("Weights must be nonnegative and sum to 1")
    return cfg


def load_env():
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def clip(value, low=-1.0, high=1.0):
    return max(low, min(high, value))
