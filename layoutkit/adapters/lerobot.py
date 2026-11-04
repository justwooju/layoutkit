"""LeRobot v2.x 어댑터 — meta/info.json · meta/episodes.jsonl · data/chunk-*/episode_*.parquet → 궤적 사건 → Dataset.

parquet 읽기에 pyarrow 가 필요하다(pip install pyarrow, 또는 pip install 'layoutkit[parquet]').
에피소드 파일이 없으면(v3 처럼 한 파일에 여러 에피소드) data/ 아래 parquet 을 다 읽어 episode_index 로 나눈다.

열 고르기(옵션 — 없으면 짐작):
  state      상태 벡터 열(기본 observation.state, 없으면 이름에 state 가 든 첫 벡터 열)
  eef        EEF 위치가 따로 든 열(예: observation.eef_pos) — 주면 xyz 는 이 열에서
  xyz        위치 칸 번호 3개(기본: names 에서 x·y·z 를 찾고, 못 찾으면 [0, 1, 2])
  grip       그리퍼 칸 번호 또는 열 이름(기본: names 에 grip·finger·claw 가 든 칸 → 따로 된 gripper 열 → 상태 마지막 칸)
  yaw        yaw 칸 번호(기본: names 에 yaw·rz 가 든 칸, 없으면 쓰지 않음)
  units · yaw_units · closed_is · threshold · grip_range · min_closed_s …   events.detect 옵션(기본 units auto, yaw_units auto)
상태가 관절각뿐(names 에 joint·shoulder·elbow 등)이고 위치 칸을 못 찾으면 짐작하지 않고 오류로 알린다(eef 또는 xyz 를 준다).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from .. import events as EV
from ..data import episode
from . import display_path, make_dataset

EV_KEYS = ("units", "yaw_units", "closed_is", "threshold", "grip_range", "min_closed_s", "min_open_s", "min_frames", "hyst",
           "sep_ratio", "settle_s", "still_mm_s", "which")
JOINTY = re.compile(r"joint|shoulder|elbow|wrist_(flex|roll|pitch)|pan|lift|q\d", re.I)


def _need_pyarrow():
    try:
        import pyarrow.parquet as pq                                 # 선택 의존
        return pq
    except ImportError as e:
        raise RuntimeError("LeRobot parquet 을 읽으려면 pyarrow 가 필요하다: pip install pyarrow "
                           "(또는 pip install 'layoutkit[parquet]')") from e


def flat_names(feat) -> list[str] | None:
    """features[열]["names"] → 이름 목록(목록 · {"motors": [...]} · {"axes": [...]} 모두)."""
    n = (feat or {}).get("names")
    if isinstance(n, list):
        if n and isinstance(n[0], list):
            return [str(x) for sub in n for x in sub]
        return [str(x) for x in n]
    if isinstance(n, dict):
        out = []
        for v in n.values():
            if isinstance(v, list):
                out += [str(x) for x in v]
        return out or None
    return None


def _find(names, pats, avoid=("rot", "quat", "vel", "action", "force", "torque")):
    if not names:
        return None
    for i, nm in enumerate(names):
        s = nm.lower()
        if any(a in s for a in avoid):
            continue
        if any(re.search(p, s) for p in pats):
            return i
    return None


def guess_columns(info: dict, opt: dict) -> dict:
    """info.json features → {"state", "eef", "xyz", "grip_col", "grip", "yaw", "names", "guessed": [...]}."""
    feats = info.get("features") or {}
    g = {"guessed": []}
    st = opt.get("state")
    if st is None:
        if "observation.state" in feats:
            st = "observation.state"
        else:
            st = next((k for k, f in feats.items() if "state" in k and len((f or {}).get("shape") or [0]) == 1
                       and ((f or {}).get("shape") or [0])[0] >= 3), None)
    g["state"] = st
    eef = opt.get("eef")
    if eef is None:
        eef = next((k for k in feats if re.search(r"(eef|ee|tcp|end_effector)[._]?(pos|position|xyz)", k.lower())), None)
        if eef:
            g["guessed"].append("eef")
    g["eef"] = eef
    names = flat_names(feats.get(st)) if st else None
    g["names"] = names
    xyz = opt.get("xyz")
    if xyz is None and eef is None:
        idx = [_find(names, [rf"^{a}$", rf"[._ ]{a}$", rf"^(ee|eef|tcp|pos)[._]?{a}$"]) for a in "xyz"]
        if all(i is not None for i in idx):
            xyz = idx
        else:
            if names and sum(bool(JOINTY.search(n)) for n in names) >= 2:
                raise ValueError(f"상태 열 {st} 이 관절각으로 보인다({', '.join(names[:8])}…) — EEF 위치 열(eef=) 또는 칸 번호(xyz=)를 준다")
            xyz = [0, 1, 2]
            g["guessed"].append("xyz=[0,1,2]")
    g["xyz"] = list(xyz) if xyz is not None else [0, 1, 2]
    grip = opt.get("grip")
    g["grip_col"] = None
    if isinstance(grip, str) and not grip.lstrip("-").isdigit():
        g["grip_col"], grip = grip, 0
    elif grip is not None:
        grip = int(grip)
    else:
        i = _find(names, [r"grip", r"finger", r"claw", r"jaw"], avoid=("vel", "force", "torque"))
        if i is not None:
            grip = i
        else:
            col = next((k for k in feats if re.search(r"grip|finger|claw", k.lower()) and not k.startswith("action")), None)
            if col:
                g["grip_col"], grip = col, 0
            else:
                shp = (feats.get(st) or {}).get("shape") or [0]
                grip = int(shp[0]) - 1 if shp and shp[0] else -1
                g["guessed"].append("grip=last")
    g["grip"] = grip
    yaw = opt.get("yaw")
    if yaw is None:
        yaw = _find(names, [r"yaw", r"(^|[._ ])rz$"])
    g["yaw"] = None if yaw is None else int(yaw)
    return g


def _vec(col, n_expect=None):
    A = np.asarray([np.asarray(v, float).reshape(-1) if v is not None else np.full(n_expect or 1, np.nan) for v in col], float)
    return A.reshape(len(col), -1)


def episode_from_columns(cols: dict, info: dict, g: dict, idx: int, ev_opt=None, task=None) -> dict:
    """한 에피소드의 열(dict: 이름 → 프레임 목록) → 에피소드 dict. parquet 없이도 시험할 수 있게 분리했다."""
    fps = float(info.get("fps") or 10.0)
    st = _vec(cols[g["state"]]) if g.get("state") and g["state"] in cols else None
    src = _vec(cols[g["eef"]]) if g.get("eef") else st
    if src is None:
        raise ValueError(f"episode {idx}: 위치 열이 없다(state={g.get('state')}, eef={g.get('eef')})")
    xyz = src[:, g["xyz"]]
    if g.get("grip_col"):
        gr = _vec(cols[g["grip_col"]])[:, int(g["grip"])]
    else:
        gr = st[:, int(g["grip"])]
    yaw = st[:, int(g["yaw"])] if (g.get("yaw") is not None and st is not None) else None
    if "timestamp" in cols:
        t = np.asarray(cols["timestamp"], float).reshape(-1)
    elif "frame_index" in cols:
        t = np.asarray(cols["frame_index"], float).reshape(-1) / fps
    else:
        t = np.arange(len(xyz)) / fps
    o = {"units": "auto", "yaw_units": "auto", "hz": fps}
    o.update(ev_opt or {})
    ev = EV.detect(t, xyz, gr, yaw, **o)
    extra = {"duration_s": ev["duration_s"], "n_frames": ev["n_frames"], "path_mm": ev["path_mm"], "n_grasps": len(ev["segments"])}
    if ev["ok"]:
        extra.update(t_pick_s=ev["t_pick"] - float(t[0]), t_place_s=ev["t_place"] - float(t[0]))
    disc = {"task": task} if task else {}
    e = episode(f"episode_{idx:06d}", "", ev["start"] if ev["ok"] else None, ev["goal"] if ev["ok"] else None, outcome=None,
                source="lerobot", discrete=disc, extra=extra)
    e["_events"] = {"flags": ev["flags"], "threshold": ev["threshold"], "closed_is": ev["closed_is"], "units": ev["units"]}
    return e


def _episodes_meta(root: Path, info: dict) -> list[dict]:
    p = root / "meta" / "episodes.jsonl"
    out = []
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    if not out:
        out = [{"episode_index": i} for i in range(int(info.get("total_episodes") or 0))]
    return out


def _ep_path(root: Path, info: dict, idx: int) -> Path | None:
    tpl = info.get("data_path") or "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet"
    cs = int(info.get("chunks_size") or 1000)
    try:
        p = root / tpl.format(episode_chunk=idx // cs, episode_index=idx)
        if p.is_file():
            return p
    except (KeyError, IndexError, ValueError):
        pass
    hits = sorted(root.glob(f"data/**/episode_{idx:06d}.parquet"))
    return hits[0] if hits else None


def load(path, name=None, weight=1.0, state=None, eef=None, xyz=None, grip=None, yaw=None, episodes=None, **opt):
    """LeRobot 폴더 → Dataset. episodes: 읽을 에피소드 번호 목록(없으면 전부)."""
    root = Path(path).expanduser()
    info = json.loads((root / "meta" / "info.json").read_text(encoding="utf-8"))
    g = guess_columns(info, {"state": state, "eef": eef, "xyz": xyz, "grip": grip, "yaw": yaw})
    ev_opt = {k: v for k, v in opt.items() if k in EV_KEYS}
    pq = _need_pyarrow()
    cols_need = sorted({c for c in (g["state"], g["eef"], g["grip_col"], "timestamp", "frame_index", "episode_index") if c})
    metas = _episodes_meta(root, info)
    if episodes is not None:
        want = {int(i) for i in episodes}
        metas = [m for m in metas if int(m.get("episode_index", -1)) in want]
    eps, flags = [], {}
    pooled = None
    for m in metas:
        idx = int(m.get("episode_index", len(eps)))
        tasks = m.get("tasks")
        task = tasks[0] if isinstance(tasks, list) and tasks else None
        p = _ep_path(root, info, idx)
        if p is not None:
            tb = pq.read_table(p, columns=[c for c in cols_need if c in pq.read_schema(p).names])
            cols = tb.to_pydict()
        else:
            if pooled is None:                                       # 한 파일에 여러 에피소드(v3 모양) — 한 번만 다 읽는다
                pooled = {}
                for f in sorted(root.glob("data/**/*.parquet")):
                    names = pq.read_schema(f).names
                    d = pq.read_table(f, columns=[c for c in cols_need if c in names]).to_pydict()
                    if "episode_index" not in d:
                        continue
                    ei = np.asarray(d["episode_index"], int)
                    for k in np.unique(ei):
                        sel = np.flatnonzero(ei == k)
                        part = pooled.setdefault(int(k), {})
                        for c, v in d.items():
                            part.setdefault(c, []).extend(v[i] for i in sel)
            cols = pooled.get(idx)
            if cols is None:
                continue
        e = episode_from_columns(cols, info, g, idx, ev_opt, task)
        for f in e.pop("_events")["flags"]:
            flags[f] = flags.get(f, 0) + 1
        eps.append(e)
    meta = {"kind": "lerobot", "path": display_path(root.resolve()), "version": info.get("codebase_version"),
            "fps": info.get("fps"), "columns": {k: g[k] for k in ("state", "eef", "xyz", "grip_col", "grip", "yaw")},
            "guessed": g["guessed"], "event_flags": flags}
    return make_dataset(name or root.name, eps, weight=weight, meta=meta)
