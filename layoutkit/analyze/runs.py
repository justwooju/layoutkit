"""수집 실행 기록 요약 — 날짜별 결과·실패 이유·실행 시간·맞춤(hover)·미세조정(servo).

이유(성공 아닌 실행만): 이유 조각(" | " 로 나눈 것) → 글 종류 text(괄호 밖 ' — '·': ' 앞만, 숫자는 #) → 이유 code(RULES 의 첫 맞는 것,
없으면 other). code 는 report/i18n.py REASON 의 키: fixture_moved · fixture_lifted · object_not_seen · goal_state_unknown ·
not_recorded · aborted · other. 원문 글은 데이터라 그대로 둔다(texts·example).
"""
from __future__ import annotations

import re

import numpy as np

NUM = re.compile(r"(?<![A-Za-z])[+-]?\d+(?:\.\d+)?(?![A-Za-z])")
RULES = [                                                           # (정규식, 이유 code) — fr5auto 판정 글 기준, 위에서부터
    (re.compile(r"뺄 때 받침이 같이 들렸|lifted", re.I), "fixture_lifted"),
    (re.compile(r"받침이 (움직였|조금 밀렸)|칸 자리가 .*밀렸|fixture moved|rack moved", re.I), "fixture_moved"),
    (re.compile(r"안 보인다|떨어뜨렸|not seen|dropped", re.I), "object_not_seen"),
    (re.compile(r"꽂을 칸 상태|넣을 칸 상태|goal state", re.I), "goal_state_unknown"),
    (re.compile(r"기록 시작 실패|record(ing)? (start )?fail", re.I), "not_recorded"),
    (re.compile(r"따라오지 않|중단|abort", re.I), "aborted"),
]
VERDICTS = ("success", "fail", "unsure")


def _cut(s: str, sep: str) -> str:
    """괄호 밖에서 처음 나온 sep 앞까지."""
    depth = 0
    for i, ch in enumerate(s):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        elif depth == 0 and s.startswith(sep, i):
            return s[:i]
    return s


def reason_text(part: str) -> str:
    """이유 조각 → 글 종류(숫자 #)."""
    return NUM.sub("#", _cut(_cut(str(part), " — "), ": ")).strip()


def reason_code(part: str) -> str:
    """이유 조각 → 이유 code(RULES)."""
    for rx, code in RULES:
        if rx.search(str(part)):
            return code
    return "other"


def _stats(v):
    v = np.asarray([x for x in v if x is not None], float)
    if len(v) == 0:
        return None
    return {"n": int(len(v)), "median": round(float(np.median(v)), 2), "mean": round(float(v.mean()), 2),
            "p10": round(float(np.percentile(v, 10)), 2), "p90": round(float(np.percentile(v, 90)), 2),
            "min": round(float(v.min()), 2), "max": round(float(v.max()), 2)}


def summarize(runs) -> dict | None:
    rows = list(runs or [])
    if not rows:
        return None
    by_v, kept, dec = {}, {}, {}
    for r in rows:
        v = r.get("verdict") or "none"
        by_v[v] = by_v.get(v, 0) + 1
        k = r.get("kept") or "none"
        kept[k] = kept.get(k, 0) + 1
        d = r.get("decided_by") or "none"
        dec[d] = dec.get(d, 0) + 1
    days = {}
    for r in rows:
        day = (r.get("t") or "")[:10] or "unknown"
        D = days.setdefault(day, {"day": day, "n": 0, "success": 0, "fail": 0, "unsure": 0, "other": 0, "kept": 0, "exec_s": []})
        D["n"] += 1
        v = r.get("verdict")
        D[v if v in VERDICTS else "other"] += 1
        D["kept"] += 1 if r.get("kept") == "success" else 0
        if r.get("exec_s") is not None:
            D["exec_s"].append(r["exec_s"])
    by_day = []
    for day in sorted(days):
        D = days[day]
        D["exec_s_median"] = round(float(np.median(D["exec_s"])), 2) if D["exec_s"] else None
        D.pop("exec_s")
        by_day.append(D)
    reasons = {}
    for r in rows:
        if r.get("verdict") == "success":
            continue                                                 # 실패·불확실·기록 안 함의 이유만
        seen = set()
        parts = r.get("reasons") or ([] if r.get("verdict") in ("success",) else ["(no reason)"])
        for part in parts:
            c = reason_code(part)
            tx = reason_text(part)
            R = reasons.setdefault(c, {"code": c, "n": 0, "by_verdict": {}, "texts": {}, "example": part[:200]})
            R["texts"][tx] = R["texts"].get(tx, 0) + 1
            if c in seen:                                            # 실행 한 번은 code 마다 한 번만 센다
                continue
            seen.add(c)
            R["n"] += 1
            v = r.get("verdict") or "none"
            R["by_verdict"][v] = R["by_verdict"].get(v, 0) + 1
    for R in reasons.values():
        R["texts"] = [{"text": k, "n": v} for k, v in sorted(R["texts"].items(), key=lambda x: (-x[1], x[0]))]
    dur = {"all": _stats([r.get("exec_s") for r in rows])}
    for v in VERDICTS:
        s = _stats([r.get("exec_s") for r in rows if r.get("verdict") == v])
        if s:
            dur[v] = s
    hv = [r.get("hover") or {} for r in rows]
    sv = [r.get("servo") or {} for r in rows]
    hover = {"n": sum(1 for h in hv if h.get("shifted") is not None),
             "shifted": sum(1 for h in hv if h.get("shifted")), "too_big": sum(1 for h in hv if h.get("too_big")),
             "abs_off_mm": _stats([abs(h["off_mm"]) for h in hv if h.get("off_mm") is not None])}
    servo = {"n": sum(1 for s in sv if s.get("meas") is not None), "hit_limit": sum(1 for s in sv if s.get("hit_limit")),
             "fixes": _stats([s.get("fixes") for s in sv]), "abs_shift_mm": _stats([abs(s["shift_mm"]) for s in sv if s.get("shift_mm") is not None])}
    n = len(rows)
    return {"n": n, "first": rows[0].get("t"), "last": rows[-1].get("t"), "by_verdict": by_v, "kept": kept, "decided_by": dec,
            "success_rate": round(by_v.get("success", 0) / n, 3), "kept_rate": round(kept.get("success", 0) / n, 3),
            "by_day": by_day, "reasons": sorted(reasons.values(), key=lambda x: (-x["n"], x["code"])),
            "durations": dur, "hover": hover, "servo": servo}
