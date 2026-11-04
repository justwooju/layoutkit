"""fr5auto 수집 실행 기록 → Runs(한 줄 = 실행 한 번).

읽는 것:
  work/runs.jsonl      kind == "run" 줄만(FR5-AutoCollect docs/DATA.md 5.2) — plan·reset 은 녹화가 아니다
  runs_*.csv           열: time, verdict, kept, decided_by, record, exec_s, hover_off_mm, hover_shifted, hover_too_big,
                       servo_meas, servo_fixes, servo_hit_limit, servo_shift_mm, servo_wrist_deg, reason
  폴더                 그 안의 runs.jsonl · work/runs.jsonl · runs_*.csv · data/real/runs_*.csv 를 모두

한 줄 모양:
  {"t": ISO, "verdict": success|fail|unsure|abort|norec|None, "kept": 라벨|None, "decided_by": auto|human|None,
   "record": bool|None, "exec_s": 실행 시간(s)|None, "reason": 원문, "reasons": [" | " 로 나눈 조각],
   "hover": {"off_mm", "shifted", "too_big"}, "servo": {"meas", "fixes", "hit_limit", "shift_mm", "wrist_deg"}, "episode": 번호|None}
"""
from __future__ import annotations

import csv
import json
import math
import time
from pathlib import Path

from . import Runs, display_path


def _f(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _b(v):
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "yes"):
        return True
    if s in ("0", "false", "no"):
        return False
    return None


def _s(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _iso(t):
    if t is None or t == "":
        return None
    f = _f(t)
    if f is not None and f > 1e8:                                    # 유닉스 시각
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(f))
    return str(t)


def split_reason(s) -> list[str]:
    return [p.strip() for p in str(s or "").split(" | ") if p.strip()]


def _row(t, verdict, kept, decided_by, record, exec_s, reason, hover, servo, episode=None, source="csv"):
    return {"t": _iso(t), "verdict": _s(verdict), "kept": _s(kept), "decided_by": _s(decided_by), "record": _b(record),
            "exec_s": _f(exec_s), "reason": str(reason or ""), "reasons": split_reason(reason), "hover": hover, "servo": servo,
            "episode": episode, "source": source}


def read_csv(p: Path) -> list[dict]:
    out = []
    with p.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            r = {(k or "").strip(): v for k, v in r.items()}
            out.append(_row(r.get("time"), r.get("verdict"), r.get("kept"), r.get("decided_by"), r.get("record"), r.get("exec_s"),
                            r.get("reason"),
                            {"off_mm": _f(r.get("hover_off_mm")), "shifted": _b(r.get("hover_shifted")), "too_big": _b(r.get("hover_too_big"))},
                            {"meas": _f(r.get("servo_meas")), "fixes": _f(r.get("servo_fixes")), "hit_limit": _b(r.get("servo_hit_limit")),
                             "shift_mm": _f(r.get("servo_shift_mm")), "wrist_deg": _f(r.get("servo_wrist_deg"))}))
    return out


def read_jsonl(p: Path) -> list[dict]:
    out = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not isinstance(r, dict) or r.get("kind") != "run":
                continue
            why = r.get("verdict_why")
            reason = " | ".join(str(x) for x in why) if isinstance(why, list) and why else (r.get("why") or "")
            hv = r.get("hover") or ((r.get("evidence") or {}).get("hover")) or {}
            sv = r.get("servo") or ((r.get("evidence") or {}).get("servo")) or {}
            hv = hv if isinstance(hv, dict) else {}
            sv = sv if isinstance(sv, dict) else {}
            out.append(_row(r.get("t"), r.get("verdict"), r.get("kept"), r.get("decided_by"), r.get("record"), r.get("T"), reason,
                            {"off_mm": _f(hv.get("off_mm")), "shifted": _b(hv.get("shift")), "too_big": _b(hv.get("too_big"))},
                            {"meas": _f(sv.get("n_meas")), "fixes": _f(sv.get("n_fix")), "hit_limit": _b(sv.get("n_clamp") and sv.get("n_clamp") > 0),
                             "shift_mm": _f(sv.get("shift_mm")), "wrist_deg": _f(sv.get("phi_deg"))},
                            episode=r.get("episode"), source="jsonl"))
    return out


def files_in(p: Path) -> list[Path]:
    if p.is_file():
        return [p]
    out = []
    for q in (p / "runs.jsonl", p / "work" / "runs.jsonl"):
        if q.is_file():
            out.append(q)
    out += sorted(p.glob("runs_*.csv")) + sorted((p / "data" / "real").glob("runs_*.csv"))
    return out


def load(path, name=None, **_) -> Runs:
    """경로(파일·폴더) → Runs(시각 순)."""
    p = Path(path).expanduser()
    rows = []
    fs = files_in(p)
    if not fs:
        raise FileNotFoundError(f"{display_path(p)}: runs.jsonl · runs_*.csv 가 없다")
    for q in fs:
        rows += read_jsonl(q) if q.suffix.lower() == ".jsonl" else read_csv(q)
    rows.sort(key=lambda r: r["t"] or "")
    return Runs(rows, name=name or p.stem, path=display_path(p.resolve()))
