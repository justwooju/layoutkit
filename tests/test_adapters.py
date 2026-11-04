"""어댑터·사건 찾기 — 알고 있는 집는·놓는 자리를 다시 찾나(오차 ≤ 2 mm), 형식 자동 판별, 표 열 대응, 실행 기록.

    python3 tests/test_adapters.py
LeRobot parquet 왕복은 pyarrow 가 있을 때만(없으면 같은 열로 메모리에서). FR5-AutoCollect tests/make_human.py 로 만든
fr5rec 가짜 데이터 시험은 환경 변수 FR5AUTO_DIR(FR5-AutoCollect 폴더)가 있을 때만.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "examples" / "lerobot_demo"))
import layoutkit as lk  # noqa: E402
import make_lerobot as ML  # noqa: E402
from layoutkit import events as EV  # noqa: E402
from layoutkit.adapters import detect_kind  # noqa: E402
from layoutkit.adapters import lerobot as LR  # noqa: E402

TOL = 2.0
TMP = Path(tempfile.mkdtemp(prefix="layoutkit_t_"))


def _err(a, b):
    return math.hypot(a["x"] - b[0], a["y"] - b[1])


def test_lerobot_columns():
    """LeRobot 열(make_lerobot 궤적, m·rad, 그리퍼 폭) → 사건 → 자리 오차 ≤ 2 mm. 잡음·한 프레임 튐 포함."""
    eps = ML.make(None, 8, seed=0)
    info = ML.info_json(eps)
    g = LR.guess_columns(info, {})
    assert (g["xyz"], g["grip"], g["yaw"]) == ([0, 1, 2], 6, 5), g
    worst = 0.0
    for e in eps:
        ep = LR.episode_from_columns(e["cols"], info, g, e["episode_index"])
        assert ep["_events"]["flags"] == [] and ep["_events"]["units"] == "m", ep["_events"]
        worst = max(worst, _err(ep["start"], e["pick_mm"]), _err(ep["goal"], e["place_mm"]))
    assert worst <= TOL, worst
    print(f"    LeRobot 열 8판: 최대 오차 {worst:.2f} mm")


def test_events_inverted_noisy():
    """그리퍼 값이 '닫힘 명령'(클수록 닫힘, 0~1)이고 잡음·튐이 있어도 방향을 스스로 짐작하고 자리를 찾는다."""
    rng = np.random.default_rng(5)
    e = ML.make(None, 1, seed=3)[0]
    st = np.asarray(e["cols"]["observation.state"], float)
    t = np.asarray(e["cols"]["timestamp"], float)
    cmd = (ML.OPEN - st[:, 6]) / (ML.OPEN - ML.CLOSED) + rng.normal(0, 0.03, len(t))   # 0 엶 → 1 쥠
    cmd[[40, 41]] = 0.9                                              # 열린 동안 두 프레임 튐(0.07 s < min_closed_s)
    ev = EV.detect(t, st[:, :3], cmd, None)
    assert ev["ok"] and ev["closed_is"] == "high" and len(ev["segments"]) == 1, ev
    assert _err(ev["start"], e["pick_mm"]) <= TOL and _err(ev["goal"], e["place_mm"]) <= TOL
    ev2 = EV.detect(t, st[:, :3], np.full(len(t), 0.5) + rng.normal(0, 1e-3, len(t)))   # 그리퍼가 안 움직임
    assert not ev2["ok"] and "no_grip" in ev2["flags"], ev2


def test_lerobot_parquet():
    """pyarrow 가 있으면 make_lerobot 로 폴더를 써서 load_dataset(자동 판별) 왕복."""
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        print("    (건너뜀: pyarrow 없음 — 열 시험으로 대신)")
        return
    root = ML.write(TMP / "lerobot", ML.make(None, 8, seed=1))
    assert detect_kind(root) == "lerobot"
    ds = lk.load_dataset(root, name="fake")
    truth = json.loads((root / "truth.json").read_text())
    assert len(ds) == 8 and len(ds.usable()) == 8
    worst = max(max(_err(e["start"], t["pick_mm"]), _err(e["goal"], t["place_mm"])) for e, t in zip(ds.episodes, truth))
    assert worst <= TOL, worst
    print(f"    LeRobot parquet 8판: 최대 오차 {worst:.2f} mm")


def _fr5rec_meta(rng, pick, place, hz=10.0, blip=True):
    """fr5rec meta 흉내(frames[].t · tcp_base_mm_deg · grip_width) — 잡기 2.5~3.0 s 멈춤, 놓기 7.0~7.6 s 멈춤."""
    seg = [(1.0, (300, 0, 300), False), (2.5, (*pick, 140), False), (3.0, (*pick, 140), True), (4.0, (*pick, 260), True),
           (6.5, (*place, 260), True), (7.0, (*place, 150), True), (7.6, (*place, 150), False), (9.0, (300, 0, 300), False)]
    frames = []
    prev_t, prev = 0.0, np.array([300.0, 0.0, 300.0])
    k = 0
    for i in range(int(9.0 * hz) + 1):
        t = i / hz
        while k < len(seg) - 1 and t > seg[k][0]:
            prev_t, prev = seg[k][0], np.asarray(seg[k][1], float)
            k += 1
        te, pe, closed = seg[k]
        s = np.clip((t - prev_t) / (te - prev_t), 0, 1)
        s = s * s * (3 - 2 * s)
        p = prev + (np.asarray(pe, float) - prev) * s + rng.normal(0, 0.4, 3)
        gw = 0.012 if (2.6 <= t < 7.3) else 0.04
        if blip and i == 15:
            gw = 0.012                                               # 열린 동안 한 프레임 튐
        frames.append({"i": i, "t": 1.7e9 + t, "tcp_base_mm_deg": [*np.round(p, 3).tolist(), 180.0, 0.0, -80.0 + rng.normal(0, 0.2)],
                       "grip_width": gw})
    return {"outcome": "success", "frames": frames, "fr5rec": {"started_at": "2026-11-04T10:00:00", "tag": None}}


def test_fr5rec_events_and_tags():
    """fr5rec 폴더: 꼬리표 없는 판은 궤적 사건으로(오차 ≤ 2 mm), 꼬리표(red_xy·slot_xy) 있는 판은 꼬리표 자리로.
    _discarded/ · ep_NNN.part/ 는 읽지 않는다."""
    rng = np.random.default_rng(2)
    d = TMP / "fr5rec_ds"
    truth = []
    for i in range(4):
        pick = (float(rng.uniform(-150, 250)), float(rng.uniform(450, 650)))
        place = (float(rng.uniform(-150, 250)), float(rng.uniform(450, 650)))
        (d / f"ep_{i:03d}").mkdir(parents=True, exist_ok=True)
        (d / f"ep_{i:03d}" / "meta.json").write_text(json.dumps(_fr5rec_meta(rng, pick, place)))
        truth.append((pick, place))
    m = _fr5rec_meta(rng, (0, 500), (100, 600))
    m["fr5rec"]["tag"] = {"by": "fr5auto", "task": "rack", "src": [1, 3], "dst": [0, 2], "red_xy": [240.3, 579.8], "slot_xy": [-29.3, 573.7],
                          "yellow_at": [1, 0], "racks": [{"x": -10, "y": 580, "yaw": 2}, {"x": 190, "y": 580, "yaw": 3}],
                          "params": {"yaw_g": 92.0, "yaw_i": 91.0}}
    (d / "ep_004").mkdir()
    (d / "ep_004" / "meta.json").write_text(json.dumps(m))
    for junk in ("_discarded/ep_005_20261104_100000", "ep_005.part"):
        (d / junk).mkdir(parents=True)
        (d / junk / "meta.json").write_text(json.dumps(_fr5rec_meta(rng, (0, 500), (100, 600))))
    assert detect_kind(d) == "fr5rec"
    ds = lk.load_dataset(d)
    assert ds.name == "fr5rec_ds" and len(ds) == 5 and ds.meta["how"] == {"events": 4, "tag": 1}, ds.meta
    worst = max(max(_err(e["start"], p), _err(e["goal"], q)) for e, (p, q) in zip(ds.episodes[:4], truth))
    assert worst <= TOL, worst
    tg = ds.episodes[4]
    assert (tg["start"]["x"], tg["goal"]["y"], tg["start"]["yaw"]) == (240.3, 573.7, 92.0), tg
    assert tg["discrete"] == {"start_fixture": 1, "start_slot": 3, "goal_fixture": 0, "goal_slot": 2, "same_fixture": False,
                              "obstacle_slot": 0, "arrangement": "Y○○R"}, tg["discrete"]
    assert len(tg["fixtures"]) == 2 and ds.episodes[0]["extra"]["n_frames"] == 91
    print(f"    fr5rec 가짜 4판(사건): 최대 오차 {worst:.2f} mm · 꼬리표 판 1")


def test_fr5rec_make_human():
    """FR5-AutoCollect tests/make_human.py(사람 시연 흉내 — 3 Hz, IK·FK 를 거친 TCP) 데이터에서 집은 자리(잡을 때 TCP)를 다시 찾는다."""
    fa = os.environ.get("FR5AUTO_DIR")
    if not fa or not (Path(fa) / "tests" / "make_human.py").is_file():
        print("    (건너뜀: FR5AUTO_DIR 없음)")
        return
    sys.path.insert(0, str(Path(fa)))
    sys.path.insert(0, str(Path(fa) / "tests"))
    import make_human as MH
    from fr5auto import geom as G
    d = TMP / "human"
    info = MH.make(d, 3, seed=7)
    ds = lk.load_dataset(d)
    assert ds.meta["how"] == {"events": 3}, ds.meta
    worst = 0.0
    for e, t in zip(ds.episodes, info):
        tcp = np.asarray(t["hole"]) + [0, 0, t["gdz"]] - G.rot_xyz(180.0, 0.0, t["yaw_t"]) @ np.asarray(t["off"])
        worst = max(worst, _err(e["start"], tcp[:2]))
        assert abs(e["start"]["yaw"] - t["yaw_t"]) < 1.0 and e["thumbs"].get("third"), e
    assert worst <= TOL, worst
    print(f"    make_human 3판: 집은 자리 최대 오차 {worst:.2f} mm")


def test_table_adapter():
    """CSV 열 대응(map) · 이름 짐작 · v2 내보내기 전용 대응."""
    p = TMP / "t.csv"
    p.write_text("ep,red_x,red_y,ring_x,ring_y,slot,ok,note\n"
                 "a,10,500,100,600,0,true,x\nb,20,510,-50,620,1,false,y\nc,30,520,0,630,1,true,z\n", encoding="utf-8")
    ds = lk.load_dataset(p, map={"start.x": "red_x", "start.y": "red_y", "goal.x": "ring_x", "goal.y": "ring_y",
                                 "discrete.goal_slot": "slot", "outcome": "ok", "id": "ep"})
    assert [e["id"] for e in ds.episodes] == ["t/a", "t/b", "t/c"]
    assert ds.episodes[1]["goal"] == {"x": -50.0, "y": 620.0} and ds.episodes[1]["outcome"] == "fail"
    assert ds.episodes[0]["discrete"] == {"goal_slot": 0, "note": "x"}, ds.episodes[0]["discrete"]
    q = TMP / "g.jsonl"
    q.write_text("\n".join(json.dumps({"pick_x": i, "pick_y": 2 * i, "place_xy": [i + 50, 3 * i]}) for i in range(4)), encoding="utf-8")
    ds = lk.load_dataset(q, name="g")
    assert ds.episodes[3]["start"] == {"x": 3.0, "y": 6.0} and ds.episodes[3]["goal"] == {"x": 53.0, "y": 9.0}
    v2 = lk.load_dataset(ROOT / "examples" / "rack_fr5" / "data" / "v2_layouts_20261103.json")
    e = v2.episodes[0]
    assert v2.name == "fr5_autocollect10hz_20261103" and e["discrete"]["same_fixture"] is False and e["discrete"]["goal_slot"] == 1
    auto = lk.load_dataset(p)                                        # red_x·ring_x 같은 흔한 이름은 짐작한다
    assert auto.episodes[2]["start"] == {"x": 30.0, "y": 520.0} and auto.episodes[2]["goal"] == {"x": 0.0, "y": 630.0}
    u = TMP / "u.csv"
    u.write_text("a,b,c,d\n1,2,3,4\n", encoding="utf-8")
    try:
        lk.load_dataset(u)                                           # 맞는 이름이 없으면 무엇을 주면 되는지 알린다
        raise AssertionError("열 대응 없이 읽혔다")
    except ValueError as ex:
        assert "map" in str(ex)


def test_runs_adapter():
    """실행 기록: CSV(예제 200회) 판별·읽기 · runs.jsonl(kind run 만)."""
    csvp = ROOT / "examples" / "rack_fr5" / "data" / "runs_20261031_20261104.csv"
    assert detect_kind(csvp) == "fr5auto_runs"
    r = lk.load_dataset(csvp)
    assert len(r) == 200 and r[3]["reasons"][0].startswith("꽂을 칸") and r[0]["exec_s"] == 20.7
    j = TMP / "work" / "runs.jsonl"
    j.parent.mkdir(parents=True, exist_ok=True)
    j.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in [
        {"kind": "plan", "t": 1.0, "ok": True},
        {"kind": "run", "t": 1762300000.0, "verdict": "fail", "kept": None, "decided_by": "auto", "T": 21.5, "record": True,
         "verdict_why": ["받침이 움직였다 — 실패: 받침0 6.4 mm"], "hover": {"shift": True, "off_mm": 2.0}, "servo": {"n_meas": 4, "n_fix": 3}},
        {"kind": "run", "t": 1762300100.0, "verdict": "success", "kept": "success", "decided_by": "auto", "T": 22.0, "record": True}]),
        encoding="utf-8")
    r = lk.load_runs(TMP)
    assert len(r) == 2 and r[0]["exec_s"] == 21.5 and r[0]["hover"]["shifted"] is True
    from layoutkit.analyze.runs import summarize
    s = summarize(r)
    assert s["reasons"][0]["code"] == "fixture_moved" and s["by_verdict"] == {"fail": 1, "success": 1}


if __name__ == "__main__":
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print(f"ok  {name}")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
