"""과제 선언(spec). 분석 눈금·목표 영역·이산 칸·추천용 배치 모양·제약을 한 파일(JSON 또는 YAML)에 적는다.

최소 예(분석만):

    {"task": "pick_place", "area": {"x": [-200, 270], "y": [450, 650]}}

전체 키와 기본값은 DEFAULTS. 사용자가 준 값이 DEFAULTS 위에 덮인다(묶음은 안쪽 키만).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

DEFAULTS: dict = {
    "task": "pick_place",
    "title": None,                         # 화면 제목(없으면 task)
    "units": "mm",
    "frame": {                             # 좌표 뜻 — 화면 방향만 정한다
        "x_label": None, "y_label": None,   # 없으면 화면 사전의 축 이름(x [mm] · y [mm])
        "x_left_positive": False,          # True 면 지도에서 +x 를 왼쪽에 그린다(로봇 뒤에서 앞을 본 모습)
        "note": "",
    },
    "area": None,                          # {"x": [lo, hi], "y": [lo, hi]} — 집는 자리·놓는 자리의 목표 영역(없으면 데이터 범위 + 여유)
    "scales": {"h_xy_mm": 30.0,            # 육각 칸 반지름 = 거리 눈금
               "h_yaw_deg": 20.0,          # 방향 칸 반폭
               "use_yaw": True},           # 데이터에 yaw 가 있으면 칸에 방향도 넣는다
    "near_mm": 100.0,                      # 이 거리 이하로 옮기면 '가까이'
    "targets": {"rho_max": 0.3,            # |ρ| 목표 상한(좋음)
                "rho_bad": 0.5,            # 넘으면 나쁨
                "near_share": 0.25,        # 가까이 비율 목표 하한
                "near_warn": 0.10,
                "predict_good": 0.65,      # 출발만으로 목표 쪽을 맞히는 정확도(우연 0.5) — 이하면 좋음
                "predict_bad": 0.80,
                "coverage_good": 0.80,     # 채운 칸 / 놓을 수 있는 칸
                "coverage_warn": 0.50,
                "strata_dev_good": 0.10,   # 이산 칸 비율이 목표에서 벗어난 최대값
                "strata_dev_bad": 0.25,
                "dup_mm": 12.0},           # 이 거리 안이면 '같은 자리'
    "strata": [],                          # [{"name": "goal_slot", "values": [0,1,2,3], "shares": null(=고르게)}]
    "pairs": [["start.x", "goal.x"], ["start.y", "goal.y"]],    # 지름길 상관을 볼 (출발, 목표) 짝
    "layout": None,                        # 추천용 배치 모양 — layoutkit.recommend 가 읽는다(docs/SPEC.md)
    "constraints": [],                     # 추천 제약 — [{"type": "gap", "min_mm": 60}, {"type": "in_view", "camera": "third", "margin_px": 16}, ...]
    "cameras": [],                         # [{"name": "third", "width": 848, "height": 480, "K": [[fx,0,cx],[0,fy,cy],[0,0,1]],
                                           #   "dist": [k1,k2,p1,p2,k3] | null, "T_cam_base": 4×4}] — 보임 검사·화면 그림
    "holdout": 0,                          # 시험 전용 배치 수(k-center) — 0 이면 안 뗀다
    "recommend": {"n_cand": 4096, "top_k": 30, "temp": 0.15, "seed": None,
                  "weights": {"alpha": 0.5, "beta": 0.3, "eta": 1.0, "gamma": 0.15}},
    "lang": "ko",                          # 화면 말: ko | en
    "dataset_colors": {},                  # {데이터셋 이름: "#RRGGBB"} — 없으면 Okabe–Ito 순서(파랑·주황·초록 …)
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load(path_or_dict=None) -> dict:
    """spec 파일(JSON·YAML) 또는 dict → 기본값을 채운 spec. None 이면 기본값만."""
    if path_or_dict is None:
        user = {}
    elif isinstance(path_or_dict, dict):
        user = path_or_dict
    else:
        p = Path(path_or_dict)
        txt = p.read_text(encoding="utf-8")
        if p.suffix.lower() in (".yaml", ".yml"):
            try:
                import yaml                    # 선택 의존
            except ImportError as e:
                raise RuntimeError("YAML spec 은 PyYAML 이 필요하다(pip install pyyaml) — 아니면 JSON 으로 쓴다") from e
            user = yaml.safe_load(txt) or {}
        else:
            user = json.loads(txt)
        user.setdefault("_source", str(p))
    sp = _merge(DEFAULTS, user)
    check(sp)
    return sp


def check(sp: dict) -> None:
    """모양 검사 — 틀리면 ValueError(무엇이 틀렸는지)."""
    a = sp.get("area")
    if a is not None:
        for k in ("x", "y"):
            v = a.get(k)
            if not (isinstance(v, (list, tuple)) and len(v) == 2 and float(v[0]) < float(v[1])):
                raise ValueError(f"area.{k} 는 [작은 값, 큰 값] 이어야 한다: {v}")
    if float(sp["scales"]["h_xy_mm"]) <= 0:
        raise ValueError("scales.h_xy_mm 는 0 보다 커야 한다")
    for s in sp.get("strata") or []:
        if "name" not in s or not s.get("values"):
            raise ValueError(f"strata 항목에는 name 과 values 가 있어야 한다: {s}")
        sh = s.get("shares")
        if sh is not None and (len(sh) != len(s["values"]) or abs(sum(sh) - 1.0) > 1e-6):
            raise ValueError(f"strata {s['name']}: shares 는 values 와 길이가 같고 합이 1 이어야 한다")
    for pr in sp.get("pairs") or []:
        if not (isinstance(pr, (list, tuple)) and len(pr) == 2):
            raise ValueError(f"pairs 항목은 [출발 특징, 목표 특징]: {pr}")
    if sp.get("lang") not in ("ko", "en"):
        raise ValueError("lang 은 ko 또는 en")


def area_from_data(episodes, pad_mm: float = 30.0) -> dict:
    """spec 에 area 가 없을 때: 집은·놓은 자리 전체 범위 + 여유."""
    xs = [e[k]["x"] for e in episodes for k in ("start", "goal") if e.get(k)]
    ys = [e[k]["y"] for e in episodes for k in ("start", "goal") if e.get(k)]
    if not xs:
        return {"x": [-100.0, 100.0], "y": [-100.0, 100.0]}
    return {"x": [min(xs) - pad_mm, max(xs) + pad_mm], "y": [min(ys) - pad_mm, max(ys) + pad_mm]}


def feature(ep: dict, name: str):
    """'start.x' · 'goal.yaw' · 'discrete.goal_slot' · 'extra.duration_s' → 값(없으면 None)."""
    cur = ep
    for part in name.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur
