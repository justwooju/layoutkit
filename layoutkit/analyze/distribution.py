"""분포 — 범위, 서로 다른 자리(12 mm 욕심 묶음), 옮긴 거리·가까이 비율, 이산 칸(strata), 이산 값 셈, 같은 자리 짝.

서로 다른 자리 = rackrec.clusters(앞에서부터 r mm 안을 한 묶음, '<' 비교) 그대로 — 에피소드 순서가 결과를 정하므로 읽은 순서를 지킨다.
같은 자리 짝(dups) = 집은 자리끼리·놓은 자리끼리 모두 dup_mm 안인 두 에피소드(뒤 에피소드에 dup 깃발).
"""
from __future__ import annotations

import numpy as np

from ..spec import feature


def clusters(P, r=12.0) -> np.ndarray:
    """r mm 묶음(앞에서부터 욕심껏) — '서로 다른 자리' 수 세기. rackrec 그대로."""
    P = np.asarray(P, float).reshape(-1, 2)
    lab = -np.ones(len(P), int)
    c = 0
    for i in range(len(P)):
        if lab[i] >= 0:
            continue
        m = (np.linalg.norm(P - P[i], axis=1) < r) & (lab < 0)
        lab[m] = c
        c += 1
    return lab


def vkey(v) -> str:
    """이산 값 → 표 키(참거짓 true/false, 정수 같은 실수는 정수로)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def ranges(eps) -> dict:
    out = {}
    for role in ("start", "goal"):
        for k in ("x", "y", "yaw", "z"):
            v = [e[role][k] for e in eps if e[role].get(k) is not None]
            if v:
                out[f"{role}.{k}"] = [round(float(min(v)), 1), round(float(max(v)), 1)]
    return out


def transfer(eps, near_mm) -> tuple[dict, np.ndarray]:
    d = np.array([np.hypot(e["goal"]["x"] - e["start"]["x"], e["goal"]["y"] - e["start"]["y"]) for e in eps], float)
    w = np.array([float(e.get("weight", 1.0)) for e in eps], float)
    near = d <= float(near_mm)
    if len(d) == 0:
        return {"values": [], "min": None, "median": None, "max": None, "near_share": None, "near_n": 0, "near_mm": float(near_mm)}, d
    return {"values": np.round(d, 1).tolist(), "min": round(float(d.min()), 1), "median": round(float(np.median(d)), 1),
            "max": round(float(d.max()), 1), "near_share": round(float((w * near).sum() / w.sum()), 3) if w.sum() > 0 else None,
            "near_n": int(near.sum()), "near_mm": float(near_mm)}, d


def spots(eps, dup_mm) -> tuple[dict, set]:
    S = np.array([[e["start"]["x"], e["start"]["y"]] for e in eps], float).reshape(-1, 2)
    G = np.array([[e["goal"]["x"], e["goal"]["y"]] for e in eps], float).reshape(-1, 2)
    ls, lg = clusters(S, dup_mm), clusters(G, dup_mm)
    dups, flagged = [], set()
    if len(S) >= 2:
        dS = np.sqrt(((S[:, None, :] - S[None, :, :]) ** 2).sum(axis=2))
        dG = np.sqrt(((G[:, None, :] - G[None, :, :]) ** 2).sum(axis=2))
        m = np.triu((dS < dup_mm) & (dG < dup_mm), 1)
        for i, j in zip(*np.nonzero(m)):
            dups.append([eps[i]["id"], eps[j]["id"], round(float(max(dS[i, j], dG[i, j])), 1)])
            flagged.add(eps[j]["id"])
    return {"start": int(ls.max() + 1) if len(ls) else 0, "goal": int(lg.max() + 1) if len(lg) else 0,
            "pairs": len(set(zip(ls.tolist(), lg.tolist()))), "dup_mm": float(dup_mm), "n_dups": len(dups),
            "dup_episodes": len(flagged), "dups": dups[:500]}, flagged


def _dval(e, name):
    """strata 이름 → 값: discrete.<이름> 먼저, 아니면 'start.x' 같은 특징."""
    d = e.get("discrete") or {}
    if name in d:
        return d[name]
    return feature(e, name)


def strata(eps, spec) -> list[dict]:
    """spec.strata 마다 칸 비율과 목표(없으면 고르게) — n = 에피소드 수, share = 무게 비율."""
    out = []
    w = np.array([float(e.get("weight", 1.0)) for e in eps], float)
    for s in spec.get("strata") or []:
        vals = list(s["values"])
        sh = s.get("shares") or [1.0 / len(vals)] * len(vals)
        got = [_dval(e, s["name"]) for e in eps]
        keys = [vkey(v) if v is not None else None for v in got]
        known = [k is not None for k in keys]
        tot = float(w[np.asarray(known, bool)].sum()) if eps else 0.0
        rows = []
        for v, p in zip(vals, sh):
            m = np.array([k == vkey(v) for k in keys], bool)
            ww = float(w[m].sum()) if len(m) else 0.0
            rows.append({"value": v, "n": int(m.sum()), "w": round(ww, 3), "share": round(ww / tot, 3) if tot > 0 else None,
                         "target": round(float(p), 3)})
        listed = {vkey(v) for v in vals}
        other = sum(1 for k in keys if k is not None and k not in listed)
        devs = [abs(r["share"] - r["target"]) for r in rows if r["share"] is not None]
        out.append({"name": s["name"], "rows": rows, "max_dev": round(max(devs), 3) if devs else None,
                    "n_known": int(sum(known)), "n_other": other})
    return out


def discrete_counts(eps, max_values=24) -> dict:
    """discrete 키마다 값 셈(값 종류가 max_values 보다 많은 키는 뺀다)."""
    keys = []
    for e in eps:
        for k in (e.get("discrete") or {}):
            if k not in keys:
                keys.append(k)
    out = {}
    for k in keys:
        c = {}
        for e in eps:
            v = (e.get("discrete") or {}).get(k)
            if v is None:
                continue
            kk = vkey(v)
            c[kk] = c.get(kk, 0) + 1
        if 0 < len(c) <= max_values:
            out[k] = dict(sorted(c.items(), key=lambda x: (-x[1], x[0])))
    return out
