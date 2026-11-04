"""칸 채움 — 육각 칸(fr5auto rackrec 와 같은 hex_centers·cell_of), 방향 칸, N_min, 쿠폰 수집, 채움 거리.

칸 = 목표 영역 가운데에 맞춘 반지름 h 육각 배열의 칸 가운데(영역 안). 점은 가장 가까운 칸(영역 밖이면 −1).
이론 칸 수 = ⌈A / ((3√3/2)h²)⌉ × 방향 칸 수 [Kershner 1939] — 무작위로 놓을 때 다 채우는 데 드는 판 수 n·H_n(쿠폰 수집)의 n.
방향 칸(yaw): spec.scales.use_yaw 이고 yaw 가 있는 에피소드가 있을 때만. 폭 2·h_yaw.
  창 = spec.layout.yaw_window({"center_deg" 또는 숫자 "center", "half_deg"}) — center 가 숫자가 아니면 데이터 yaw 의 원형 중앙값.
  창이 없으면 데이터 yaw 범위. 주기는 spec.scales.yaw_period_deg(없으면 360 — 평행 그리퍼처럼 180° 면 180 을 적는다).
reach(놓을 수 있는 칸)는 분석이 모른다(로봇·카메라 검사가 필요) → None. 추천이 알면 apply_reach 로 채운다.
N_min(앞으로 필요한 판 수의 하한) = max(놓을 수 있는 칸 − 그중 채운 칸) 집는·놓는 쪽 — 판 하나가 집는 칸·놓는 칸을 하나씩만 채운다.
  reach 가 없으면 xy 칸 전부를 놓을 수 있다고 본다(위 상한 쪽 추정). 방향 칸까지 친 값은 n_min_yaw.
"""
from __future__ import annotations

import math

import numpy as np


def hex_cell_area(h) -> float:
    """반지름 h 원으로 평면을 빈틈없이 덮는 육각 배열에서 원 하나가 맡는 넓이(3√3/2)h² [Kershner 1939]."""
    return 1.5 * math.sqrt(3.0) * float(h) ** 2


def n_hex(area_mm2, h) -> int:
    """영역을 반지름 h 원으로 덮는 데 드는 칸 수 ⌈A / ((3√3/2)h²)⌉."""
    return int(math.ceil(float(area_mm2) / hex_cell_area(h) - 1e-9))


def hex_centers(area, h):
    """영역(x0, x1, y0, y1) 가운데에 맞춘 육각 배열의 칸 가운데(영역 안) — 줄은 긴 쪽 방향, 간격 √3h, 줄 사이 1.5h. rackrec 그대로."""
    x0, x1, y0, y1 = (float(v) for v in area)
    a, b = math.sqrt(3.0) * h, 1.5 * h
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    long_x = (x1 - x0) >= (y1 - y0)
    nu = int(max(x1 - x0, y1 - y0) / a) + 3
    nv = int(max(x1 - x0, y1 - y0) / b) + 3
    out = []
    for j in range(-nv, nv + 1):
        for i in range(-nu, nu + 1):
            u, v = i * a + (a / 2 if j % 2 else 0.0), j * b
            x, y = (cx + u, cy + v) if long_x else (cx + v, cy + u)
            if x0 - 1e-9 <= x <= x1 + 1e-9 and y0 - 1e-9 <= y <= y1 + 1e-9:
                out.append((x, y))
    return np.array(out, float).reshape(-1, 2)


def cell_of(P, C, area):
    """점마다 가장 가까운 칸 번호(영역 밖이면 −1). rackrec 그대로."""
    P = np.asarray(P, float).reshape(-1, 2)
    if len(P) == 0 or len(C) == 0:
        return np.full(len(P), -1, int)
    x0, x1, y0, y1 = area
    k = np.argmin(((P[:, None, :] - C[None, :, :]) ** 2).sum(axis=2), axis=1)
    ins = (P[:, 0] >= x0) & (P[:, 0] <= x1) & (P[:, 1] >= y0) & (P[:, 1] <= y1)
    return np.where(ins, k, -1)


def coupon(n) -> float:
    """n 칸을 무작위로 다 채우는 데 드는 판 수의 기댓값 n·(1 + 1/2 + … + 1/n)."""
    n = int(n)
    return float(n * sum(1.0 / k for k in range(1, n + 1))) if n > 0 else 0.0


def area_tuple(area: dict):
    return (float(area["x"][0]), float(area["x"][1]), float(area["y"][0]), float(area["y"][1]))


# ---------------------------------------------------------------- 방향 칸
def _wrap(d, period):
    return (np.asarray(d, float) + period / 2.0) % period - period / 2.0


def circ_median(a, period=360.0):
    a = np.asarray([v for v in a if v is not None and np.isfinite(v)], float)
    if len(a) == 0:
        return None
    s = 2 * math.pi / period
    c = math.atan2(np.sin(a * s).mean(), np.cos(a * s).mean()) / s     # 원형 평균 기준으로 풀어 중앙값
    return float(c + np.median(_wrap(a - c, period)))


def yaw_scheme(spec: dict, yaws) -> dict | None:
    """방향 칸 정의 {"center", "half", "width", "bins", "period"} — 쓰지 않으면 None."""
    sc = spec.get("scales") or {}
    ys = [v for v in yaws if v is not None and np.isfinite(v)]
    if not sc.get("use_yaw", True) or not ys:
        return None
    period = float(sc.get("yaw_period_deg") or 360.0)
    width = 2.0 * float(sc.get("h_yaw_deg") or 20.0)
    yw = ((spec.get("layout") or {}).get("yaw_window")) or None
    center = half = None
    if isinstance(yw, dict):
        c = yw.get("center_deg", yw.get("center"))
        center = float(c) if isinstance(c, (int, float)) else None
        half = float(yw["half_deg"]) if isinstance(yw.get("half_deg"), (int, float)) else None
    if center is None:
        center = circ_median(ys, period)
    if half is None:
        d = _wrap(np.asarray(ys) - center, period)
        half = max(float(np.abs(d).max()), width / 2.0)
    half = min(half, period / 2.0)
    bins = max(1, int(math.ceil(2.0 * half / width - 1e-9)))
    return {"center": round(center, 3), "half": round(half, 3), "width": width, "bins": bins, "period": period}


def yaw_bin(yaw, ys: dict | None) -> int:
    """yaw → 방향 칸 번호(창 밖은 가장자리 칸, yaw 없으면 −1) — rackrec.psi_bin 과 같은 식(창 가운데 기준, 잘라 넣기)."""
    if ys is None or yaw is None or not np.isfinite(yaw):
        return -1
    d = float(_wrap(float(yaw) - ys["center"], ys["period"])) + ys["half"]
    return int(min(max(d // ys["width"], 0), ys["bins"] - 1))


# ---------------------------------------------------------------- 채움 거리
def convex_hull(P):
    """2차원 볼록 껍질(단조 사슬) — 반시계 꼭짓점."""
    pts = sorted({(float(x), float(y)) for x, y in np.asarray(P, float).reshape(-1, 2)})
    if len(pts) < 3:
        return np.array(pts, float).reshape(-1, 2)

    def cr(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return np.array(lo[:-1] + up[:-1], float)


def polygon_area(H) -> float:
    if len(H) < 3:
        return 0.0
    x, y = H[:, 0], H[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def _inside_hull(H, X):
    ok = np.ones(len(X), bool)
    for i in range(len(H)):
        a, b = H[i], H[(i + 1) % len(H)]
        ok &= (b[0] - a[0]) * (X[:, 1] - a[1]) - (b[1] - a[1]) * (X[:, 0] - a[0]) >= -1e-9
    return ok


def fill_distance(P_all, sets: dict, max_grid=60000) -> dict:
    """빈 곳 크기: 모든 점(집은·놓은 자리 합침)의 볼록 껍질 안 격자점에서 그 쪽 가장 가까운 점까지 거리의 최댓값(mm).
    docs(FR5-AutoCollect RECOMMENDER 1절) 의 v1 값 61 · 56 mm(껍질 0.059 m²)와 같은 정의 — 격자 간격은 껍질 넓이에 맞춰 1 mm 부터."""
    H = convex_hull(P_all)
    A = polygon_area(H)
    out = {"hull_m2": round(A / 1e6, 4)}
    if A <= 0:
        return {**out, **{k: None for k in sets}}
    step = max(1.0, math.sqrt(A / max_grid))
    xs = np.arange(H[:, 0].min(), H[:, 0].max() + 1e-9, step)
    ys = np.arange(H[:, 1].min(), H[:, 1].max() + 1e-9, step)
    X = np.stack(np.meshgrid(xs, ys), -1).reshape(-1, 2)
    X = X[_inside_hull(H, X)]
    for k, P in sets.items():
        P = np.asarray(P, float).reshape(-1, 2)
        if len(P) == 0 or len(X) == 0:
            out[k] = None
            continue
        best = np.full(len(X), np.inf)
        for i in range(0, len(P), 256):                              # 메모리 아끼게 나눠 잰다
            d = ((X[:, None, :] - P[None, i:i + 256, :]) ** 2).sum(axis=2).min(axis=1)
            best = np.minimum(best, d)
        out[k] = round(float(np.sqrt(best.max())), 1)
    return out


# ---------------------------------------------------------------- 묶음
def coverage(eps: list[dict], spec: dict, area: dict, ds_names: list[str]) -> tuple[dict, dict]:
    """에피소드(쓴 것) → (result["coverage"], 에피소드마다 칸 {id: {"cell_start", "cell_goal", "yaw_bin_start", "yaw_bin_goal"}})."""
    h = float(spec["scales"]["h_xy_mm"])
    at = area_tuple(area)
    C = hex_centers(at, h)
    nC = len(C)
    w = np.array([float(e.get("weight", 1.0)) for e in eps], float)
    ys = yaw_scheme(spec, [e[r].get("yaw") for e in eps for r in ("start", "goal")])
    Y = ys["bins"] if ys else 0
    per = {e["id"]: {} for e in eps}
    out = {"h": h, "centers": np.round(C, 1).tolist(), "n_cells": nC, "yaw_bins": Y, "yaw": ys}
    n_theory = n_hex((at[1] - at[0]) * (at[3] - at[2]), h) * max(1, Y)
    filled_xy, filled_y = {}, {}
    for role in ("start", "goal"):
        P = np.array([[e[role]["x"], e[role]["y"]] for e in eps], float).reshape(-1, 2)
        cells = cell_of(P, C, at)
        cnt = np.zeros(nC)
        n = np.zeros(nC, int)
        by = {d: np.zeros(nC, int) for d in ds_names}
        cy = set()
        for e, c, wi in zip(eps, cells, w):
            yb = yaw_bin(e[role].get("yaw"), ys)
            per[e["id"]][f"cell_{role}"] = int(c)
            if ys:
                per[e["id"]][f"yaw_bin_{role}"] = yb
            if c < 0:
                continue
            cnt[c] += wi
            n[c] += 1
            if e.get("dataset") in by:
                by[e["dataset"]][c] += 1
            if yb >= 0:
                cy.add((int(c), yb))
        out[role] = {"count": np.round(cnt, 3).tolist(), "n": n.tolist(), "count_by_ds": {d: v.tolist() for d, v in by.items()},
                     "reach": None, "outside": int((cells < 0).sum())}
        if ys:
            out[role]["cells_yaw"] = sorted([c, b] for c, b in cy)
        filled_xy[role] = int((n > 0).sum())
        filled_y[role] = len(cy)
    out.update(filled_start=filled_xy["start"], filled_goal=filled_xy["goal"], reach_start=None, reach_goal=None)
    if ys:
        out.update(filled_start_yaw=filled_y["start"], filled_goal_yaw=filled_y["goal"])
    out["n_theory"] = n_theory
    out["n_hex"] = n_hex((at[1] - at[0]) * (at[3] - at[2]), h)
    out["coupon_random"] = round(coupon(n_theory), 1)
    _n_min(out)
    if len(eps) >= 3:
        S = np.array([[e["start"]["x"], e["start"]["y"]] for e in eps], float)
        G = np.array([[e["goal"]["x"], e["goal"]["y"]] for e in eps], float)
        fd = fill_distance(np.r_[S, G], {"start": S, "goal": G})
        out["fill_dist_mm"] = {"start": fd["start"], "goal": fd["goal"]}
        out["hull_m2"] = fd["hull_m2"]
    else:
        out["fill_dist_mm"] = {"start": None, "goal": None}
        out["hull_m2"] = None
    return out, per


def _n_min(cov: dict) -> None:
    """reach(있으면) 기준 N_min · 채움 비율 다시 계산(제자리)."""
    nC = cov["n_cells"]
    vals, vals_y, basis = [], [], "all"
    for role in ("start", "goal"):
        n = np.asarray(cov[role]["n"], int)
        r = cov[role].get("reach")
        if r is not None:
            basis = "reach"
            r = np.asarray(r, bool)
            cov[f"reach_{role}"] = int(r.sum())
            filled_r = int(((n > 0) & r).sum())
            vals.append(int(r.sum()) - filled_r)
            if cov.get("yaw_bins"):
                fy = sum(1 for c, _ in cov[role].get("cells_yaw") or [] if 0 <= c < nC and r[c])
                vals_y.append(int(r.sum()) * cov["yaw_bins"] - fy)
        else:
            vals.append(nC - int((n > 0).sum()))
            if cov.get("yaw_bins"):
                vals_y.append(nC * cov["yaw_bins"] - cov.get(f"filled_{role}_yaw", 0))
    cov["n_min"] = max(vals) if vals else None
    cov["n_min_yaw"] = max(vals_y) if vals_y else None
    cov["n_min_basis"] = basis


def apply_reach(result: dict, reach_start=None, reach_goal=None) -> dict:
    """추천이 놓을 수 있는 칸(xy 칸마다 참·거짓, 길이 n_cells)을 알면 결과에 채우고 N_min·coverage 카드를 다시 계산한다."""
    cov = result["coverage"]
    for role, r in (("start", reach_start), ("goal", reach_goal)):
        if r is not None:
            if len(r) != cov["n_cells"]:
                raise ValueError(f"reach_{role} 길이 {len(r)} ≠ 칸 수 {cov['n_cells']}")
            cov[role]["reach"] = [bool(v) for v in r]
    _n_min(cov)
    from . import verdict
    result["cards"] = verdict.cards(result, result["spec"])
    return result
