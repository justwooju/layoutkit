"""표 어댑터 — CSV · JSON · JSONL(에피소드 한 줄). 열 이름 대응은 map 으로, 없으면 흔한 이름으로 짐작한다.

map 키(값 = 열 이름):
  id · t · outcome · weight
  start.x · start.y · start.yaw · start.z · goal.x · goal.y · goal.yaw · goal.z
  start · goal                   [x, y(, yaw)] 목록이 든 한 열(예: red_xy)
  discrete.<이름> · extra.<이름> · thumbs.<이름>
예: map={"start.x": "red_x", "start.y": "red_y", "goal": "ring_xy", "discrete.goal_slot": "ring_slot"}

짐작(map 에 없는 것만): 아래 이름표의 첫 맞는 열. 대응 안 된 열은 숫자면 extra, 글자·참거짓·값 종류 12개 이하 정수면 discrete.
fr5auto 받침 진단 내보내기(red_xy·ring_xy·red_slot·ring_slot·arrangement·same_rack — v2_layouts_*.json) 는 전용 대응을 쓴다.
JSON 은 [행, ...] 또는 {"episodes" | "rows" | "data": [행, ...], "dataset": 이름}.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from ..data import episode
from . import display_path, make_dataset

GUESS = {
    "id": ["id", "ep", "episode", "episode_id", "episode_index", "name"],
    "t": ["t", "time", "timestamp", "started_at", "datetime", "date"],
    "outcome": ["outcome", "result", "verdict", "success"],
    "weight": ["weight", "w"],
    "start": ["start_xy", "pick_xy", "start", "pick", "src_xy", "from_xy", "red_xy", "object_xy"],
    "goal": ["goal_xy", "place_xy", "goal", "place", "dst_xy", "to_xy", "target_xy", "ring_xy", "slot_xy"],
    "start.x": ["start.x", "start_x", "pick_x", "src_x", "from_x", "x0", "red_x", "object_x"],
    "start.y": ["start.y", "start_y", "pick_y", "src_y", "from_y", "y0", "red_y", "object_y"],
    "start.yaw": ["start.yaw", "start_yaw", "pick_yaw", "yaw0"],
    "start.z": ["start.z", "start_z", "pick_z", "z0"],
    "goal.x": ["goal.x", "goal_x", "place_x", "dst_x", "to_x", "x1", "target_x", "ring_x", "slot_x"],
    "goal.y": ["goal.y", "goal_y", "place_y", "dst_y", "to_y", "y1", "target_y", "ring_y", "slot_y"],
    "goal.yaw": ["goal.yaw", "goal_yaw", "place_yaw", "yaw1"],
    "goal.z": ["goal.z", "goal_z", "place_z", "z1"],
}

# fr5auto rack cover 내보내기(v2_layouts_*.json) 전용 — 열 뜻이 정해져 있다
FR5AUTO_COVER = {"id": "ep", "t": "t", "outcome": "outcome", "start": "red_xy", "goal": "ring_xy",
                 "discrete.start_slot": "red_slot", "discrete.goal_slot": "ring_slot", "discrete.arrangement": "arrangement",
                 "discrete.same_fixture": "same_rack", "extra.move_mm": "move_mm"}
FR5AUTO_COVER_SKIP = {"i", "near", "rec_id", "placed_vs_target"}     # 분석이 다시 세는 값·글 설명


def _conv(v):
    """CSV 글자 → 숫자·참거짓·None."""
    if not isinstance(v, str):
        return v
    s = v.strip()
    if s == "":
        return None
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    if s[0] in "[{":
        try:
            return json.loads(s)
        except ValueError:
            return s
    try:
        f = float(s)
        if math.isfinite(f) and f == int(f) and "." not in s and "e" not in low:
            return int(f)
        return f
    except ValueError:
        return s


def read_rows(path, sep=None) -> tuple[list[dict], dict]:
    """파일 → (행 목록, 머리 정보 {"dataset", "note"})."""
    p = Path(path).expanduser()
    suf = p.suffix.lower()
    head = {}
    if suf in (".csv", ".tsv"):
        with p.open(encoding="utf-8", newline="") as f:
            rows = [{k.strip(): _conv(v) for k, v in r.items() if k is not None} for r in
                    csv.DictReader(f, delimiter=sep or ("\t" if suf == ".tsv" else ","))]
        return rows, head
    if suf == ".jsonl":
        rows = []
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    if isinstance(r, dict):
                        rows.append(r)
        return rows, head
    d = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(d, list):
        return [r for r in d if isinstance(r, dict)], head
    if isinstance(d, dict):
        for k in ("episodes", "rows", "data"):
            if isinstance(d.get(k), list):
                head = {"dataset": d.get("dataset"), "note": d.get("note")}
                return [r for r in d[k] if isinstance(r, dict)], head
    raise ValueError(f"{display_path(p)}: 표 모양이 아니다(행 목록 또는 {{'episodes': [...]}})")


def _get(r, col):
    if col is None:
        return None
    if col in r:
        return r[col]
    cur = r                                                          # 'a.b' 안쪽 키
    for part in str(col).split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def guess_map(rows, given=None) -> dict:
    """열 이름 → 대응(map 에 없는 것만 짐작)."""
    cols = []
    for r in rows[:50]:
        for k in r:
            if k not in cols:
                cols.append(k)
    m = dict(given or {})
    if {"red_xy", "ring_xy"} <= set(cols) and not given:
        m = {k: v for k, v in FR5AUTO_COVER.items() if v in cols}
        return m
    low = {c.lower(): c for c in cols}
    for key, names in GUESS.items():
        if key in m:
            continue
        if key in ("start", "goal") and (f"{key}.x" in m):
            continue
        for nm in names:
            if nm.lower() in low:
                c = low[nm.lower()]
                if key in ("start", "goal") and not any(isinstance(r.get(c), (list, tuple)) for r in rows[:20]):
                    continue                                         # 목록 열이 아니면 x·y 짝으로
                m[key] = c
                break
    for role in ("start", "goal"):                                   # 목록 열을 찾았으면 x·y 짝 짐작은 버린다
        if role in m and (given or {}).get(f"{role}.x") is None:
            m.pop(f"{role}.x", None)
            m.pop(f"{role}.y", None)
    return m


def _pt(r, m, role):
    p = {}
    v = _get(r, m.get(role)) if role in m else None
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        p.update(x=v[0], y=v[1])
        if len(v) >= 3:
            p["yaw"] = v[2]
    elif isinstance(v, dict):
        p.update({k: v[k] for k in ("x", "y", "yaw", "z") if k in v})
    for k in ("x", "y", "yaw", "z"):
        c = m.get(f"{role}.{k}")
        if c is not None and _get(r, c) is not None:
            p[k] = _get(r, c)
    return p or None


def _outcome(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return "success" if v else "fail"
    s = str(v).strip().lower()
    if s in ("success", "ok", "1", "true", "pass", "yes"):
        return "success"
    if s in ("fail", "failure", "0", "false", "no"):
        return "fail"
    if s in ("unsure", "unknown", "?"):
        return "unsure"
    return s


def rows_to_episodes(rows, m, skip=(), scale=1.0) -> list[dict]:
    used = set(m.values()) | set(skip)
    # 대응 안 된 열: 값 종류
    rest = {}
    for r in rows:
        for k, v in r.items():
            if k in used:
                continue
            rest.setdefault(k, set())
            if isinstance(v, (str, bool, int)) and not isinstance(v, float):
                rest[k].add(v if not isinstance(v, list) else None)
    eps = []
    for i, r in enumerate(rows):
        st, gl = _pt(r, m, "start"), _pt(r, m, "goal")
        if scale != 1.0:
            for p in (st, gl):
                for k in ("x", "y", "z"):
                    if p and k in p and p[k] is not None:
                        p[k] = float(p[k]) * scale
        disc, extra, thumbs = {}, {}, {}
        for key, col in m.items():
            v = _get(r, col)
            if v is None:
                continue
            if key.startswith("discrete."):
                disc[key[9:]] = v
            elif key.startswith("extra."):
                extra[key[6:]] = v
            elif key.startswith("thumbs."):
                thumbs[key[7:]] = str(v)
        for k, v in r.items():
            if k in used or v is None:
                continue
            if isinstance(v, bool) or isinstance(v, str):
                if len(rest.get(k, ())) <= 12:
                    disc[k] = v
            elif isinstance(v, int) and len(rest.get(k, ())) <= 12:
                disc[k] = v
            elif isinstance(v, (int, float)):
                extra[k] = v
        w = _get(r, m.get("weight")) if "weight" in m else None
        try:
            w = float(w) if w is not None else 1.0
        except (TypeError, ValueError):
            w = 1.0
        rid = _get(r, m.get("id")) if "id" in m else None
        t = _get(r, m.get("t")) if "t" in m else None
        eps.append(episode(rid if rid is not None else f"ep_{i:03d}", "", st, gl, t=None if t is None else str(t),
                           outcome=_outcome(_get(r, m.get("outcome")) if "outcome" in m else None), weight=w, source="table",
                           discrete=disc, extra=extra, thumbs=thumbs))
    return eps


def _native(r) -> bool:
    """data.py 에피소드 모양인가: start·goal 이 x·y 를 가진 묶음."""
    return all(isinstance(r.get(k), dict) and "x" in r[k] and "y" in r[k] for k in ("start", "goal"))


def load(path, name=None, weight=1.0, map=None, sep=None, scale=1.0, **_):
    """표 파일 → Dataset. map: 열 대응(모듈 설명), scale: 좌표에 곱할 값(m → mm 면 1000)."""
    p = Path(path).expanduser()
    rows, head = read_rows(p, sep)
    if not map and rows and all(_native(r) for r in rows[:20]):
        # layoutkit 에피소드 모양 그대로(data.py — start/goal 이 {"x","y",...} 묶음): 열 대응 없이 받는다
        eps = [episode(r.get("id", f"ep_{i:03d}"), "", r["start"], r["goal"], t=r.get("t"), outcome=r.get("outcome"),
                       weight=r.get("weight", 1.0), source=r.get("source") or "table", discrete=r.get("discrete"),
                       fixtures=r.get("fixtures"), extra=r.get("extra"), thumbs=r.get("thumbs"))
               for i, r in enumerate(rows) if _native(r)]
        nm = name or (str(head["dataset"]) if head.get("dataset") else p.stem)
        meta = {"kind": "table", "path": display_path(p.resolve()), "format": "layoutkit"}
        if head.get("note"):
            meta["note"] = str(head["note"])
        return make_dataset(nm, eps, weight=weight, meta=meta)
    m = guess_map(rows, map)
    if not any(k in m for k in ("start", "start.x")) or not any(k in m for k in ("goal", "goal.x")):
        cols = sorted({k for r in rows[:20] for k in r})
        raise ValueError(f"{display_path(p)}: 집은 자리·놓은 자리 열을 못 찾았다 — map 으로 알려 준다(예: start.x=열이름). 열: {', '.join(cols)}")
    skip = FR5AUTO_COVER_SKIP if m.get("start") == "red_xy" and m.get("goal") == "ring_xy" else ()
    eps = rows_to_episodes(rows, m, skip, float(scale))
    nm = name or (Path(str(head["dataset"])).name if head.get("dataset") else p.stem)
    meta = {"kind": "table", "path": display_path(p.resolve()), "map": m}
    if head.get("note"):
        meta["note"] = str(head["note"])
    return make_dataset(nm, eps, weight=weight, meta=meta)
