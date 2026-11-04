#!/usr/bin/env python3
"""배치 추천 시험(표준 라이브러리 + numpy) — python3 tests/test_recommend.py

1. 카메라 투영이 fr5auto camera.Cam(flip) 과 0.01 px 안으로 같다(적어 둔 기준 값 · fr5auto 가 옆에 있으면 무작위 점도)
2. 받침 spec(실물 3인칭, 손목 없음): 후보 16384개(시드 20261102) 통과 121 · 놓을 수 있는 칸 60 · 41(fr5auto 와 같다)
3. 가짜 세계(사람이 추천 자리에 ±10 mm·±5° 로 놓음) 40판: 추천이 무작위보다 칸을 많이 채운다
4. 시험 배치(k-center) 근처(start·goal 모두 0.5 h 안)를 피한다
5. 큐: 저장 → 지움 → 같은 목표가 A 로 다시 · 놓인 자리로 맞추기
6. result 를 주면 coverage.reach·n_min·recommend 를 채운다
fr5auto 비교: 환경 변수 FR5AUTO_DIR(없으면 이 저장소 옆 FR5-AutoCollect)이 있으면 같은 후보까지 맞춰 본다.
"""
from __future__ import annotations

import copy
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from layoutkit import data as DA                                          # noqa: E402
from layoutkit import spec as SP                                          # noqa: E402
from layoutkit.recommend import (queue_add, queue_match, queue_new, queue_next, queue_recorded, queue_sync, reach,  # noqa: E402
                                 recommend)
from layoutkit.recommend import constraints as CN                         # noqa: E402
from layoutkit.recommend import layout as LY                              # noqa: E402
from layoutkit.recommend import sample as SM                              # noqa: E402
from layoutkit.recommend import score as SC                               # noqa: E402
from layoutkit.recommend.camera import Camera                             # noqa: E402
from layoutkit.recommend.select import data_arrays, layout_of             # noqa: E402

RACK = ROOT / "examples" / "rack_fr5" / "spec.json"
FR5AUTO = Path(os.environ.get("FR5AUTO_DIR") or (ROOT.parent / "FR5-AutoCollect"))

# fr5auto camera.project_world(Cam(intr, flip), inv(T_cb), P) 로 잰 값(2026-11-04, 실물 3인칭 보정)
REF_P = [[0.0, 550.0, 106.44], [-200.0, 450.0, 46.44], [270.0, 650.0, 156.44], [120.0, 600.0, 109.0], [-150.0, 640.0, 0.0], [250, 420, 156.44]]
REF_FLIP = [[480.54294369307553, 334.14833415068995], [588.4717838791016, 317.1089476459627], [262.30182469198473, 364.9084484000583],
            [394.5917586305177, 359.38617742819235], [587.6233823887436, 439.38251236246845], [319.7821860313777, 247.85820734427452]]
REF_NOFLIP = [[480.19430912442067, 333.521073831897], [586.0799413612193, 315.9326656272468], [265.3445790201172, 362.5579387478975],
              [394.8530887665291, 358.3877114772655], [583.8382723009375, 434.6484737881337], [320.4251312300263, 247.78863473329199]]


def _fr5auto():
    if not (FR5AUTO / "fr5auto" / "rackrec.py").is_file():
        return None
    if str(FR5AUTO) not in sys.path:
        sys.path.insert(0, str(FR5AUTO))
    try:
        from fr5auto import camera as CM, config, rackrec                 # noqa: F401
        return CM, config, rackrec
    except Exception as e:                                               # 의존이 모자라면 건너뛴다
        print(f"  (fr5auto 를 못 읽음 — 건너뜀: {type(e).__name__}: {e})")
        return None


# ---------------------------------------------------------------- 1
def test_camera_matches_fr5auto():
    sp = SP.load(RACK)
    cd = sp["cameras"][0]
    cam = Camera(cd)
    err = np.abs(cam.project(np.array(REF_P)) - np.array(REF_FLIP)).max()
    assert err < 0.01, f"flip=true 투영 차이 {err} px"
    cam2 = Camera({**cd, "dist_flip": False})
    err2 = np.abs(cam2.project(np.array(REF_P)) - np.array(REF_NOFLIP)).max()
    assert err2 < 0.01, f"flip=false 투영 차이 {err2} px"
    fa = _fr5auto()
    if fa:
        CM = fa[0]
        intr = {"width": cd["width"], "height": cd["height"], "fx": cd["K"][0][0], "fy": cd["K"][1][1], "ppx": cd["K"][0][2],
                "ppy": cd["K"][1][2], "model": "distortion.inverse_brown_conrady", "coeffs": cd["dist"]}
        rng = np.random.default_rng(0)
        P = np.c_[rng.uniform(-300, 350, 500), rng.uniform(350, 750, 500), rng.uniform(0, 250, 500)]
        for flip, c in ((True, cam), (False, cam2)):
            ref = CM.project_world(CM.Cam(intr, flip), CM.inv(np.asarray(cd["T_cam_base"], float)), P)
            e = np.nanmax(np.abs(c.project(P) - ref))
            assert e < 0.01, f"fr5auto 와 무작위 점 차이 {e} px (flip={flip})"
        print(f"  fr5auto 무작위 500점 비교 통과")
    print(f"  최대 차이 flip {err:.2e} · noflip {err2:.2e} px")


# ---------------------------------------------------------------- 2
def test_rack_reach_121():
    sp = SP.load(RACK)
    Rs, Rg, n_ok, n = reach(sp)
    assert n == 16384, n
    assert n_ok == 121, f"통과 {n_ok} (fr5auto 121)"
    assert (len(Rs), len(Rg)) == (60, 41), (len(Rs), len(Rg))
    fa = _fr5auto()
    if fa:
        import json
        _, config, rackrec = fa
        d = json.loads((ROOT / "examples" / "rack_fr5" / "data" / "real_rack_20261103.json").read_text(encoding="utf-8"))
        cfg = copy.deepcopy(config.DEFAULTS)
        cfg["rack"].update({"z_top_mm": 106.44, "pitch_mm": 37.18, "hole_dz_mm": 5.23, "grasp_dz_mm": 25.0})
        W = rackrec.World(cfg, rcal={"third": d["third"]}, intr3=d["third"]["intr"], wcal={})
        C0 = rackrec.sample(W, 16384, np.random.default_rng(20261102))
        ok0 = W.checks(C0)[0]
        lay = LY.parse(sp)
        C1 = SM.sample(lay, 16384, np.random.default_rng(20261102))
        ok1 = CN.checks(C1, CN.Context(sp, lay))[0]
        assert np.allclose(C0["P"], C1["P"]) and np.allclose(C0["psi"], C1["yaw"]), "후보가 다르다"
        assert np.array_equal(ok0, ok1), "통과 후보가 다르다"
        print("  fr5auto 와 같은 후보 · 같은 통과 집합")
    print(f"  통과 {n_ok}/{n} · 놓을 수 있는 칸 start {len(Rs)} · goal {len(Rg)}")


# ---------------------------------------------------------------- 3
FAKE = {
    "task": "fake_racks",
    "area": {"x": [-200, 200], "y": [420, 620]},
    "scales": {"h_xy_mm": 30.0, "h_yaw_deg": 20.0},
    "strata": [{"name": "start_slot", "values": [0, 1, 2, 3]}, {"name": "goal_slot", "values": [0, 1, 2, 3]}],
    "layout": {"kind": "fixtures",
               "fixtures": [{"name": "rack", "count": 2, "size_mm": [170, 40], "height_mm": 60, "slots": 4, "pitch_mm": 37.0,
                             "hole_r_mm": 15.0, "z_top_mm": 60.0}],
               "items": [{"name": "red", "role": "start", "symbol": "R", "above_mm": 50, "cap_r_mm": 17.5},
                         {"name": "yellow", "role": "obstacle", "symbol": "Y"}, {"name": "ring", "role": "goal"}],
               "same_fixture_allowed": True, "yaw_window": {"center_deg": -80.0, "half_deg": 54.0}},
    "constraints": [{"type": "reach", "min_mm": 150, "max_mm": 900}, {"type": "gap", "min_mm": 60}],
    "recommend": {"n_cand": 2048},
}


def _slot(fx, t, k):
    u, v = t.offsets[k]
    r = math.radians(fx["yaw"])
    return fx["x"] + u * math.cos(r) - v * math.sin(r), fx["y"] + u * math.sin(r) + v * math.cos(r)


def place(opt, lay, rng, i, ds="sim", rec_id=None, noise=(10.0, 5.0)):
    """사람이 추천 자리에 놓는다: 고정물마다 ±10 mm·±5°(고르게) — 실제 자리가 기록된다."""
    fx = []
    for f in opt["fixtures"]:
        fx.append({"name": f["name"], "x": f["x"] + rng.uniform(-noise[0], noise[0]), "y": f["y"] + rng.uniform(-noise[0], noise[0]),
                   "yaw": float(LY.canon(f["yaw"] + rng.uniform(-noise[1], noise[1])))})
    by = {f["name"]: f for f in fx}
    t = lay.start_type
    sx, sy = _slot(by[opt["start"]["fixture"]], t, opt["start"]["slot"])
    gx, gy = _slot(by[opt["goal"]["fixture"]], lay.goal_type, opt["goal"]["slot"])
    obs = [it["slot"] for it in opt["items"] if it["role"] == "obstacle"]
    disc = {"start_slot": opt["start"]["slot"], "goal_slot": opt["goal"]["slot"], "obstacle_slot": obs[0] if obs else None}
    if rec_id:
        disc["rec_id"] = rec_id
    return DA.episode(f"ep_{i:03d}", ds, {"x": sx, "y": sy}, {"x": gx, "y": gy}, outcome="success", discrete=disc, fixtures=fx,
                      source="synth")


def _filled(eps, sp, lay):
    D = data_arrays(eps, lay, sp, SC.families(sp, lay))
    cells = SC.Cells(lay)
    _, a = cells.ids(D["g"], "start")
    _, b = cells.ids(D["q"], "goal")
    return len({int(c) for c in a if c >= 0}), len({int(c) for c in b if c >= 0})


def test_fake_world_fills_faster():
    sp = SP.load(copy.deepcopy(FAKE))
    lay = LY.parse(sp)
    n_ep = 40
    rng = np.random.default_rng(11)
    eps = []
    t0 = time.time()
    for i in range(n_ep):
        rec = recommend([DA.Dataset("sim", eps)], sp, n=1, seed=100 + i)
        assert rec["options"], rec.get("why")
        eps.append(place(rec["options"][0], lay, rng, i))
    t_rec = time.time() - t0
    # 무작위: 놓을 수 있는 배치(검사 통과) 중 고르게
    rr = np.random.default_rng(12)
    C = SM.sample(lay, 8192, rr)
    ok = CN.checks(C, CN.Context(sp, lay))[0]
    idx = rr.choice(np.flatnonzero(ok), n_ep, replace=False)
    rnd = [place(layout_of(C, int(j), lay), lay, rr, k) for k, j in enumerate(idx)]
    fr, fq = _filled(eps, sp, lay)
    rr_, rq_ = _filled(rnd, sp, lay)
    Rs, Rg, n_ok, n = reach(sp)
    print(f"  {n_ep}판 채운 (자리, 방향) 칸 start·goal: 추천 {fr}·{fq} · 무작위 {rr_}·{rq_} (놓을 수 있는 칸 {len(Rs)}·{len(Rg)}) · 추천 {t_rec:.1f} s")
    assert fr + fq > rr_ + rq_, "추천이 무작위보다 칸을 덜 채웠다"
    assert fr >= 0.75 * n_ep and fq >= 0.75 * n_ep, "추천이 판당 새 칸을 너무 적게 채웠다"


# ---------------------------------------------------------------- 4
def test_avoids_holdout():
    sp = SP.load({**copy.deepcopy(FAKE), "holdout": 6})
    lay = LY.parse(sp)
    q = queue_new()
    rng = np.random.default_rng(3)
    eps = []
    for i in range(6):
        rec = recommend([DA.Dataset("sim", eps)], sp, n=3, seed=i, queue=q)
        assert len(q["holdout"]) == 6
        H = q["holdout"]
        for o in rec["options"]:
            for hd in H:
                dg = math.sqrt(SC.d2_xyp([o["feat"]["g"]], [hd["feat"]["g"]], lay.h_xy, lay.h_psi)[0, 0])
                dq = math.sqrt(SC.d2_xyp([o["feat"]["q"]], [hd["feat"]["q"]], lay.h_xy, lay.h_psi)[0, 0])
                assert not (dg < 0.5 and dq < 0.5), f"선택지 {o['label']} 가 시험 배치 {hd['id']} 근처"
            assert "holdout_dist_h" in o and o["holdout_dist_h"] >= 0.5 - 1e-9
        eps.append(place(rec["options"][0], lay, rng, i))
    ids = [h["id"] for h in q["holdout"]]
    assert ids == [f"T{k:02d}" for k in range(1, 7)], ids
    print(f"  시험 배치 {len(ids)}개 · 선택지가 모두 0.5 h 밖 · 가장 가까운 거리 예 {rec['options'][0]['holdout_dist_h']} h")


# ---------------------------------------------------------------- 5
def test_queue_deleted_returns():
    sp = SP.load(copy.deepcopy(FAKE))
    lay = LY.parse(sp)
    rng = np.random.default_rng(5)
    q = queue_new()
    rec = recommend([], sp, n=3, seed=1, queue=q)
    t1 = queue_add(q, rec["options"][0])
    queue_recorded(q, t1["id"])
    e1 = place(rec["options"][0], lay, rng, 0, rec_id=t1["id"])
    assert queue_sync(q, [e1])[t1["id"]] == "collected"
    assert queue_next(q) is None
    # 판을 지운다(폴더에서 빠짐) → 그 목표가 pending 으로 돌아가고 다음 추천의 A 가 된다
    assert queue_sync(q, [])[t1["id"]] == "pending"
    assert q["targets"][0].get("kept_once") is True
    assert queue_next(q)["id"] == t1["id"]
    rec2 = recommend([], sp, n=3, seed=2, queue=q)
    labs = [o["label"] for o in rec2["options"]]
    A = rec2["options"][0]
    assert A["label"] == "A" and A["how"] == "keep" and A["target_id"] == t1["id"] and "retry_deleted" in A["why_codes"], A
    assert "A2" in labs, labs
    # 다시 모으면 끝
    e1b = place(A, lay, rng, 1, rec_id=t1["id"])
    queue_sync(q, [e1b])
    assert queue_next(q) is None
    # rec_id 없이 놓인 자리로 맞추기(둘째 목표)
    t2 = queue_add(q, rec2["options"][1])
    e2 = place(rec2["options"][1], lay, rng, 2, noise=(5.0, 3.0))
    m = queue_match(q, [e1b, e2], tol_mm=30.0)
    assert m.get(e2["id"]) == t2["id"] and m.get(e1b["id"]) == t1["id"], m
    print(f"  {t1['id']}: 저장 → 지움 → 다시 A · {t2['id']}: rec_id 없이 놓인 자리로 맞춤")


# ---------------------------------------------------------------- 6
def test_fills_result():
    sp = SP.load(copy.deepcopy(FAKE))
    lay = LY.parse(sp)
    C = SC.hex_centers(lay.area, lay.h_xy)
    rng = np.random.default_rng(9)
    rec0 = recommend([], sp, n=1, seed=1)
    eps = [place(rec0["options"][0], lay, rng, 0)]
    xy = SC.cell_of(np.array([[eps[0]["start"]["x"], eps[0]["start"]["y"]]]), C, lay.area)
    cnt = np.zeros(len(C))
    cnt[xy[0]] = 1.0
    result = {"coverage": {"h": lay.h_xy, "centers": C.tolist(), "n_cells": len(C), "start": {"count": cnt.tolist()},
                           "goal": {"count": [0.0] * len(C)}, "yaw_bins": 0}}
    out = recommend([DA.Dataset("sim", eps)], sp, result=result, n=3, seed=2)
    cov = result["coverage"]
    assert result["recommend"] is out and out["options"]
    assert len(cov["start"]["reach"]) == len(C) and len(cov["goal"]["reach"]) == len(C)
    assert cov["reach_start"] == sum(cov["start"]["reach"]) and cov["n_min"] >= cov["reach_goal"] - 0
    print(f"  coverage: reach start {cov['reach_start']} · goal {cov['reach_goal']} (자리 칸 {len(C)}) · n_min {cov['n_min']}")


def main():
    tests = [(k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)]
    bad = 0
    for name, fn in tests:
        t = time.time()
        try:
            fn()
            print(f"ok   {name} ({time.time() - t:.1f} s)")
        except AssertionError as e:
            bad += 1
            print(f"FAIL {name}: {e}")
        except Exception as e:
            bad += 1
            import traceback
            traceback.print_exc()
            print(f"ERR  {name}: {type(e).__name__}: {e}")
    print(f"{len(tests) - bad}/{len(tests)} 통과")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
