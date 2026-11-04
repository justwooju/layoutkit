"""지름길(출발 ↔ 목표 짝) — 가중 상관, 쪽 표, 출발만으로 목표 쪽 맞히기.

- pairs: spec.pairs 의 (출발 특징, 목표 특징)마다 가중 Pearson ρ(rackrec.wcorr 그대로) + 데이터셋마다(무게 없이).
- side: 첫 좌표 짝(start.x·goal.x 처럼 같은 축)의 축에서 기준선 split 을 정하고 출발 쪽 → 목표 쪽 2×2 표.
  기준선 = 출발 값 범위의 가운데 (min + max) / 2 — fr5auto rackrec.diagnose 와 같다(v1: x > 64.9 가 왼쪽).
  spec 에 side_split 을 숫자로 주면 그 값, "area_mid" 면 목표 영역 가운데.
  표 순서(화면 왼 → 오): 행 = 출발 쪽 [화면 왼쪽, 오른쪽], 열 = 목표 쪽 [화면 오른쪽, 왼쪽] — 대각선이 '건너편으로 옮김'.
  frame.x_left_positive 이면 화면 왼쪽 = 큰 값(hi). v1: [[44, 0], [4, 52]](왼쪽 44판 모두 오른쪽으로, 오른쪽 56판 중 52판 왼쪽으로).
  acc = 행마다 많은 쪽을 맞혔다고 칠 때 맞힘(출발 쪽만 알면 목표 쪽을 얼마나 아나).
- predict: 출발 xy 만으로 목표 쪽을 맞히는 최근접 이웃(k = 5, 다수결) leave-one-out 정확도. chance = 많은 쪽 비율.
"""
from __future__ import annotations

import math

import numpy as np

from ..spec import feature


def wcorr(x, y, w=None) -> float | None:
    """무게 상관(Pearson). 판이 3개 아래거나 분산 0 이면 None. rackrec 그대로."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    w = np.ones(len(x)) if w is None else np.asarray(w, float)
    if len(x) < 3 or w.sum() <= 0:
        return None
    mx, my = (w * x).sum() / w.sum(), (w * y).sum() / w.sum()
    cxy = (w * (x - mx) * (y - my)).sum()
    vx, vy = (w * (x - mx) ** 2).sum(), (w * (y - my) ** 2).sum()
    if vx <= 1e-12 or vy <= 1e-12:
        return None
    return float(cxy / math.sqrt(vx * vy))


def _vals(eps, name):
    out = []
    for e in eps:
        v = feature(e, name)
        try:
            out.append(float(v) if v is not None and not isinstance(v, bool) else (float(v) if isinstance(v, bool) else np.nan))
        except (TypeError, ValueError):
            out.append(np.nan)
    return np.asarray(out, float)


def pair_rho(eps, a, b, weighted=True):
    x, y = _vals(eps, a), _vals(eps, b)
    w = np.array([float(e.get("weight", 1.0)) for e in eps], float) if weighted else np.ones(len(eps))
    m = np.isfinite(x) & np.isfinite(y)
    return wcorr(x[m], y[m], w[m]) if m.sum() >= 3 else None


def side_axis(spec) -> str:
    for a, b in spec.get("pairs") or []:
        pa, pb = str(a).split("."), str(b).split(".")
        if len(pa) == 2 and len(pb) == 2 and pa[0] == "start" and pb[0] == "goal" and pa[1] == pb[1] and pa[1] in ("x", "y"):
            return pa[1]
    return "x"


def split_value(eps, spec, area, axis) -> float | None:
    s = spec.get("side_split", "range_mid")
    if isinstance(s, (int, float)):
        return float(s)
    v = np.array([e["start"][axis] for e in eps], float)
    if len(v) == 0:
        return None
    if s == "area_mid" and area:
        return 0.5 * (float(area[axis][0]) + float(area[axis][1]))
    return float((v.min() + v.max()) / 2.0)                         # rackrec.diagnose: 출발 좌우 범위의 가운데


def side_table(eps, spec, split, axis) -> dict:
    """출발 쪽 → 목표 쪽 표(모듈 설명의 순서)."""
    left_hi = bool((spec.get("frame") or {}).get("x_left_positive")) if axis == "x" else False
    s = np.array([e["start"][axis] for e in eps], float)
    g = np.array([e["goal"][axis] for e in eps], float)
    w = np.array([float(e.get("weight", 1.0)) for e in eps], float)
    hi_s, hi_g = s > split, g > split
    # 화면 왼쪽이 hi 인지 lo 인지
    sides = ["hi", "lo"] if left_hi else ["lo", "hi"]               # [화면 왼쪽, 화면 오른쪽]
    is_side = {"hi": lambda m: m, "lo": lambda m: ~m}
    rows, cols = sides, sides[::-1]
    T = [[int((is_side[r](hi_s) & is_side[c](hi_g)).sum()) for c in cols] for r in rows]
    Tw = [[float((w * (is_side[r](hi_s) & is_side[c](hi_g))).sum()) for c in cols] for r in rows]
    n = len(s)
    acc = (sum(max(r) for r in T) / n) if n else None
    tw = sum(sum(r) for r in Tw)
    acc_w = (sum(max(r) for r in Tw) / tw) if tw > 0 else None
    return {"split": None if split is None else round(split, 1), "split_exact": split, "axis": axis, "table": T,
            "rows": ["left", "right"], "cols": ["right", "left"], "left_is": sides[0],
            "acc": None if acc is None else round(acc, 3), "acc_w": None if acc_w is None else round(acc_w, 3),
            "n_cross": int(T[0][0] + T[1][1]), "n": n}


def knn_predict(eps, split, axis, k=5) -> dict:
    """출발 xy → 목표 쪽(> split) 최근접 이웃 leave-one-out 정확도."""
    n = len(eps)
    if n < 4 or split is None:
        return {"knn_acc": None, "chance": None, "k": k, "n": n}
    S = np.array([[e["start"]["x"], e["start"]["y"]] for e in eps], float)
    lab = np.array([e["goal"][axis] > split for e in eps], bool)
    kk = int(min(k, n - 1))
    D = ((S[:, None, :] - S[None, :, :]) ** 2).sum(axis=2)
    np.fill_diagonal(D, np.inf)
    nb = np.argsort(D, axis=1, kind="stable")[:, :kk]
    votes = lab[nb].mean(axis=1)
    pred = np.where(votes == 0.5, lab.mean() >= 0.5, votes > 0.5)   # 비기면 많은 쪽
    acc = float((pred == lab).mean())
    chance = float(max(lab.mean(), 1 - lab.mean()))
    return {"knn_acc": round(acc, 3), "chance": round(chance, 3), "k": kk, "n": n}


def coupling(eps: list[dict], spec: dict, area: dict, by_ds: dict) -> dict:
    """eps = 합친(쓴) 에피소드, by_ds = {데이터셋: 에피소드}."""
    pairs = []
    for a, b in spec.get("pairs") or []:
        r = pair_rho(eps, a, b)
        pairs.append({"a": a, "b": b, "rho": None if r is None else round(r, 3),
                      "rho_by_ds": {d: (None if (v := pair_rho(E, a, b, weighted=False)) is None else round(v, 3)) for d, E in by_ds.items()}})
    axis = side_axis(spec)
    split = split_value(eps, spec, area, axis)
    side = side_table(eps, spec, split, axis) if (split is not None and eps) else None
    pred = knn_predict(eps, split, axis)
    return {"pairs": pairs, "side": side, "predict": pred}
