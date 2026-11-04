"""받침 예제 숫자 재현(docs/ARCHITECTURE.md 7절) — fr5auto rackrec(test_v1_numbers)·RECOMMENDER.md 1절과 같은 값이 나오나.

    python3 tests/test_rack_numbers.py      (pytest 없이도 돈다)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import layoutkit as lk  # noqa: E402

EX = ROOT / "examples" / "rack_fr5"
SPEC = EX / "spec.json"
V1_TAGS = EX / "data" / "v1_tags.json"
V1_FEAT = EX / "data" / "v1_feat.json"
V2 = EX / "data" / "v2_layouts_20261103.json"
RUNS = EX / "data" / "runs_20261031_20261104.csv"


def _rho(r, a, b):
    return next(p["rho"] for p in r["coupling"]["pairs"] if p["a"] == a and p["b"] == b)


def _slots(r, name):
    return [row["n"] for row in next(s for s in r["strata"] if s["name"] == name)["rows"]]


def test_v1_numbers():
    """v1 100판: 왼쪽(x > 64.9) → 오른쪽 44/44 · 오른쪽 → 왼쪽 52/56 · ρ −0.81·−0.43 · 118~380 중앙 232 · ≤100 mm 0 ·
    자리 32·43·99 · 빨강 칸 31/16/8/45 · 링 칸 25/22/25/28 · 채운 칸 20·27(47칸) · 이론 41×3 = 123 · 무작위 663."""
    for src in (V1_TAGS, V1_FEAT):
        r = lk.analyze([lk.load_dataset(src, name="fr5_v1", weight=0.5)], SPEC)
        sd = r["coupling"]["side"]
        assert sd["split"] == 64.9 and sd["left_is"] == "hi" and sd["table"] == [[44, 0], [4, 52]], sd
        assert sd["acc"] == 0.96, sd
        assert round(_rho(r, "start.x", "goal.x"), 2) == -0.81 and round(_rho(r, "start.y", "goal.y"), 2) == -0.43
        tr = r["transfer"]
        assert (round(tr["min"]), round(tr["max"]), round(tr["median"]), tr["near_n"], tr["near_share"]) == (118, 380, 232, 0, 0.0), tr
        sp = r["spots"]
        assert (sp["start"], sp["goal"], sp["pairs"]) == (32, 43, 99), sp
        assert _slots(r, "start_slot") == [31, 16, 8, 45] and _slots(r, "goal_slot") == [25, 22, 25, 28]
        cv = r["coverage"]
        assert (cv["n_cells"], cv["filled_start"], cv["filled_goal"]) == (47, 20, 27), cv
        assert cv["n_hex"] == 41 and cv["yaw_bins"] == 3 and cv["n_theory"] == 123 and round(cv["coupon_random"]) == 663, cv
        rg = r["ranges"]
        assert [round(v) for v in rg["start.x"]] == [-111, 240] and [round(v) for v in rg["goal.x"]] == [-146, 260], rg
        assert r["discrete"]["same_fixture"] == {"false": 100}
        assert abs(cv["fill_dist_mm"]["start"] - 61) < 1 and abs(cv["fill_dist_mm"]["goal"] - 56) < 1 and cv["hull_m2"] == 0.0593, cv
    r = lk.analyze([lk.load_dataset(V1_TAGS, name="fr5_v1", weight=0.5)], SPEC)
    assert r["discrete"]["arrangement"] == {"Y○○R": 45, "R○○Y": 31, "○R○Y": 16, "Y○R○": 8}, r["discrete"]["arrangement"]
    cards = {c["id"]: c for c in r["cards"]}
    assert cards["coupling"]["status"] == "bad" and cards["near"]["status"] == "bad" and cards["predict"]["status"] == "bad"
    print(f"    v1: 44/44 · 52/56 · ρ {_rho(r, 'start.x', 'goal.x')} · 자리 32/43/99 · 칸 20/27/47 · 무작위 {r['coverage']['coupon_random']}")


def test_v2_numbers():
    """v2 19판: ρ(x) −0.03 · 가까이 21 % · 자리 19·19·19 · 같은 받침 8 · (fr5auto cover: 기준 30.1, 왼쪽 9 중 4 오른쪽 · 오른쪽 10 중 7 왼쪽)."""
    r = lk.analyze([lk.load_dataset(V2, name="fr5_v2")], SPEC)
    assert round(_rho(r, "start.x", "goal.x"), 2) == -0.03
    assert round(r["transfer"]["near_share"], 2) == 0.21 and r["transfer"]["near_n"] == 4
    sp = r["spots"]
    assert (sp["start"], sp["goal"], sp["pairs"]) == (19, 19, 19), sp
    assert r["discrete"]["same_fixture"]["true"] == 8
    sd = r["coupling"]["side"]
    assert sd["split"] == 30.1 and sd["table"][0] == [4, 5] and sd["table"][1] == [3, 7], sd
    assert r["coverage"]["yaw_bins"] == 0                             # v2 내보내기에는 yaw 가 없다
    print(f"    v2: ρ {_rho(r, 'start.x', 'goal.x')} · 가까이 {r['transfer']['near_share']} · 자리 19/19/19 · 같은 받침 8")


def test_combined_and_runs():
    """v1(무게 0.5) + v2 + 실행 기록: 비교 지표가 데이터셋마다 혼자 분석한 값과 같고, 실행 기록 200회가 요약된다."""
    v1 = lk.load_dataset(V1_TAGS, name="fr5_v1", weight=0.5)
    v2 = lk.load_dataset(V2, name="fr5_v2")
    r = lk.analyze([v1, v2], SPEC, runs=lk.load_runs(RUNS))
    m = {x["key"]: x["values"] for x in r["compare"]["metrics"]}
    assert m["rho:start.x→goal.x"] == {"fr5_v1": -0.807, "fr5_v2": -0.034}, m
    assert m["side_acc"]["fr5_v1"] == 0.96 and m["near_share"]["fr5_v2"] == 0.211 and m["same_fixture_n"]["fr5_v2"] == 8, m
    assert [d["color"] for d in r["datasets"]] == ["#0072B2", "#E69F00"]          # Okabe–Ito 순서(파랑 먼저)
    ru = r["runs"]
    assert ru["n"] == 200 and ru["by_verdict"]["success"] == 148 and ru["kept"]["success"] == 149, ru["by_verdict"]
    assert sum(d["n"] for d in ru["by_day"]) == 200 and ru["reasons"][0]["code"] == "fixture_moved"
    print(f"    v1+v2: 가중 ρ {_rho(r, 'start.x', 'goal.x')} · 실행 {ru['n']}회 성공 {ru['by_verdict']['success']}")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
