"""계정 설정 불러오기.

accounts/<id>.json 하나가 한 계정의 전부입니다(주제·말투·요일 시리즈·검수 규칙·납품 폴더·일정).
accounts/_defaults.json 의 값 위에 계정 파일 값을 덮어씁니다(사전은 한 단계 깊이까지 합침).
"""
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACCOUNTS = ROOT / "accounts"
KST = timezone(timedelta(hours=9))
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
REQUIRED = ["account_id", "handle", "brand", "persona", "audience", "tone", "series_by_weekday",
            "rule_presets", "disclaimer", "delivery"]


def _merge(base, over):
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def list_ids():
    return sorted(p.stem for p in ACCOUNTS.glob("*.json") if not p.stem.startswith("_"))


def load(account_id):
    f = ACCOUNTS / f"{account_id}.json"
    if not f.exists():
        raise SystemExit(f"계정 설정이 없습니다: {f}\n있는 계정: {', '.join(list_ids()) or '없음'}")
    defaults = json.loads((ACCOUNTS / "_defaults.json").read_text(encoding="utf-8"))
    cfg = _merge(defaults, json.loads(f.read_text(encoding="utf-8")))
    missing = [k for k in REQUIRED if not cfg.get(k)]
    if missing:
        raise SystemExit(f"{f.name} 에 필수 항목이 비었습니다: {', '.join(missing)}")
    if cfg["account_id"] != account_id:
        raise SystemExit(f"{f.name} 의 account_id 가 파일 이름과 다릅니다.")
    return cfg


def new(account_id):
    """_template.json 을 복사해 새 계정 파일을 만듭니다."""
    dst = ACCOUNTS / f"{account_id}.json"
    if dst.exists():
        raise SystemExit(f"이미 있습니다: {dst}")
    data = json.loads((ACCOUNTS / "_template.json").read_text(encoding="utf-8"))
    data["account_id"] = account_id
    dst.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dst


def today(now=None):
    return (now or datetime.now(KST)).astimezone(KST)


def plan(cfg, now=None):
    """오늘(KST) 이 계정이 할 일. 쉬는 날이면 series 가 None."""
    d = today(now)
    key = WEEKDAYS[d.weekday()]
    s = cfg["series_by_weekday"].get(key)
    return {"date": d.strftime("%Y-%m-%d"), "weekday": key, "series": s}
