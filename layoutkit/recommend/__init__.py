"""배치 추천 — 다음에 모을 배치(어디서 집어 어디에 놓을지, 고정물은 어디에)를 계산한다. 로봇은 안 움직인다.

    from layoutkit.recommend import recommend, reach
    rec = recommend([ds_v1, ds_v2], spec, result=None, n=3, seed=1)
    rec["options"][0]  →  {"label": "A", "start": {...}, "goal": {...}, "fixtures": [...], "discrete": {...},
                           "score": 1.23, "parts": {...}, "why_codes": ["empty_start_cell", ...], "cells": {...}}

수학은 FR5-AutoCollect fr5auto/rackrec.py(docs/RECOMMENDER.md 3절)를 그대로 쓰고, 받침에 묶인 부분만 spec 으로 바꿨다:
  배치 변수 = spec.layout(layout.py) · 놓을 수 있는 영역 = spec.constraints(constraints.py) · 카메라 = spec.cameras(camera.py).
result(analyze 결과)를 주면 그 칸(coverage.centers)을 쓰고 result["recommend"] 와 coverage 의 reach·n_min 을 채운다.
analyze 가 없어도 돈다(칸·상관은 여기서 계산 — 나중에 analyze 와 겹치는 계산은 정리).
고르기의 '빈 칸'은 언제나 (자리, 방향) 칸(rackrec 과 같은 정의)으로 센다 — result 의 count 는 reach·n_min 을 채울 때만 쓴다.

spec.recommend 에서 읽는 키(spec.DEFAULTS 밖은 코드 기본): n_cand 4096 · top_k 30 · temp 0.15 · seed · weights{alpha, beta, eta, gamma,
bad_view 0.8} · lambda 0.05 · rho_v2_n 10 · n_plan 20(final 훅 예산) · n_reach(4 × n_cand) · auto_strata true(near·adjacent 묶음 자동)
· rho_pairs(기본 spec.pairs 첫 짝) · target_dataset(기본 마지막 데이터셋).
카메라 항목의 policy_weight(정책 입력 칸 항 — rackrec img3 0.4) · goal_visible 의 bonus(rackrec vis3 0.2)도 점수에 들어간다.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

from .. import data as _data
from .. import spec as _spec
from . import constraints as CN
from . import layout as L
from . import sample as SM
from . import score as SC
from . import select as SL
from .select import queue_add, queue_load, queue_match, queue_new, queue_next, queue_recorded, queue_save, queue_sync  # noqa: F401

REACH_SEED = 20261102            # rackrec.Recommender.reach 와 같은 고정 시드
_REACH_CACHE: dict = {}

__all__ = ["recommend", "reach", "queue_new", "queue_load", "queue_save", "queue_add", "queue_sync", "queue_match", "queue_next",
           "queue_recorded"]


def _load_spec(spec):
    if isinstance(spec, dict) and all(k in spec for k in ("scales", "targets", "recommend")):
        return spec
    return _spec.load(spec)


def _episodes(datasets):
    """Dataset 목록 · 에피소드 목록 · 둘이 섞인 것 → (쓸 수 있는 에피소드, 데이터셋 이름 순서)."""
    eps, names = [], []
    for d in datasets or []:
        if isinstance(d, _data.Dataset):
            eps += d.usable()
            names.append(d.name)
        elif isinstance(d, dict) and _data.valid(d):
            eps.append(d)
            if d.get("dataset") not in names:
                names.append(d.get("dataset"))
    return eps, names


def _centers_of(result):
    cov = (result or {}).get("coverage") or {}
    c = cov.get("centers")
    return np.asarray(c, float).reshape(-1, 2) if c else None


def _key(sp, centers):
    k = {k_: sp.get(k_) for k_ in ("area", "scales", "layout", "constraints", "cameras", "near_mm")}
    k["n_reach"] = (sp.get("recommend") or {}).get("n_reach")
    k["n_cand"] = (sp.get("recommend") or {}).get("n_cand")
    k["centers"] = None if centers is None else np.round(centers, 4).tolist()
    return hashlib.sha1(json.dumps(k, sort_keys=True, default=str).encode()).hexdigest()


def _reach_full(sp, lay=None, centers=None) -> dict:
    """놓을 수 있는 칸: 고정 시드 Halton 후보(n_reach = 4 × n_cand, 기본 16384) 중 검사를 다 통과한 후보가 드는 칸.
    N_min 의 분모 — 영역 밖·창 밖·안 보이는 칸은 아무리 모아도 못 채운다(rackrec.Recommender.reach). 결과는 spec 마다 기억한다."""
    lay = lay or L.parse(sp)
    key = _key(sp, centers)
    if key in _REACH_CACHE:
        return _REACH_CACHE[key]
    rc = sp.get("recommend") or {}
    n = int(rc.get("n_reach") or 4 * int(rc.get("n_cand") or 4096))
    ctx = CN.Context(sp, lay)
    C = SM.sample(lay, n, np.random.default_rng(REACH_SEED))
    ok, drop, _ = CN.checks(C, ctx)
    cells = SC.Cells(lay, centers)
    gs, gid = cells.ids(C["g"], "start")
    qs, qid = cells.ids(C["q"], "goal")
    out = {"start": {int(c) for c in gid[ok] if c >= 0}, "goal": {int(c) for c in qid[ok] if c >= 0},
           "start_xy": {int(c) for c in gs[ok] if c >= 0}, "goal_xy": {int(c) for c in qs[ok] if c >= 0},
           "n_ok": int(ok.sum()), "n": n, "drop": drop, "skipped": list(ctx.skipped)}
    _REACH_CACHE[key] = out
    return out


def reach(spec):
    """놓을 수 있는 (자리, 방향) 칸 → (start 칸 집합, goal 칸 집합, 통과 후보 수, 후보 수). 칸 번호 = 육각 자리 칸 × 방향 칸 수 + 방향 칸."""
    sp = _load_spec(spec)
    R = _reach_full(sp)
    return R["start"], R["goal"], R["n_ok"], R["n"]


def _seed(seed, sp):
    if seed is None:
        seed = (sp.get("recommend") or {}).get("seed")
    if seed is None:
        seed = int(np.random.SeedSequence().entropy % (2 ** 31))
    return int(seed)


def _py(o):
    """JSON 으로 저장되게(numpy → 파이썬)."""
    if isinstance(o, dict):
        return {str(k): _py(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_py(v) for v in o]
    if isinstance(o, np.ndarray):
        return _py(o.tolist())
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        v = float(o)
        return v if np.isfinite(v) else None
    if isinstance(o, float) and not np.isfinite(o):
        return None
    return o


def recommend(datasets, spec, result=None, n=3, seed=None, queue=None, scene=None, goal=None, n_cand=None) -> dict:
    """다음 배치 선택지(A·B·C …) — docs/ARCHITECTURE.md 3절 recommend 모양.

    datasets: Dataset 목록(또는 에피소드 dict 목록). 마지막 데이터셋이 '지금 모으는 묶음'(상관 최소최대의 새 데이터셋 —
              spec.recommend.target_dataset 으로 바꿀 수 있다). 하나뿐이면 합친 상관만.
    result:   analyze() 결과(있으면 그 칸을 쓰고 result["recommend"]·coverage.reach·n_min 을 채운다).
    queue:    queue_new()/queue_load() 큐 — 시험 배치(한 번 정해 둔다)·지운 판의 목표(다시 A)·장면(scene)·bad_view.
    scene:    지금 탁자 장면(수고 계산) {"fixtures": [{x, y, yaw}], "start": [i, k], "obstacles": [[i, k]], "goal": [i, k]}.
    goal:     앞으로 모을 판 수(가까이 비율 맞추기) — 없으면 N_min.
    """
    sp = _load_spec(spec)
    rc = sp.get("recommend") or {}
    eps, names = _episodes(datasets)
    if sp.get("area") is None:                                       # 영역이 없으면 데이터 범위 + 여유(spec.area_from_data)
        sp = {**sp, "area": _spec.area_from_data(eps)}
    lay = L.parse(sp)
    ctx = CN.Context(sp, lay)
    target = rc.get("target_dataset") or (names[-1] if len(names) > 1 else None)
    fams = SC.families(sp, lay)
    D = SL.data_arrays(eps, lay, sp, fams, target)
    centers = _centers_of(result)
    cells = SC.Cells(lay, centers)
    R = _reach_full(sp, lay, centers)
    # 채운 칸·N_min — (자리, 방향) 칸(rackrec 과 같은 정의)
    _, ds_id = cells.ids(D["g"], "start") if D["n"] else (None, np.zeros(0, int))
    _, dg_id = cells.ids(D["q"], "goal") if D["n"] else (None, np.zeros(0, int))
    Fs, Fg = {int(c) for c in ds_id if c >= 0}, {int(c) for c in dg_id if c >= 0}
    n_min = max(0, len(R["start"] - Fs), len(R["goal"] - Fg))
    # 시험 배치: 큐에 있으면 그대로(한 번 정해 둔다), 없으면 k-center(시드 0)로 정하고 큐에 남긴다
    k_ho = int(sp.get("holdout") or 0)
    if queue is not None and queue.get("holdout"):
        hold = queue["holdout"]
    else:
        hold = SL.holdout(lay, ctx, D, k_ho, seed=0, n_cand=int(n_cand or rc.get("n_cand") or 4096)) if k_ho > 0 else []
        if queue is not None and hold:
            queue["holdout"] = hold
    sd = _seed(seed, sp)
    rng = np.random.default_rng(sd)
    out = SL.choose(lay, ctx, D, cells, fams, rng, sd, n_opt=int(n), n_cand=int(n_cand or rc.get("n_cand") or 4096), queue=queue,
                    scene=scene, n_min=n_min, goal=goal, holdout=hold)
    out["holdout"] = hold
    out["skipped_checks"] = list(dict.fromkeys(list(ctx.skipped) + list(R["skipped"])))
    out["cells"] = {"h": cells.h, "n_xy": cells.n_xy, "n_psi": [cells.n_psi_s, cells.n_psi_g],
                    "reach_start": len(R["start"]), "reach_goal": len(R["goal"]),
                    "reach_start_xy": len(R["start_xy"]), "reach_goal_xy": len(R["goal_xy"]),
                    "filled_start": len(Fs & R["start"]), "filled_goal": len(Fg & R["goal"]), "n_min": n_min,
                    "reach_n_ok": R["n_ok"], "reach_n": R["n"], "reach_drop": R["drop"]}
    out["n_episodes"] = D["n"]
    out["target_dataset"] = target
    # 분석 결과의 상관(있으면 나란히 — 계산이 어긋나면 화면에서 바로 보이게)
    for pr in ((result or {}).get("coupling") or {}).get("pairs") or []:
        first = (rc.get("rho_pairs") or (sp.get("pairs") or [["start.x", "goal.x"]])[:1])[0]
        if [pr.get("a"), pr.get("b")] == list(first) and pr.get("rho") is not None:
            out["rho_result"] = round(abs(float(pr["rho"])), 3)
    out = _py(out)
    if result is not None:
        _fill_result(result, out, R, D, cells)
    return out


def _fill_result(result, out, R, D, cells):
    """result["recommend"] 와 coverage 의 start/goal.reach · reach_start/goal · n_min 을 채운다.
    count 길이가 칸 수면 자리 칸 기준, 칸 수 × 방향 칸 수면 (자리, 방향) 칸 기준으로 맞춘다(analyze 가 어느 쪽을 쓰든)."""
    result["recommend"] = out
    cov = result.get("coverage")
    if not cov:
        # analyze 없이: 이 패키지에서 자리 칸 셈을 만든다(가중)
        cov = {"h": cells.h, "centers": np.round(cells.centers, 1).tolist(), "n_cells": cells.n_xy, "yaw_bins": 0}
        for side, X in (("start", D["g"]), ("goal", D["q"])):
            xy, _ = cells.ids(X, side) if D["n"] else (np.zeros(0, int), None)
            cnt = np.bincount(xy[xy >= 0], weights=D["w"][xy >= 0], minlength=cells.n_xy) if D["n"] else np.zeros(cells.n_xy)
            cov[side] = {"count": np.round(cnt, 3).tolist(), "count_by_ds": {}, "reach": None}
        result["coverage"] = cov
    # analyze 가 있으면 그 apply_reach(자리 칸 reach → N_min·카드 다시)를 쓴다 — 화면 카드와 숫자가 한 곳에서 나오게
    n_xy = cov.get("n_cells") or len(cov.get("centers") or [])
    applied = False
    if n_xy == cells.n_xy and result.get("spec") and all("n" in (cov.get(s) or {}) for s in ("start", "goal")):
        try:
            from ..analyze.coverage import apply_reach
            apply_reach(result, reach_start=[i in R["start_xy"] for i in range(n_xy)], reach_goal=[i in R["goal_xy"] for i in range(n_xy)])
            applied = True
        except Exception:                                            # analyze 가 없거나 모양이 다르면 아래에서 직접
            applied = False
    fill = {}
    for side in ("start", "goal") if not applied else ():
        c = cov.setdefault(side, {})
        cnt = c.get("count") or []
        if len(cnt) == cells.n_xy:
            rs = R[f"{side}_xy"]
        elif len(cnt) == cells.n_ids(side):
            rs = R[side]
        else:
            c["reach"] = None
            fill[side] = None
            continue
        c["reach"] = [i in rs for i in range(len(cnt))]
        filled = {i for i, v in enumerate(cnt) if v and v > 0}
        fill[side] = (len(rs), len(rs - filled))
    if not applied:
        cov["reach_start"] = fill["start"][0] if fill.get("start") else None
        cov["reach_goal"] = fill["goal"][0] if fill.get("goal") else None
        if fill.get("start") and fill.get("goal"):
            cov["n_min"] = max(0, fill["start"][1], fill["goal"][1])
            cov["n_min_basis"] = "reach"
    cov["reach_detail"] = {"xy_psi": {"start": len(R["start"]), "goal": len(R["goal"]), "n_psi": [cells.n_psi_s, cells.n_psi_g],
                                      "n_min": out["cells"]["n_min"]},
                           "n_ok": R["n_ok"], "n": R["n"], "seed": REACH_SEED}
