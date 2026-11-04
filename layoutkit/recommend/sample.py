"""후보 배치 뽑기 — Halton 수열 + 무작위 이동(Cranley–Patterson), 이산은 고르게. rackrec.halton·sample 의 일반화.

받침 spec(고정물 한 형식 × 2, 칸 4, 장애물 1, 같은 받침 허용)에서는 rackrec.sample 과 난수를 같은 순서로 쓴다
(Halton 6차원 → 빨강 받침 a → (빨강, 노랑) 칸 순서쌍 → 링 받침 b → 링 칸 하나씩) — 같은 시드면 같은 후보가 나온다(tests 에서 확인).

후보 묶음 C(dict, 길이 N):
  공통: "kind", "n", "g" (N×3: start x, y, ψ), "q" (N×3: goal x, y, ψ), "disc" {이름: 값 번호 N}
  fixtures: "P" (N×F×2 고정물 가운데), "yaw" (N×F), "H" (N×F×S×2 칸 xy, 없는 칸 NaN), "a"·"ks" (start 고정물·칸),
            "obs" (N×n_obs 장애물 칸 — 고정물 a), "b"·"kg" (goal 고정물·칸). F = 모든 고정물 인스턴스(고정된 것 포함).
"""
from __future__ import annotations

import itertools

import numpy as np

from .layout import Layout, canon

# 앞 8개는 rackrec.PRIMES 와 같다(재현) — 고정물·차원이 많으면 뒤 소수를 쓴다
PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97, 101, 103, 107, 109, 113)


def halton(n, d, rng=None, start=None):
    """Halton 수열 n×d(소수 밑 반전) + 무작위 이동(Cranley–Patterson) — 낮은 불일치로 고르게(scipy 없이). rackrec.halton 과 같다."""
    if d > len(PRIMES):
        raise ValueError(f"Halton 차원 {d} > {len(PRIMES)} — 고정물을 줄이거나 PRIMES 를 늘린다")
    rng = rng or np.random.default_rng()
    s = int(rng.integers(1, 10 ** 5)) if start is None else int(start)
    out = np.zeros((n, d))
    idx = np.arange(s, s + n)
    for j in range(d):
        b = PRIMES[j]
        f, i, v = 1.0, idx.copy(), np.zeros(n)
        while np.any(i > 0):
            f /= b
            v += f * (i % b)
            i //= b
        out[:, j] = v
    return (out + rng.random(d)[None, :]) % 1.0


def sample(lay: Layout, n: int, rng) -> dict:
    n = int(n)
    if lay.kind == "points":
        return _points(lay, n, rng)
    return _fixtures(lay, n, rng)


# ---------------------------------------------------------------- points
def _points(lay: Layout, n, rng) -> dict:
    dims = 4 + (1 if lay.start_yaw else 0) + (1 if lay.goal_yaw else 0)
    U = halton(n, dims, rng)
    j = 0
    out = {}
    for side, ar, yr in (("g", lay.start_area, lay.start_yaw), ("q", lay.goal_area, lay.goal_yaw)):
        x0, x1, y0, y1 = ar
        X = np.zeros((n, 3))
        X[:, 0] = x0 + U[:, j] * (x1 - x0)
        X[:, 1] = y0 + U[:, j + 1] * (y1 - y0)
        j += 2
        if yr:
            X[:, 2] = canon(yr[0] + U[:, j] * (yr[1] - yr[0]), lay.period_s)
            j += 1
        out[side] = X
    disc = {v["name"]: rng.integers(0, len(v["values"]), n) for v in lay.discrete}
    return {"kind": "points", "n": n, "g": out["g"], "q": out["q"], "disc": disc}


# ---------------------------------------------------------------- fixtures
def _yaw_of(lay: Layout, t, x, y, u):
    """인스턴스 줄 방향 뽑기: yaw_range 가 있으면 그 안 고르게 · 손목 창이면 그 자리 창 가운데 ± 반폭(rackrec.sample) · 아니면 전 범위."""
    if t.yaw_range is not None:
        lo, hi = t.yaw_range
        return canon(lo + u * (hi - lo), t.period)
    if lay.window is not None:
        return canon(lay.window.center(x, y) + (2 * u - 1) * lay.window.half, t.period)
    return canon(-t.period / 2.0 + u * t.period, t.period)


def _fixtures(lay: Layout, n, rng) -> dict:
    inst = lay.instances
    F = len(inst)
    mov = [i for i, I in enumerate(inst) if I.pose is None]
    U = halton(n, 3 * len(mov), rng) if mov else np.zeros((n, 0))
    P = np.zeros((n, F, 2))
    yaw = np.zeros((n, F))
    for j, i in enumerate(mov):
        I = inst[i]
        t = I.type
        x0, x1, y0, y1 = I.area
        m = t.m                                                       # rackrec: 목표 영역을 칸 줄 반 길이만큼 넓혀 가운데를 뽑는다
        P[:, i, 0] = x0 - m + U[:, 3 * j] * (x1 - x0 + 2 * m)
        P[:, i, 1] = y0 - m + U[:, 3 * j + 1] * (y1 - y0 + 2 * m)
        yaw[:, i] = _yaw_of(lay, t, P[:, i, 0], P[:, i, 1], U[:, 3 * j + 2])
    for i, I in enumerate(inst):
        if I.pose is not None:
            P[:, i] = (I.pose["x"], I.pose["y"])
            yaw[:, i] = I.pose["yaw"]
    # 번호: order "x" 인 형식은 움직이는 인스턴스끼리 베이스 x 작은 쪽부터(rackrec: 받침 번호 = 인식 순서). 같으면 그대로(stable)
    for t in lay.types:
        ids = [i for i in mov if inst[i].type is t]
        if t.order == "x" and len(ids) > 1:
            o = np.argsort(P[:, ids, 0], axis=1, kind="stable")
            sel = np.asarray(ids)[o]
            P[:, ids] = np.take_along_axis(P, np.repeat(sel[:, :, None], 2, axis=2), axis=1)
            yaw[:, ids] = np.take_along_axis(yaw, sel, axis=1)
    sT, gT = lay.start_type, lay.goal_type
    A_idx = np.array([i for i, I in enumerate(inst) if I.type is sT])
    B_idx = np.array([i for i, I in enumerate(inst) if I.type is gT])
    n_obs = len(lay.obstacles)
    perms = np.array(list(itertools.permutations(range(sT.n_slots), 1 + n_obs)), int)   # rackrec pairs 와 같은 순서
    disc = {}
    if not lay.rule:
        a = A_idx[rng.integers(0, len(A_idx), n)]
        pk = rng.integers(0, len(perms), n)
        for v in lay.discrete:                                        # 받침 spec 에는 없다(재현 순서 유지)
            disc[v["name"]] = rng.integers(0, len(v["values"]), n)
        if sT is gT and not lay.same_allowed:
            if len(B_idx) == 2:
                b = np.where(a == B_idx[0], B_idx[1], B_idx[0])      # rackrec: b = 1 − a (난수 안 씀)
            else:
                r = rng.integers(0, len(B_idx) - 1, n)
                pa = np.searchsorted(B_idx, a)
                b = B_idx[np.where(r >= pa, r + 1, r)]
        else:
            b = B_idx[rng.integers(0, len(B_idx), n)]
    else:
        # 규칙(예: 색 → 정해진 고정물): 규칙 변수 먼저, goal 고정물은 규칙으로, start 고정물은 남은 것 중 고르게
        rule = lay.rule
        for v in lay.discrete:
            disc[v["name"]] = rng.integers(0, len(v["values"]), n)
        vals = next(v["values"] for v in lay.discrete if v["name"] == rule["by"])
        names = lay.instance_names()
        tgt = []
        for val in vals:
            g_ = (rule.get("goal") or {}).get(str(val))
            if g_ is None:
                raise ValueError(f"layout.rule.goal 에 {val} 이 없다")
            tgt.append(names.index(f"{g_['fixture']}{int(g_.get('index', 0))}"))
        b = np.asarray(tgt, int)[disc[rule["by"]]]
        diff = bool(rule.get("start_differs", True))
        a = np.zeros(n, int)
        for t_ in range(n):
            allowed = [i for i in A_idx if not (diff and i == b[t_])] or list(A_idx)
            a[t_] = allowed[int(rng.integers(len(allowed)))]
        pk = rng.integers(0, len(perms), n)
    ks, obs = perms[pk, 0], perms[pk, 1:]
    nG = np.array([I.type.n_slots for I in inst])[b]                # 규칙이면 goal 고정물 형식이 후보마다 다를 수 있다(버림 통 1칸)
    kg = np.zeros(n, int)
    for t_ in range(n):
        occ = set([int(ks[t_])] + [int(o) for o in obs[t_]]) if b[t_] == a[t_] else set()
        free = [k for k in range(int(nG[t_])) if k not in occ]
        kg[t_] = free[int(rng.integers(len(free)))]                 # rackrec 과 같은 호출(같은 난수 줄)
    S = max(t.n_slots for t in lay.types)
    H = np.full((n, F, S, 2), np.nan)
    for i, I in enumerate(inst):
        off = I.type.offsets
        r = np.radians(yaw[:, i])
        c, s_ = np.cos(r)[:, None], np.sin(r)[:, None]
        H[:, i, :len(off), 0] = P[:, i, 0][:, None] + off[None, :, 0] * c - off[None, :, 1] * s_
        H[:, i, :len(off), 1] = P[:, i, 1][:, None] + off[None, :, 0] * s_ + off[None, :, 1] * c
    idx = np.arange(n)
    g = np.c_[H[idx, a, ks], yaw[idx, a]]
    q = np.c_[H[idx, b, kg], yaw[idx, b]]
    return {"kind": "fixtures", "n": n, "P": P, "yaw": yaw, "H": H, "a": a, "ks": ks, "obs": obs, "b": b, "kg": kg,
            "g": g, "q": q, "disc": disc}


def take(C: dict, m) -> dict:
    """후보 묶음에서 일부(불리언 또는 번호)만."""
    out = {}
    for k, v in C.items():
        if isinstance(v, np.ndarray) and v.ndim >= 1 and v.shape[0] == C["n"]:
            out[k] = v[m]
        elif k == "disc":
            out[k] = {kk: vv[m] for kk, vv in v.items()}
        else:
            out[k] = v
    out["n"] = len(out["g"])
    return out
