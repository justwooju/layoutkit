"""명령 흐름 — analyze 가 result.json 을 만들고 키가 docs/ARCHITECTURE.md 3절과 맞나 · init-spec · watch --once · pipeline.

    python3 tests/test_cli.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples" / "rack_fr5"
TMP = Path(tempfile.mkdtemp(prefix="layoutkit_cli_"))

# DESIGN 3절 키(더 있어도 된다 — 빠지면 안 된다)
TOP = {"tool", "version", "created", "spec", "datasets", "episodes", "area", "cards", "coverage", "coupling", "transfer", "spots",
       "strata", "ranges", "timeline", "runs", "recommend", "compare"}
SUB = {
    "datasets": {"name", "n", "n_usable", "n_success", "weight", "color"},
    "episodes": {"id", "dataset", "t", "outcome", "weight", "source", "start", "goal", "discrete", "fixtures", "extra", "thumbs",
                 "flags", "cell_start", "cell_goal", "move_mm"},
    "cards": {"id", "status", "value", "unit", "target", "code", "args"},
    "coverage": {"h", "centers", "n_cells", "start", "goal", "yaw_bins", "filled_start", "filled_goal", "reach_start", "reach_goal",
                 "n_min", "coupon_random", "fill_dist_mm"},
    "coverage.start": {"count", "count_by_ds", "reach"},
    "coupling": {"pairs", "side", "predict"},
    "coupling.pairs": {"a", "b", "rho", "rho_by_ds"},
    "coupling.side": {"split", "axis", "table", "acc"},
    "coupling.predict": {"knn_acc", "chance", "k"},
    "transfer": {"values", "min", "median", "max", "near_share", "near_mm"},
    "spots": {"start", "goal", "pairs", "dup_mm", "dups"},
    "strata": {"name", "rows", "max_dev"},
    "strata.rows": {"value", "n", "share", "target"},
    "timeline": {"t", "id", "dataset", "outcome"},
}


def run(*args, ok=True):
    env = dict(os.environ, PYTHONPATH=str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    p = subprocess.run([sys.executable, "-m", "layoutkit", *map(str, args)], cwd=ROOT, env=env, capture_output=True, text=True,
                       timeout=600)
    if ok and p.returncode != 0:
        raise AssertionError(f"layoutkit {' '.join(map(str, args))} → {p.returncode}\n{p.stdout}\n{p.stderr}")
    return p


def _keys(name, obj):
    obj = obj[0] if isinstance(obj, list) else obj
    miss = SUB[name] - set(obj)
    assert not miss, f"{name}: 빠진 키 {sorted(miss)}"


def test_analyze_json_keys():
    out = TMP / "result.json"
    run("analyze", f"fr5_v1={EX / 'data' / 'v1_tags.json'}", f"fr5_v2={EX / 'data' / 'v2_layouts_20261103.json'}",
        "--weight", "fr5_v1=0.5", "--spec", EX / "spec.json", "--runs", EX / "data" / "runs_20261031_20261104.csv", "--json", out)
    r = json.loads(out.read_text(encoding="utf-8"))
    assert not (TOP - set(r)), sorted(TOP - set(r))
    assert r["tool"] == "layoutkit" and r["version"] == "0.1.0" and r["recommend"] is None
    for k in ("datasets", "episodes", "cards", "coverage", "coupling", "transfer", "spots", "strata", "timeline"):
        _keys(k, r[k])
    _keys("coverage.start", r["coverage"]["start"])
    _keys("coupling.pairs", r["coupling"]["pairs"])
    _keys("coupling.side", r["coupling"]["side"])
    _keys("coupling.predict", r["coupling"]["predict"])
    _keys("strata.rows", r["strata"][0]["rows"])
    assert [d["name"] for d in r["datasets"]] == ["fr5_v1", "fr5_v2"] and r["datasets"][0]["weight"] == 0.5
    assert r["episodes"][0]["weight"] == 0.5 and r["runs"]["n"] == 200 and r["compare"]["datasets"] == ["fr5_v1", "fr5_v2"]
    assert len(r["coverage"]["start"]["count"]) == r["coverage"]["n_cells"] == 47
    assert {c["status"] for c in r["cards"]} <= {"good", "warn", "bad", "info"}
    assert "/home/" not in out.read_text(encoding="utf-8")            # 공개 저장소용: 계정 경로가 결과에 안 나온다


def test_init_spec_and_watch_once():
    sp = TMP / "spec_guess.json"
    run("init-spec", EX / "data" / "v2_layouts_20261103.json", "--out", sp)
    g = json.loads(sp.read_text(encoding="utf-8"))
    assert g["area"]["x"][0] <= -200 and g["area"]["x"][1] >= 266 and {s["name"] for s in g["strata"]} == {"start_slot", "goal_slot"}
    out = TMP / "w.json"
    run("watch", EX / "data" / "v2_layouts_20261103.json", "--spec", sp, "--json", out, "--once")
    st = json.loads((TMP / "w.watch.json").read_text(encoding="utf-8"))
    assert out.is_file() and st["builds"] == 1 and st["stopped"] == "once" and st["n_used"] == 19, st


def test_pipeline_config():
    cfg = TMP / "cfg.json"
    cfg.write_text(json.dumps({
        "spec": str(EX / "spec.json"),
        "datasets": [{"name": "fr5_v1", "path": str(EX / "data" / "v1_feat.json"), "weight": 0.5},
                     {"name": "fr5_v2", "path": str(EX / "data" / "v2_layouts_20261103.json")}],
        "out": {"dir": "out", "json": "result.json", "csv": "episodes.csv", "cards_csv": "cards.csv"}}), encoding="utf-8")
    run("pipeline", cfg)
    r = json.loads((TMP / "out" / "result.json").read_text(encoding="utf-8"))
    rows = (TMP / "out" / "episodes.csv").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1 + 119 and rows[0].startswith("id,dataset,t,outcome") and len(r["cards"]) >= 5


if __name__ == "__main__":
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print(f"ok  {name}")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
