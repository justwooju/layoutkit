#!/usr/bin/env python3
"""작은 LeRobot v2.1 데이터셋 만들기 — 알고 있는 집는 자리·놓는 자리로 가짜 집어 옮기기 궤적(에피소드 6~10개).

어댑터(layoutkit.adapters.lerobot)가 궤적 사건으로 찾은 자리가 참값과 맞는지 보는 데 쓴다(truth.json 에 참값, mm).
상태 observation.state = [x, y, z (m), roll, pitch, yaw (rad), gripper(폭 m — 0.08 엶, 0.035 쥠)], fps 30.
잡음: 위치 σ 0.3 mm, 그리퍼 σ 0.5 mm, 옮기는 중 그리퍼 값 한 프레임 튐(일부 에피소드) — 사건 찾기가 잡음에 견디는지.

    python3 examples/lerobot_demo/make_lerobot.py OUT_DIR [--n 8] [--seed 0]
    python3 -m layoutkit analyze OUT_DIR --json result.json

parquet 쓰기에 pyarrow 가 필요하다. make_episode(궤적 열 만들기)는 numpy 만 쓴다.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

FPS = 30
NAMES = ["x", "y", "z", "roll", "pitch", "yaw", "gripper"]
OPEN, CLOSED = 0.08, 0.035
TASK = "pick the cube and place it on the target"


def _smooth(s):
    s = np.clip(s, 0.0, 1.0)
    return s * s * (3 - 2 * s)


def make_episode(rng, pick_mm, place_mm, yaw_deg=0.0, fps=FPS, noise_mm=0.3, blip=False) -> dict:
    """한 에피소드 열(dict: 열 이름 → 프레임 목록). pick_mm·place_mm = (x, y) mm."""
    px, py = pick_mm[0] / 1000.0, pick_mm[1] / 1000.0
    qx, qy = place_mm[0] / 1000.0, place_mm[1] / 1000.0
    home = (0.30, 0.0, 0.30)
    yaw0, yaw1 = 0.0, math.radians(yaw_deg)
    # (끝 시각, 목표 xyz, 목표 yaw, 그리퍼) — 구간 안은 smoothstep
    seg = [(0.5, home, yaw0, OPEN), (2.0, (px, py, 0.20), yaw1, OPEN), (3.0, (px, py, 0.05), yaw1, OPEN),
           (3.5, (px, py, 0.05), yaw1, OPEN), (3.9, (px, py, 0.05), yaw1, CLOSED), (4.3, (px, py, 0.05), yaw1, CLOSED),
           (5.3, (px, py, 0.20), yaw1, CLOSED), (7.0, (qx, qy, 0.20), yaw1, CLOSED), (8.0, (qx, qy, 0.07), yaw1, CLOSED),
           (8.4, (qx, qy, 0.07), yaw1, CLOSED), (8.8, (qx, qy, 0.07), yaw1, OPEN), (9.2, (qx, qy, 0.07), yaw1, OPEN),
           (10.2, (qx, qy, 0.22), yaw1, OPEN), (11.5, home, yaw0, OPEN)]
    T = seg[-1][0]
    n = int(T * fps) + 1
    t = np.arange(n) / fps
    P = np.zeros((n, 3))
    Y = np.zeros(n)
    Gp = np.zeros(n)
    prev_t, prev = 0.0, (home, yaw0, OPEN)
    k = 0
    for i, ti in enumerate(t):
        while k < len(seg) - 1 and ti > seg[k][0]:
            prev_t, prev = seg[k][0], (seg[k][1], seg[k][2], seg[k][3])
            k += 1
        te, pe, ye, ge = seg[k]
        s = _smooth((ti - prev_t) / max(1e-9, te - prev_t))
        P[i] = np.asarray(prev[0]) + (np.asarray(pe) - np.asarray(prev[0])) * s
        Y[i] = prev[1] + (ye - prev[1]) * s
        Gp[i] = prev[2] + (ge - prev[2]) * s
    P += rng.normal(0.0, noise_mm / 1000.0, P.shape)
    Gp += rng.normal(0.0, 0.0005, n)
    if blip:                                                         # 옮기는 중 그리퍼 센서 값 한 프레임 튐
        j = int(6.0 * fps)
        Gp[j] = OPEN
    state = np.c_[P, np.full(n, math.pi), np.zeros(n), Y, Gp].astype(np.float32)
    action = np.r_[state[1:], state[-1:]]
    return {"observation.state": state.tolist(), "action": action.tolist(), "timestamp": t.astype(np.float32).tolist(),
            "frame_index": list(range(n)), "task_index": [0] * n}


def make(out_dir, n=8, seed=0, fps=FPS) -> list[dict]:
    """참값 목록(에피소드마다 pick·place mm)과 함께 에피소드 열들을 만든다(쓰기 전)."""
    rng = np.random.default_rng(seed)
    eps = []
    for i in range(int(n)):
        pick = (float(rng.uniform(250, 450)), float(rng.uniform(-200, 200)))
        while True:
            place = (float(rng.uniform(250, 450)), float(rng.uniform(-200, 200)))
            if math.hypot(place[0] - pick[0], place[1] - pick[1]) > 60:
                break
        cols = make_episode(rng, pick, place, yaw_deg=float(rng.uniform(-40, 40)), fps=fps, blip=(i % 3 == 1))
        eps.append({"episode_index": i, "pick_mm": [round(pick[0], 2), round(pick[1], 2)],
                    "place_mm": [round(place[0], 2), round(place[1], 2)], "cols": cols})
    return eps


def info_json(eps, fps=FPS) -> dict:
    tot = sum(len(e["cols"]["timestamp"]) for e in eps)
    return {"codebase_version": "v2.1", "robot_type": "fake_arm", "total_episodes": len(eps), "total_frames": tot,
            "total_tasks": 1, "total_videos": 0, "total_chunks": 1, "chunks_size": 1000, "fps": fps,
            "splits": {"train": f"0:{len(eps)}"},
            "data_path": "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
            "video_path": None,
            "features": {"observation.state": {"dtype": "float32", "shape": [7], "names": NAMES},
                         "action": {"dtype": "float32", "shape": [7], "names": NAMES},
                         "timestamp": {"dtype": "float32", "shape": [1], "names": None},
                         "frame_index": {"dtype": "int64", "shape": [1], "names": None},
                         "episode_index": {"dtype": "int64", "shape": [1], "names": None},
                         "index": {"dtype": "int64", "shape": [1], "names": None},
                         "task_index": {"dtype": "int64", "shape": [1], "names": None}}}


def write(out_dir, eps, fps=FPS) -> Path:
    """LeRobot v2.1 폴더로 쓴다(pyarrow 필요)."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        sys.exit("pyarrow 가 필요하다: pip install pyarrow")
    root = Path(out_dir)
    (root / "meta").mkdir(parents=True, exist_ok=True)
    (root / "data" / "chunk-000").mkdir(parents=True, exist_ok=True)
    gidx = 0
    with (root / "meta" / "episodes.jsonl").open("w", encoding="utf-8") as fe:
        for e in eps:
            c = dict(e["cols"])
            n = len(c["timestamp"])
            c["episode_index"] = [e["episode_index"]] * n
            c["index"] = list(range(gidx, gidx + n))
            gidx += n
            tb = pa.table({"observation.state": pa.array(c["observation.state"], type=pa.list_(pa.float32())),
                           "action": pa.array(c["action"], type=pa.list_(pa.float32())),
                           "timestamp": pa.array(c["timestamp"], type=pa.float32()),
                           "frame_index": pa.array(c["frame_index"], type=pa.int64()),
                           "episode_index": pa.array(c["episode_index"], type=pa.int64()),
                           "index": pa.array(c["index"], type=pa.int64()),
                           "task_index": pa.array(c["task_index"], type=pa.int64())})
            pq.write_table(tb, root / "data" / "chunk-000" / f"episode_{e['episode_index']:06d}.parquet")
            fe.write(json.dumps({"episode_index": e["episode_index"], "tasks": [TASK], "length": n}) + "\n")
    (root / "meta" / "tasks.jsonl").write_text(json.dumps({"task_index": 0, "task": TASK}) + "\n", encoding="utf-8")
    (root / "meta" / "info.json").write_text(json.dumps(info_json(eps, fps), indent=1), encoding="utf-8")
    truth = [{"episode_index": e["episode_index"], "pick_mm": e["pick_mm"], "place_mm": e["place_mm"]} for e in eps]
    (root / "truth.json").write_text(json.dumps(truth, indent=1), encoding="utf-8")
    return root


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    if not 1 <= a.n <= 200:
        sys.exit("--n 은 1~200")
    root = write(a.out, make(a.out, a.n, a.seed))
    print(f"LeRobot v2.1 데이터셋 {a.n}개 에피소드: {root} (참값 truth.json)")


if __name__ == "__main__":
    main()
