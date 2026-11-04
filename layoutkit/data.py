"""에피소드·데이터셋 공통 모양. 모든 어댑터가 이 모양을 내고, 분석·추천·화면은 이 모양만 읽는다.

에피소드 하나 = dict (JSON 으로 그대로 저장된다):

    {
      "id":       "fr5_v1/ep_007",          # 데이터셋 이름 / 에피소드 이름 — 데이터셋 안에서 유일
      "dataset":  "fr5_v1",
      "t":        "2026-11-01T18:29:08",     # 기록 시각(ISO, 없으면 None)
      "outcome":  "success",                 # success | fail | unsure | None
      "weight":   1.0,                       # 학습 때 뽑힐 무게(데이터셋 무게 × 에피소드 무게)
      "source":   "fr5rec",                  # fr5rec | lerobot | table | synth
      "start":    {"x": 240.3, "y": 579.8, "yaw": 77.2, "z": 131.4},   # 물체를 집은 자리(mm, 베이스 좌표). yaw·z 는 없어도 된다
      "goal":     {"x": -29.3, "y": 573.7, "yaw": 77.2},               # 물체를 놓은 자리
      "discrete": {"start_slot": 3, "goal_slot": 0, "arrangement": "Y○○R", "same_fixture": False},
      "fixtures": [{"name": "rack0", "x": 120.0, "y": 560.0, "yaw": 47.0}],   # 선택 — 받침처럼 놓는 물건
      "extra":    {"duration_s": 23.1, "path_mm": 812.0, "n_frames": 231},    # 선택 — 숫자만
      "thumbs":   {"third": "path/or/data-uri", "wrist": "..."},             # 선택 — 화면 썸네일
      "flags":    []                         # 분석이 붙이는 표시(중복·시험 배치 근처 등)
    }

좌표 약속: x·y 는 mm, 같은 데이터셋 안에서 같은 기준(보통 로봇 베이스). 화면 방향(어느 쪽이 왼쪽인가)은 spec 의 frame 에 적는다.
"""
from __future__ import annotations

import copy
import math
from typing import Iterable

EPISODE_KEYS = ("id", "dataset", "t", "outcome", "weight", "source", "start", "goal", "discrete", "fixtures", "extra", "thumbs", "flags")


def episode(id, dataset, start, goal, t=None, outcome=None, weight=1.0, source="table", discrete=None, fixtures=None,
            extra=None, thumbs=None) -> dict:
    """에피소드 하나를 만든다(빠진 칸은 기본값). start/goal 은 {"x","y"[, "yaw", "z"]}."""
    return {"id": str(id), "dataset": str(dataset), "t": t, "outcome": outcome, "weight": float(weight), "source": source,
            "start": _pt(start), "goal": _pt(goal), "discrete": dict(discrete or {}), "fixtures": list(fixtures or []),
            "extra": {k: float(v) for k, v in (extra or {}).items() if _num(v)}, "thumbs": dict(thumbs or {}), "flags": []}


def _num(v) -> bool:
    try:
        return v is not None and math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def _pt(p) -> dict | None:
    if p is None:
        return None
    out = {}
    for k in ("x", "y", "yaw", "z"):
        if k in p and _num(p[k]):
            out[k] = float(p[k])
    return out if ("x" in out and "y" in out) else None


def valid(ep: dict) -> bool:
    """분석에 쓸 수 있나: 집은 자리와 놓은 자리가 둘 다 있다."""
    return bool(ep.get("start")) and bool(ep.get("goal"))


class Dataset:
    """에피소드 묶음. weight = 학습 때 이 묶음 전체에 곱하는 무게(예: 예전 데이터 0.5)."""

    def __init__(self, name: str, episodes: Iterable[dict], weight: float = 1.0, meta: dict | None = None):
        self.name = str(name)
        self.weight = float(weight)
        self.meta = dict(meta or {})
        self.episodes = []
        for e in episodes:
            e = copy.deepcopy(e)
            e["dataset"] = self.name
            e["weight"] = float(e.get("weight", 1.0)) * self.weight
            self.episodes.append(e)

    def __len__(self):
        return len(self.episodes)

    def usable(self) -> list[dict]:
        return [e for e in self.episodes if valid(e)]

    def summary(self) -> dict:
        n_ok = sum(1 for e in self.episodes if e.get("outcome") == "success")
        return {"name": self.name, "n": len(self.episodes), "n_usable": len(self.usable()), "n_success": n_ok,
                "weight": self.weight, "meta": self.meta}


def merge(datasets: Iterable[Dataset]) -> list[dict]:
    """여러 데이터셋 → 쓸 수 있는 에피소드 한 줄(무게 포함)."""
    out = []
    for d in datasets:
        out += d.usable()
    return out
