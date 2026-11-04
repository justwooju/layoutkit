#!/usr/bin/env python3
"""캡스톤 예제 — 규칙(뚜껑 색 → 정해진 받침, 검정은 버림 통)을 따르는 가짜 에피소드를 data.py 모양 JSON 으로 만든다.

    python3 examples/capstone_colorsort/make_synth.py [--n 30] [--seed 7] [--out examples/capstone_colorsort/data]

두 묶음:
  skewed.json — 일부러 치우친 묶음: 받침 둘이 늘 같은 자리(빨강 받침 왼쪽 · 초록 받침 오른쪽), 빨강이 70 %, 칸도 늘 끝 쪽.
                출발 쪽만 보면 목표 쪽을 맞힌다(지름길) · 색·칸이 치우친다.
  even.json   — 고른 묶음: spec 의 놓을 수 있는 배치(layoutkit.recommend 검사 통과) 중 무작위, 색은 목표 비율대로.
놓인 자리에는 ±3 mm 잡음을 넣는다(실제 놓인 자리가 기록된다는 뜻).
파일 모양: {"name": 묶음 이름, "weight": 1.0, "episodes": [data.py 에피소드, ...]} — load() 로 Dataset 이 된다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

from layoutkit import data as DA                                          # noqa: E402
from layoutkit import spec as SP                                          # noqa: E402
from layoutkit.recommend import constraints as CN                         # noqa: E402
from layoutkit.recommend import layout as LY                              # noqa: E402
from layoutkit.recommend import sample as SM                              # noqa: E402

COLORS = ["red", "green", "black"]


def _slot_xy(lay, fx, k):
    """고정물 자세(x, y, yaw)와 칸 번호 → 칸 xy."""
    t = next(T for T in lay.types if fx["name"].startswith(T.name))
    u, v = t.offsets[k]
    r = math.radians(fx["yaw"])
    return fx["x"] + u * math.cos(r) - v * math.sin(r), fx["y"] + u * math.sin(r) + v * math.cos(r)


def _episode(i, name, t0, lay, fixtures, color, a, ks, b, kg, rng, noise=3.0):
    fx = {f["name"]: f for f in fixtures}
    sx, sy = _slot_xy(lay, fx[a], ks)
    gx, gy = _slot_xy(lay, fx[b], kg)
    n = lambda: float(rng.uniform(-noise, noise))                        # noqa: E731
    disc = {"color": color, "start_slot": int(ks), "goal_slot": (int(kg) if not b.startswith("bin") else None),
            "start_fixture": a, "goal_fixture": b, "same_fixture": a == b}
    return DA.episode(f"ep_{i:03d}", name, {"x": round(sx + n(), 1), "y": round(sy + n(), 1), "yaw": fx[a]["yaw"]},
                      {"x": round(gx + n(), 1), "y": round(gy + n(), 1), "yaw": fx[b]["yaw"]},
                      t=(t0 + dt.timedelta(minutes=2 * i)).isoformat(timespec="seconds"), outcome="success", source="synth",
                      discrete=disc, fixtures=[dict(f) for f in fixtures], extra={"duration_s": round(float(rng.uniform(18, 30)), 1)})


def skewed(lay, n, rng):
    """치우친 묶음: 받침 자리 고정 · 빨강 70 % · 출발 칸 2·3, 목표 칸 0·1."""
    fixtures = [{"name": "rack0", "x": 150.0, "y": 500.0, "yaw": 0.0}, {"name": "rack1", "x": -150.0, "y": 500.0, "yaw": 0.0},
                {"name": "bin0", "x": 0.0, "y": 630.0, "yaw": 0.0}]
    t0 = dt.datetime(2026, 11, 5, 10, 0, 0)
    out = []
    for i in range(n):
        c = COLORS[int(rng.choice(3, p=[0.7, 0.2, 0.1]))]
        a = {"red": "rack1", "green": "rack0", "black": "rack1"}[c]
        b = {"red": "rack0", "green": "rack1", "black": "bin0"}[c]
        ks = int(rng.choice([2, 3]))
        kg = 0 if b == "bin0" else int(rng.choice([0, 1]))
        out.append(_episode(i, "skewed", t0, lay, fixtures, c, a, ks, b, kg, rng))
    return out


def even(sp, lay, n, rng):
    """고른 묶음: 놓을 수 있는 배치(검사 통과) 중 무작위 · 색은 spec.strata 목표 비율대로."""
    ctx = CN.Context(sp, lay)
    C = SM.sample(lay, 4096, rng)
    ok, _, _ = CN.checks(C, ctx)
    shares = next(s["shares"] for s in sp["strata"] if s["name"] == "color")
    names = lay.instance_names()
    t0 = dt.datetime(2026, 11, 6, 14, 0, 0)
    out = []
    for i in range(n):
        c = COLORS[int(rng.choice(3, p=shares))]
        cand = np.flatnonzero(ok & (C["disc"]["color"] == COLORS.index(c)))
        j = int(rng.choice(cand))
        fixtures = [{"name": names[f], "x": round(float(C["P"][j, f, 0]), 1), "y": round(float(C["P"][j, f, 1]), 1),
                     "yaw": round(float(C["yaw"][j, f]), 1)} for f in range(len(names))]
        out.append(_episode(i, "even", t0, lay, fixtures, c, names[int(C["a"][j])], int(C["ks"][j]), names[int(C["b"][j])],
                            int(C["kg"][j]), rng))
    return out


def load(path, weight=None) -> DA.Dataset:
    """make_synth 가 만든 JSON → Dataset."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return DA.Dataset(d["name"], d["episodes"], weight=d.get("weight", 1.0) if weight is None else weight)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=30, help="묶음마다 에피소드 수")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=str(HERE / "data"))
    a = ap.parse_args(argv)
    sp = SP.load(HERE / "spec.json")
    lay = LY.parse(sp)
    rng = np.random.default_rng(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, eps in (("skewed", skewed(lay, a.n, rng)), ("even", even(sp, lay, a.n, rng))):
        p = out / f"{name}.json"
        p.write_text(json.dumps({"name": name, "weight": 1.0, "episodes": eps}, ensure_ascii=False, indent=1), encoding="utf-8")
        cols = {c: sum(1 for e in eps if e["discrete"]["color"] == c) for c in COLORS}
        print(f"{p}: {len(eps)}판 · 색 {cols}")


if __name__ == "__main__":
    main()
