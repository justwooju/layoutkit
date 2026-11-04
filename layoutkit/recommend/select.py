"""고르기 — 빈 칸 먼저 + 조건 단계적 완화 + top_k softmax(선택지 A·B·C) · 시험 배치(k-center) · 큐(목표·저장된 판으로 맞추기·지운 판 되돌리기).
rackrec.Recommender.recommend / holdout / queue_* 의 일반화(docs/RECOMMENDER.md 3.5·4.5·5.4).

순서: 후보(sample) → 검사(constraints) → 점수(score) → 빼기(시험 배치 근처·저장 판과 거의 같음·칸 밖) → 고르기 → (final 훅) → 선택지.
고르기:
  1. 후보마다 start 칸·goal 칸((자리, 방향))의 무게 수 n_s·n_g → 수준 ℓ = max(n_s − min n_s, n_g − min n_g) 가 가장 낮은 후보
  2. 이번 판 이동 종류: p_near = clip((near_share·(W + n_rem) − W_near) / n_rem, 0, 1) 로 '가까이' 뽑기
  3. |ρ| > rho_max 면 |ρ| 를 줄이는 후보만
  4. 없으면 차례로 푼다: (상관·이동·ℓ0) → (상관·ℓ0) → (ℓ0) → (ℓ+0.5) → (ℓ+1) → (제한 없음)
  5. 점수 위 top_k 에서 softmax(점수/temp)로 하나(A)
선택지: A = 위 · B = 같은 후보 중 점수 ≥ A − 0.1|A| 에서 수고 최소 · C = 가장 덜 찬 이산 칸에 드는 후보 중 점수 최고.
rackrec 과 다른 곳: 계획 검사(rackplan — 로봇 모델 필요)는 없다 → 같은 자리에 spec 의 final 훅을 돌린다(예산 recommend.n_plan).
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np

from . import score as SC
from .constraints import checks, final_check
from .layout import Layout, canon
from .sample import sample


# ================================================================ 데이터 → 배열
def ep_rec_id(e: dict):
    """에피소드가 따른 추천 목표 번호(있으면) — 어댑터마다 둔 자리가 달라 여러 곳을 본다."""
    for src in (e, e.get("discrete") or {}, e.get("extra") or {}, e.get("meta") or {}):
        v = src.get("rec_id") if isinstance(src, dict) else None
        if v:
            return str(v)
    return None


def _ep_psi(e, side, lay: Layout):
    """에피소드의 방향 특징: points = 그 자리 yaw · fixtures = 그 점이 든 고정물의 줄 방향.
    고정물 자세가 없으면 yaw + layout.episode_yaw_offset_deg(받침 spec: 잡는 손목 각 − 90° = 줄 방향, rackrec.ep_record)."""
    p = e.get(side) or {}
    if lay.kind == "points":
        if not lay.yaw_used(side):
            return 0.0
        return float(canon(p["yaw"], lay.period_s)) if "yaw" in p else None
    t = lay.start_type if side == "start" else lay.goal_type
    fx = [f for f in (e.get("fixtures") or []) if isinstance(f, dict) and "x" in f and "y" in f]
    if fx:
        best = None
        for f in fx:
            r = math.radians(float(f.get("yaw", 0.0)))
            hx = float(f["x"]) + t.offsets[:, 0] * math.cos(r) - t.offsets[:, 1] * math.sin(r)
            hy = float(f["y"]) + t.offsets[:, 0] * math.sin(r) + t.offsets[:, 1] * math.cos(r)
            d = float(np.min(np.hypot(hx - p["x"], hy - p["y"])))
            if best is None or d < best[0]:
                best = (d, float(f.get("yaw", 0.0)))
        if best is not None and best[0] <= max(t.hole_r, 0.5 * t.pitch, 15.0) + 10.0:
            return float(canon(best[1], t.period))
    if "yaw" in p:
        off = lay.yaw_offset
        return float(canon(p["yaw"] + (float(off) if off is not None else 0.0), t.period))
    return None


def _obstacle_slot(disc, lay: Layout):
    if not lay.obstacles:
        return -1
    if disc.get("obstacle_slot") is not None:
        try:
            return int(disc["obstacle_slot"])
        except (TypeError, ValueError):
            return -1
    arr = disc.get("arrangement")
    if isinstance(arr, str):
        sym = lay.obstacles[0].symbol
        if sym in arr:
            return arr.index(sym)
    return -1


def _int_or(v, d=-1):
    try:
        return int(v) if v is not None and not isinstance(v, bool) else d
    except (TypeError, ValueError):
        return d


def data_arrays(eps, lay: Layout, spec: dict, fams, target=None) -> dict:
    """에피소드(data.py 모양) → 특징 배열: g·q (E×3) · r · w · ks·kg·ky · near·adj · tgt(새 데이터셋) · 이산 칸 번호."""
    E = len(eps)
    g, q = np.zeros((E, 3)), np.zeros((E, 3))
    w = np.zeros(E)
    ks, kg, ky = np.full(E, -1), np.full(E, -1), np.full(E, -1)
    tgt = np.zeros(E, bool)
    rec = []
    for i, e in enumerate(eps):
        s, t = e["start"], e["goal"]
        ps, pg = _ep_psi(e, "start", lay), _ep_psi(e, "goal", lay)
        if ps is None:                                               # 모르면 그 자리 창 가운데(없으면 방향 칸 가운데)
            ps = (float(canon(lay.window.center(np.array(s["x"]), np.array(s["y"])), lay.period_s)) if lay.window is not None
                  else lay.yr_s.c0)
        if pg is None:
            pg = ps                                                  # rackrec: ψ_b 를 모르면 ψ_a
        g[i] = (s["x"], s["y"], ps)
        q[i] = (t["x"], t["y"], pg)
        w[i] = float(e.get("weight", 1.0))
        d = e.get("discrete") or {}
        ks[i], kg[i] = _int_or(d.get("start_slot")), _int_or(d.get("goal_slot"))
        ky[i] = _obstacle_slot(d, lay)
        tgt[i] = target is not None and e.get("dataset") == target
        rec.append(ep_rec_id(e))
    r = q[:, :2] - g[:, :2]
    near = np.hypot(r[:, 0], r[:, 1]) <= lay.near_mm
    adj = (ky >= 0) & (ks >= 0) & (np.abs(ks - ky) == 1)
    vals = {}
    for name, vv, _pi in fams:
        if name == "near":
            vals[name] = np.where(near, 0, 1)
        elif name == "adjacent":
            vals[name] = np.where(ky >= 0, np.where(adj, 0, 1), -1)   # rackrec: 노랑 자리를 아는 판만
        else:
            vals[name] = np.array([SC.value_index(vv, _feature(e, name)) for e in eps], int).reshape(E)
    return {"g": g, "q": q, "r": r, "w": w, "ks": ks, "kg": kg, "ky": ky, "near": near, "adj": adj, "tgt": tgt,
            "vals": vals, "ids": [str(e.get("id")) for e in eps], "rec": rec, "n": E}


def _feature(e, name):
    """이산 칸 값: discrete.<name> 먼저, 없으면 점 이름('start.x' 같은)."""
    d = e.get("discrete") or {}
    if name in d:
        return d[name]
    cur = e
    for part in name.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


# ================================================================ 후보의 이산 값
def cand_values(C, lay: Layout, fams):
    """후보마다 이산 칸 번호 {이름: (N,)} + near·adj 배열."""
    N = C["n"]
    rf = C["q"][:, :2] - C["g"][:, :2]
    near = np.hypot(rf[:, 0], rf[:, 1]) <= lay.near_mm
    if C["kind"] == "fixtures" and lay.obstacles:
        adj = np.abs(C["ks"] - C["obs"][:, 0]) == 1
    else:
        adj = np.zeros(N, bool)
    raw = {}
    if C["kind"] == "fixtures":
        names = np.array(lay.instance_names(), object)
        raw["start_slot"] = C["ks"]
        raw["goal_slot"] = C["kg"]
        raw["same_fixture"] = C["a"] == C["b"]
        raw["start_fixture"] = names[C["a"]]
        raw["goal_fixture"] = names[C["b"]]
    for v in lay.discrete:
        raw[v["name"]] = np.array(v["values"], object)[C["disc"][v["name"]]]
    out = {}
    for name, vv, _pi in fams:
        if name == "near":
            out[name] = np.where(near, 0, 1)
        elif name == "adjacent":
            out[name] = np.where(adj, 0, 1) if (C["kind"] == "fixtures" and lay.obstacles) else np.full(N, -1)
        elif name in raw:
            k = _map(vv, raw[name])
            if name == "goal_slot" and C["kind"] == "fixtures":
                # 칸이 하나뿐인 고정물(버림 통 등)의 칸은 칸 균형에 넣지 않는다(에피소드도 goal_slot = None)
                one = np.array([I.type.n_slots <= 1 for I in lay.instances])[C["b"]]
                k = np.where(one, -1, k)
            out[name] = k
        else:
            out[name] = np.full(N, -1)
    return out, near, adj


def _map(vals, arr):
    """후보 값 배열 → 이산 칸 번호(없는 값 −1). 값 종류가 적으니 고유값마다 한 번 찾는다."""
    arr = np.asarray(arr)
    if arr.dtype == object:
        keys = [str(x) for x in arr]
        lut = {}
        for kx, x in zip(keys, arr):
            if kx not in lut:
                lut[kx] = SC.value_index(vals, x)
        return np.array([lut[kx] for kx in keys], int).reshape(len(arr))
    out = np.full(len(arr), -1, int)
    for u in np.unique(arr):
        x = bool(u) if arr.dtype == bool else (int(u) if np.issubdtype(arr.dtype, np.integer) else float(u))
        out[arr == u] = SC.value_index(vals, x)
    return out


def arrangement(slots: dict, n: int) -> str:
    """고정물 위 물건 글자(예: Y○○R — 칸 0 부터). slots = {칸: 글자}."""
    s = ["○"] * n
    for k, ch in slots.items():
        if 0 <= int(k) < n:
            s[int(k)] = ch
    return "".join(s)


def layout_of(C, i, lay: Layout) -> dict:
    """후보 i → 사람이 놓을 배치(start · goal · fixtures · items · discrete · feat)."""
    g, q = C["g"][i], C["q"][i]
    out = {"start": {"x": round(float(g[0]), 1), "y": round(float(g[1]), 1)},
           "goal": {"x": round(float(q[0]), 1), "y": round(float(q[1]), 1)},
           "fixtures": [], "items": [], "discrete": {},
           "feat": {"g": [float(g[0]), float(g[1]), float(g[2])], "q": [float(q[0]), float(q[1]), float(q[2])]}}
    if lay.kind == "points":
        if lay.yaw_used("start"):
            out["start"]["yaw"] = round(float(g[2]), 1)
        if lay.yaw_used("goal"):
            out["goal"]["yaw"] = round(float(q[2]), 1)
    else:
        names = lay.instance_names()
        a, b, ks, kg = int(C["a"][i]), int(C["b"][i]), int(C["ks"][i]), int(C["kg"][i])
        out["start"].update({"yaw": round(float(g[2]), 1), "fixture": names[a], "slot": ks})
        out["goal"].update({"yaw": round(float(q[2]), 1), "fixture": names[b], "slot": kg})
        for j, I in enumerate(lay.instances):
            out["fixtures"].append({"name": I.name, "type": I.type.name, "x": round(float(C["P"][i, j, 0]), 1),
                                    "y": round(float(C["P"][i, j, 1]), 1), "yaw": round(float(C["yaw"][i, j]), 1),
                                    "fixed": I.pose is not None})
        out["items"].append({"name": lay.start.name, "role": "start", "fixture": names[a], "slot": ks})
        sy = {ks: lay.start.symbol}
        for j, o in enumerate(lay.obstacles):
            k = int(C["obs"][i, j])
            out["items"].append({"name": o.name, "role": "obstacle", "fixture": names[a], "slot": k})
            sy[k] = o.symbol
        out["items"].append({"name": lay.goal.name, "role": "goal", "fixture": names[b], "slot": kg})
        out["discrete"].update({"start_slot": ks, "goal_slot": kg if lay.instances[b].type.n_slots > 1 else None,
                                "start_fixture": names[a], "goal_fixture": names[b], "same_fixture": a == b,
                                "arrangement": arrangement(sy, lay.start_type.n_slots)})
        if lay.obstacles:
            out["discrete"]["adjacent"] = abs(ks - int(C["obs"][i, 0])) == 1
    for v in lay.discrete:
        out["discrete"][v["name"]] = v["values"][int(C["disc"][v["name"]][i])]
    out["move_mm"] = round(float(np.hypot(q[0] - g[0], q[1] - g[1])), 1)
    out["discrete"]["near"] = bool(out["move_mm"] <= lay.near_mm)
    return out


# ================================================================ 고르기
def _softmax_pick(rng, sc, temp):
    if temp > 0:
        p = np.exp((sc - sc.max()) / temp)
        p /= p.sum()
        return int(rng.choice(len(sc), p=p)), p
    p = np.zeros(len(sc))
    p[0] = 1.0
    return 0, p


def choose(lay: Layout, ctx, D: dict, cells: SC.Cells, fams, rng, seed: int, n_opt=3, n_cand=4096, queue=None, scene=None,
           n_min=None, goal=None, holdout=None) -> dict:
    sp = ctx.spec
    rc = sp.get("recommend") or {}
    wt = dict(rc.get("weights") or {})
    tg = sp.get("targets") or {}
    h, hp = cells.h, (lay.h_psi if lay.use_yaw else np.inf)
    per_s, per_g = lay.period_s, lay.period_g
    out = {"options": [], "skipped_checks": ctx.skipped, "n_cand": int(n_cand), "n_feasible": 0, "n_ok": 0, "drop": {},
           "seed": int(seed), "weights": wt, "why": []}
    C = sample(lay, n_cand, rng)
    ok, drop, vis = checks(C, ctx)
    out["drop"] = drop
    out["n_feasible"] = int(ok.sum())
    gf, qf = C["g"].copy(), C["q"].copy()
    if not lay.yaw_used("start"):
        gf[:, 2] = 0.0
    if not lay.yaw_used("goal"):
        qf[:, 2] = 0.0
    rf = qf[:, :2] - gf[:, :2]
    if not ok.any():
        out["why"].append("no_feasible")
        return out
    w = D["w"]
    lam = float(rc.get("lambda", 0.05))
    sg = SC.gp_var(SC.d2_xyp(D["g"], D["g"], h, hp, per_s), SC.d2_xyp(gf, D["g"], h, hp, per_s), w, lam)
    sq = SC.gp_var(SC.d2_xyp(D["q"], D["q"], h, hp, per_g), SC.d2_xyp(qf, D["q"], h, hp, per_g), w, lam)
    sr = SC.gp_var(SC.d2_xy(D["r"], D["r"], h), SC.d2_xy(rf, D["r"], h), w, lam)
    cv, near, adj = cand_values(C, lay, fams)
    st_term, fill, per = SC.strata_term(fams, D["vals"], w, cv)
    # 상관 짝: recommend.rho_pairs 또는 spec.pairs 첫 짝(rackrec 은 빨강 x ↔ 링 x 하나) — 'start.x' → 축 0
    ax = {"x": 0, "y": 1}
    prs = rc.get("rho_pairs") or (sp.get("pairs") or [["start.x", "goal.x"]])[:1]
    pairs = [(ax[a.split(".")[1]], ax[b.split(".")[1]]) for a, b in prs if a.split(".")[-1] in ax and b.split(".")[-1] in ax]
    cp = SC.coupling_term(D, gf, qf, pairs, int(rc.get("rho_v2_n", 10)))
    d_rho, rho1, rho0 = cp["d_rho"], cp["rho1"], cp["rho0"]
    # 정책 입력 칸(카메라마다 policy_weight) — start·goal 이 아직 안 든 화면 칸 우대(rackrec img_term)
    img_term = np.zeros(C["n"])
    img_info = {}
    zs, zg = lay.start_z(), lay.goal_z()
    for name, cam in ctx.cams.items():
        wc = float(cam.policy_weight)
        if wc <= 0:
            continue
        cr = cam.policy_cell(np.c_[gf[:, :2], np.full(C["n"], zs)])
        cq_ = cam.policy_cell(np.c_[qf[:, :2], np.full(C["n"], zg)])
        dr_ = cam.policy_cell(np.c_[D["g"][:, :2], np.full(D["n"], zs)]) if D["n"] else np.zeros(0, int)
        dq_ = cam.policy_cell(np.c_[D["q"][:, :2], np.full(D["n"], zg)]) if D["n"] else np.zeros(0, int)
        nimg = cam.img_grid ** 2
        cnt_r = np.bincount(dr_[dr_ >= 0], weights=w[dr_ >= 0], minlength=nimg)
        cnt_q = np.bincount(dq_[dq_ >= 0], weights=w[dq_ >= 0], minlength=nimg)
        tr_ = np.where(cr >= 0, 1.0 / (1.0 + cnt_r[np.maximum(cr, 0)]), 0.0)
        tq_ = np.where(cq_ >= 0, 1.0 / (1.0 + cnt_q[np.maximum(cq_, 0)]), 0.0)
        img_term += wc * 0.5 * (tr_ + tq_)
        img_info[name] = (cr, cq_, cnt_r, cnt_q)
    vis_term = np.zeros(C["n"])
    for c in sp.get("constraints") or []:
        if c.get("type") == "goal_visible" and c.get("bonus") and f"vis:{c.get('camera')}" in vis:
            vis_term += float(c["bonus"]) * (np.nan_to_num(vis[f"vis:{c.get('camera')}"]) >= float(c.get("min_frac", 0.7)))
    eff, eff_txt = SC.effort(C, scene if scene is not None else (queue or {}).get("scene"), lay)
    bad_pen = SC.bad_view_penalty(C, (queue or {}).get("bad_view") or [], h, lay.h_psi, per_s)
    a_, b_, e_, gm_ = float(wt.get("alpha", 0.5)), float(wt.get("beta", 0.3)), float(wt.get("eta", 1.0)), float(wt.get("gamma", 0.15))
    score = (sg + sq + a_ * sr + b_ * st_term - e_ * d_rho - gm_ * eff + img_term + vis_term
             - float(wt.get("bad_view", 0.8)) * bad_pen)
    # ---- 빼기: 시험 배치 근처(start·goal 모두 0.5 h 안) · 저장 판과 거의 같음(같은 칸 번호 + 0.5 h 안)
    excl = np.zeros(C["n"], bool)
    d_ho = np.full(C["n"], np.inf)
    ho = holdout or []
    if ho:
        Hg = np.array([x["feat"]["g"] for x in ho], float)
        Hq = np.array([x["feat"]["q"] for x in ho], float)
        dg, dq = np.sqrt(SC.d2_xyp(gf, Hg, h, hp, per_s)), np.sqrt(SC.d2_xyp(qf, Hq, h, hp, per_g))
        excl |= ((dg < 0.5) & (dq < 0.5)).any(axis=1)
        d_ho = np.sqrt(dg ** 2 + dq ** 2).min(axis=1)
    drop["near_holdout"] = int((ok & excl).sum())
    if D["n"]:
        dg, dq = np.sqrt(SC.d2_xyp(gf, D["g"], h, hp, per_s)), np.sqrt(SC.d2_xyp(qf, D["q"], h, hp, per_g))
        if C["kind"] == "fixtures":
            same = (C["ks"][:, None] == D["ks"][None, :]) & (C["kg"][:, None] == D["kg"][None, :])
        else:
            same = np.ones((C["n"], D["n"]), bool)
        dup = ((dg < 0.5) & (dq < 0.5) & same).any(axis=1)
        drop["dup_saved"] = int((ok & ~excl & dup).sum())
        excl |= dup
    cs_xy, cs_id = cells.ids(gf, "start")
    cg_xy, cg_id = cells.ids(qf, "goal")
    good = ok & ~excl & (cs_id >= 0) & (cg_id >= 0)
    out["n_ok"] = int(good.sum())
    if not good.any():
        out["why"].append("all_near_holdout_or_dup")
        return out
    # ---- 고르기
    ds_xy, ds_id = cells.ids(D["g"], "start") if D["n"] else (np.zeros(0, int), np.zeros(0, int))
    dg_xy, dg_id = cells.ids(D["q"], "goal") if D["n"] else (np.zeros(0, int), np.zeros(0, int))
    cnt_s = np.bincount(ds_id[ds_id >= 0], weights=w[ds_id >= 0], minlength=cells.n_ids("start"))
    cnt_g = np.bincount(dg_id[dg_id >= 0], weights=w[dg_id >= 0], minlength=cells.n_ids("goal"))
    ns, ng = cnt_s[np.maximum(cs_id, 0)], cnt_g[np.maximum(cg_id, 0)]
    # 자리 칸(xy)만 센 수 — 이유 코드(화면의 칸 지도는 자리 칸)
    cnt_sx = np.bincount(ds_xy[ds_xy >= 0], weights=w[ds_xy >= 0], minlength=cells.n_xy)
    cnt_gx = np.bincount(dg_xy[dg_xy >= 0], weights=w[dg_xy >= 0], minlength=cells.n_xy)
    ns_xy, ng_xy = cnt_sx[np.maximum(cs_xy, 0)], cnt_gx[np.maximum(cg_xy, 0)]
    ms, mg = float(ns[good].min()), float(ng[good].min())
    lev = np.maximum(ns - ms, ng - mg)
    wsum = float(w.sum())
    n_rem = max(1, int(goal if goal is not None else (n_min if n_min is not None else 1)))
    near_share = float(tg.get("near_share", 0.25))
    w_near = float((w * D["near"]).sum())
    p_near = float(np.clip(max(0.0, near_share * (wsum + n_rem) - w_near) / n_rem, 0.0, 1.0))
    want_near = bool(rng.random() < p_near)
    rho_max = float(tg.get("rho_max", 0.3))
    rho_bad = rho0 is not None and rho0 > rho_max
    c_rho = cp["c_ok"] if rho_bad else np.ones(C["n"], bool)
    c_near = near == want_near
    relax, sel = [], None
    for step, (use_rho, use_near, dl) in enumerate(((True, True, 0.0), (True, False, 0.0), (False, False, 0.0),
                                                    (False, False, 0.5), (False, False, 1.0), (False, False, 1e9))):
        m = good & (lev <= float(lev[good].min()) + dl + 1e-9)
        if use_rho:
            m &= c_rho
        if use_near:
            m &= c_near
        if m.any():
            sel = m
            if not use_near and step >= 1:
                relax.append("near" if want_near else "far")
            if not use_rho and rho_bad:
                relax.append("coupling")
            if dl > 0:
                relax.append(f"level+{dl:g}")
            break
    n_sel = int(sel.sum())
    temp, top_k = float(rc.get("temp", 0.15)), int(rc.get("top_k", 30))
    pool = np.flatnonzero(sel)
    pool = pool[np.argsort(-score[pool], kind="stable")][:max(1, top_k)]
    budget = [int(rc.get("n_plan", 20))]
    checked = {}

    def final_ok(i):
        """final 훅(없으면 늘 통과) — 예산 안에서만. None = 예산 다 씀."""
        if not ctx.final_hooks:
            return True
        if i in checked:
            return checked[i][0]
        if budget[0] <= 0:
            return None
        budget[0] -= 1
        res = final_check(layout_of(C, i, lay), ctx)
        checked[i] = res
        return res[0]

    def first_ok(cands):
        for i in cands:
            if not good[i]:
                continue
            r = final_ok(int(i))
            if r is None:
                return None
            if r:
                return int(i)
        return None

    iA, pA = None, None
    live = list(pool)
    while live:
        j, p = _softmax_pick(rng, score[live], temp)
        i = int(live[j])
        r = final_ok(i)
        if r is None:
            break
        if r:
            iA, pA = i, float(p[j])
            break
        live.pop(j)
    parts = {"var_start": sg, "var_goal": sq, "var_move": sr, "strata": st_term, "coupling": d_rho, "effort": eff,
             "img": img_term, "vis": vis_term, "bad_view": bad_pen}
    sctx = {"C": C, "lay": lay, "parts": parts, "score": score, "ns": ns, "ng": ng, "ns_xy": ns_xy, "ng_xy": ng_xy,
            "cs": (cs_xy, cs_id), "cg": (cg_xy, cg_id),
            "near": near, "cv": cv, "per": per, "fams": fams, "rho0": rho0, "rho1": rho1, "d_ho": d_ho, "vis": vis,
            "eff_txt": eff_txt, "eff": eff, "sel": sel, "near_share": near_share, "near_now": (w_near / wsum) if wsum > 0 else 0.0,
            "relax": relax, "img": img_info}
    opts = []
    keep = queue_next(queue) if queue else None
    if keep:
        o = dict(keep.get("option") or {})
        o.update({"label": "A", "how": "keep", "target_id": keep["id"], "why_codes": ["retry_deleted"], "from_keep": True})
        opts.append(o)
    if iA is not None:
        opts.append(_option(sctx, iA, "A2" if keep else "A", "softmax", p=pA, checked=checked.get(iA)))
    taken = {iA} if iA is not None else set()
    if n_opt >= 2 and (iA is not None or pool.size):
        ref = float(score[iA]) if iA is not None else float(score[pool[0]])
        cand_b = np.flatnonzero(sel & (score >= ref - 0.1 * abs(ref)))
        cand_b = cand_b[np.argsort(eff[cand_b], kind="stable")]
        posA = _pose_key(C, iA) if iA is not None else None
        iB = first_ok([i for i in cand_b if i not in taken and _pose_key(C, i) != posA][:8])
        if iB is not None:
            opts.append(_option(sctx, iB, "B", "low_effort", checked=checked.get(iB)))
            taken.add(iB)
    if n_opt >= 3:
        fill.sort(key=lambda f: (f[0], f[1], f[2]))
        for fr, name, k, val, cnt, tgt in fill:
            m = good & (cv[name] == k)
            for j_ in taken:
                m[j_] = False
            if not m.any():
                continue
            iC = first_ok(list(np.flatnonzero(m)[np.argsort(-score[m], kind="stable")])[:6])
            if iC is not None:
                o = _option(sctx, iC, "C", "strata", checked=checked.get(iC))
                o["strata_fill"] = {"name": name, "value": val, "count": round(float(cnt), 2), "target": round(float(tgt), 2)}
                if "balances_strata" not in o["why_codes"]:
                    o["why_codes"].append("balances_strata")
                opts.append(o)
                taken.add(iC)
                break
    # 더 달라면(n > 3): 남은 풀에서 softmax 로 겹치지 않게
    lab = "DEFGHIJKLMNOPQRSTUVWXYZ"
    rest = [int(i) for i in pool if int(i) not in taken]
    while len([o for o in opts if o["label"] != "A2"]) < n_opt and rest:
        j, p = _softmax_pick(rng, score[rest], temp)
        i = rest.pop(j)
        if final_ok(i):
            k = len([o for o in opts if o["label"] not in ("A", "A2", "B", "C")])
            opts.append(_option(sctx, i, lab[k] if k < len(lab) else f"X{k}", "softmax", p=float(p[j]), checked=checked.get(i)))
            taken.add(i)
    out["options"] = opts
    out["select"] = {"n_sel": n_sel, "pool": int(len(pool)), "temp": temp, "p": pA, "want_near": want_near, "p_near": round(p_near, 3),
                     "rho_bad": bool(rho_bad), "relax": relax, "level": float(lev[good].min()), "n_rem": n_rem,
                     "n_final_checked": len(checked)}
    if ctx.final_hooks:
        out["final_fail"] = [r[1][:1] for r in checked.values() if not r[0]][:5]
    if not opts:
        out["why"].append("final_check_failed" if ctx.final_hooks else "no_option")
    out["rho0"] = None if rho0 is None else round(float(rho0), 3)
    out["near_share"] = round(sctx["near_now"], 3)
    return out


def _pose_key(C, i):
    if i is None:
        return None
    if C["kind"] == "fixtures":
        return tuple(np.round(C["P"][i].ravel(), 6).tolist())
    return tuple(np.round(np.r_[C["g"][i, :2], C["q"][i, :2]], 6).tolist())


def _r(v, k=3):
    v = float(v)
    return round(v, k) if np.isfinite(v) else None


def _option(s, i, label, how, p=None, checked=None) -> dict:
    C, lay, parts = s["C"], s["lay"], s["parts"]
    o = {"label": label, "how": how}
    o.update(layout_of(C, i, lay))
    o["score"] = _r(s["score"][i])
    o["parts"] = {k: _r(v[i]) for k, v in parts.items()}
    o["cells"] = {"start": int(s["cs"][0][i]), "goal": int(s["cg"][0][i]), "start_id": int(s["cs"][1][i]), "goal_id": int(s["cg"][1][i]),
                  "start_count": _r(s["ns"][i], 2), "goal_count": _r(s["ng"][i], 2),
                  "start_xy_count": _r(s["ns_xy"][i], 2), "goal_xy_count": _r(s["ng_xy"][i], 2)}
    if p is not None:
        o["p"] = round(float(p), 3)
    if s["rho0"] is not None:
        o["rho"] = {"now": _r(s["rho0"]), "after": _r(s["rho1"][i])}
    if np.isfinite(s["d_ho"][i]):
        o["holdout_dist_h"] = _r(s["d_ho"][i], 2)
    v = {}
    for k, arr in s["vis"].items():
        kind, cam = k.split(":", 1)
        if kind in ("vis", "minor"):
            v.setdefault(cam, {})["goal_frac" if kind == "vis" else "goal_minor_px"] = _r(arr[i], 2)
    if v:
        o["vis"] = v
    if s["img"]:
        o["policy_cells"] = {cam: {"start": int(cr[i]), "goal": int(cq[i]), "start_empty": bool(cr[i] >= 0 and cnr[cr[i]] == 0),
                                   "goal_empty": bool(cq[i] >= 0 and cnq[cq[i]] == 0)} for cam, (cr, cq, cnr, cnq) in s["img"].items()}
    o["effort_text"] = s["eff_txt"][i]
    if checked is not None:
        o["final_check"] = {"ok": bool(checked[0]), "why": checked[1]}
    if s["relax"]:
        o["relax"] = list(s["relax"])
    o["why_codes"], o["why_args"] = why_codes(s, i, how)
    return o


def why_codes(s, i, how):
    """사람이 읽을 이유 코드(화면이 i18n 으로 글을 만든다 — report/i18n.WHY).
    empty_start_cell / empty_goal_cell = 그 자리 칸(xy)이 비었다 · new_yaw = 자리 칸에는 판이 있는데 이 방향 칸은 비었다 ·
    lowers_coupling · adds_near · balances_strata · low_effort(장면을 알 때만) · far_from_data(σ² ≥ 0.5) · relaxed(조건을 풀어 고름) ·
    retry_deleted(지운 판의 목표 — 큐)."""
    codes, args = [], {}
    sx, gx = s["ns_xy"][i], s["ng_xy"][i]
    if sx == 0:
        codes.append("empty_start_cell")
    if gx == 0:
        codes.append("empty_goal_cell")
    if (sx > 0 and s["ns"][i] == 0) or (gx > 0 and s["ng"][i] == 0):
        codes.append("new_yaw")
        args["new_yaw"] = [r for r, ok in (("start", sx > 0 and s["ns"][i] == 0), ("goal", gx > 0 and s["ng"][i] == 0)) if ok]
    if s["rho0"] is not None and s["parts"]["coupling"][i] < -1e-9:
        codes.append("lowers_coupling")
        args["rho"] = [_r(s["rho0"]), _r(s["rho1"][i])]
    if s["near"][i] and s["near_now"] < s["near_share"]:
        codes.append("adds_near")
    low = []
    for name, vals, pi in s["fams"]:
        k = int(s["cv"][name][i])
        if k < 0 or name in ("near",):
            continue
        cnt, pis, tot = s["per"][name]
        ratio = cnt / np.maximum(pis * max(tot, 1.0), 1e-9)
        if ratio[k] <= ratio.min() + 1e-9 and ratio[k] < 1.0:
            low.append(f"{name}={vals[k]}")
    if low:
        codes.append("balances_strata")
        args["strata"] = low
    eff = s["eff"]
    if np.any(eff > 0) and (how == "low_effort" or eff[i] <= float(eff[s["sel"]].min()) + 1e-9):   # 장면을 모르면(수고 0) 안 붙인다
        codes.append("low_effort")
    far = [r for r, k in (("start", "var_start"), ("goal", "var_goal")) if s["parts"][k][i] >= 0.5]
    if far:
        codes.append("far_from_data")
        args["far_from_data"] = far
    if s["relax"]:
        codes.append("relaxed")
        args["relaxed"] = list(s["relax"])
    return codes, args


# ================================================================ 시험 전용 배치(k-center)
def holdout(lay: Layout, ctx, D: dict, k: int, seed=0, n_cand=4096) -> list[dict]:
    """k-center 탐욕법[Gonzalez 1985]: 이미 있는 판에서, 그리고 서로 가장 먼 놓을 수 있는 배치를 차례로. 거리 = √(d_g² + d_q²). rackrec.holdout."""
    k = int(k or 0)
    if k <= 0:
        return []
    rng = np.random.default_rng(seed)
    h, hp = lay.h_xy, (lay.h_psi if lay.use_yaw else np.inf)
    C = sample(lay, int(n_cand), rng)
    ok, _, _ = checks(C, ctx)
    idx = np.flatnonzero(ok)
    if len(idx) == 0:
        return []
    gf, qf = C["g"][idx].copy(), C["q"][idx].copy()
    if not lay.yaw_used("start"):
        gf[:, 2] = 0.0
    if not lay.yaw_used("goal"):
        qf[:, 2] = 0.0
    ps, pg = lay.period_s, lay.period_g
    if D["n"]:
        dmin = np.sqrt(SC.d2_xyp(gf, D["g"], h, hp, ps) + SC.d2_xyp(qf, D["q"], h, hp, pg)).min(axis=1)
    else:
        dmin = np.full(len(idx), 1e9)
    chosen, bad = [], set()
    while len(chosen) < k:
        taken = set(bad) | {c for c, _ in chosen}
        cand = np.array([-np.inf if j in taken else dmin[j] for j in range(len(idx))])
        j = int(np.argmax(cand))
        if not np.isfinite(cand[j]):
            break
        lo = layout_of(C, int(idx[j]), lay)
        okf, why = final_check(lo, ctx) if ctx.final_hooks else (True, [])
        if not okf:
            bad.add(j)
            if len(bad) > 4 * k:
                break
            continue
        chosen.append((j, lo))
        dj = np.sqrt(SC.d2_xyp(gf, gf[j:j + 1], h, hp, ps)[:, 0] + SC.d2_xyp(qf, qf[j:j + 1], h, hp, pg)[:, 0])
        dmin = np.minimum(dmin, dj)
    out = []
    for n_, (j, lo) in enumerate(chosen):
        lo = dict(lo)
        lo["feat"] = {"g": gf[j].tolist(), "q": qf[j].tolist()}
        out.append({"id": f"T{n_ + 1:02d}", **lo})
    return out


# ================================================================ 큐 — 기준은 언제나 저장된 에피소드(지운 판은 없다)
def queue_new() -> dict:
    return {"version": 1, "holdout": [], "targets": [], "next_id": 1, "current": None, "scene": None, "bad_view": []}


def queue_load(path) -> dict:
    try:
        q = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(q, dict):
            base = queue_new()
            base.update(q)
            return base
    except (OSError, ValueError):
        pass
    return queue_new()


def queue_save(path, q) -> Path:
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(q, ensure_ascii=False, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)),
                   encoding="utf-8")
    tmp.replace(p)
    return p


def queue_add(q: dict, opt: dict, t=None) -> dict:
    """추천 선택지 하나 → 목표(R0001 …). 수집 쪽은 이 번호를 에피소드에 남기면(rec_id) 맞추기가 정확하다."""
    tid = f"R{int(q.get('next_id') or 1):04d}"
    q["next_id"] = int(q.get("next_id") or 1) + 1
    keep = {k: v for k, v in opt.items() if k not in ("effort_text",)}
    tgt = {"id": tid, "option": keep, "label": opt.get("label"), "t": t or time.strftime("%Y-%m-%dT%H:%M:%S"),
           "status": "pending", "recorded": 0, "kept": 0}
    q.setdefault("targets", []).append(tgt)
    q["current"] = tid
    return tgt


def queue_recorded(q: dict, tid: str) -> None:
    """그 목표로 한 판을 녹화했다(저장 여부와 무관) — 나중에 저장된 판이 없으면 '다시 모을 목표'가 된다."""
    for t in q.get("targets") or []:
        if t["id"] == tid:
            t["recorded"] = int(t.get("recorded") or 0) + 1


def _target_xy(t):
    o = t.get("option") or {}
    f = o.get("feat") or {}
    if f.get("g") and f.get("q"):
        return f["g"][:2], f["q"][:2]
    return [o["start"]["x"], o["start"]["y"]], [o["goal"]["x"], o["goal"]["y"]]


def queue_match(q: dict, episodes, tol_mm=30.0) -> dict:
    """저장된 판 → 목표: rec_id 가 있으면 그것, 없으면 놓인 자리로(start·goal 둘 다 tol_mm 안 · 가까운 순 · 목표 하나에 판 하나 먼저).
    반환 {에피소드 id: 목표 id}."""
    tg = q.get("targets") or []
    ids = {t["id"] for t in tg}
    out, rest = {}, []
    for e in episodes:
        rid = ep_rec_id(e)
        if rid and rid in ids:
            out[str(e.get("id"))] = rid
        elif not rid:
            rest.append(e)
    if rest and tg:
        TX = [_target_xy(t) for t in tg]
        pairs = []
        for e in rest:
            for t, (gs, gg) in zip(tg, TX):
                d = max(math.hypot(e["start"]["x"] - gs[0], e["start"]["y"] - gs[1]), math.hypot(e["goal"]["x"] - gg[0], e["goal"]["y"] - gg[1]))
                if d <= tol_mm:
                    pairs.append((d, str(e.get("id")), t["id"]))
        used_t = set(out.values())
        for d, eid, tid in sorted(pairs):
            if eid in out or tid in used_t:
                continue
            out[eid] = tid
            used_t.add(tid)
    return out


def queue_sync(q: dict, episodes, per_pose=1, tol_mm=30.0) -> dict:
    """저장된 판에서 다시 계산: 목표마다 맞는 판 수 · 실제 놓인 자리. 판을 지우면 그 목표는 'pending' 으로 돌아간다(rackrec.queue_sync).
    반환 {목표 id: 상태}."""
    m = queue_match(q, episodes, tol_mm)
    by = {}
    eps = {str(e.get("id")): e for e in episodes}
    for eid, tid in m.items():
        by.setdefault(tid, []).append(eps[eid])
    summ = {}
    for t in q.get("targets") or []:
        if t.get("status") == "collected":
            t["kept_once"] = True                                     # 한 번 저장됐던 목표(지금 pending 이면 지운 판의 목표)
        got = by.get(t["id"], [])
        t["kept"] = len(got)
        t["status"] = "collected" if len(got) >= int(per_pose) else "pending"
        t["actual"] = [{"id": e.get("id"), "start": e.get("start"), "goal": e.get("goal")} for e in got]
        summ[t["id"]] = t["status"]
    cur = q.get("current")
    if cur and summ.get(cur) == "collected":
        q["current"] = None
    return summ


def queue_next(q: dict | None) -> dict | None:
    """다시 모을 목표: 녹화했거나 한 번 저장됐는데 지금 저장된 판이 없는(지운·버린) 목표 중 가장 오래된 것(rackrec.pending_again)."""
    for t in (q or {}).get("targets") or []:
        if t.get("status") == "pending" and (t.get("recorded") or t.get("kept_once")) and not t.get("skip"):
            return t
    return None
