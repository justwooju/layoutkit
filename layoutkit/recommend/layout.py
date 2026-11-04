"""spec.layout 해석 — 추천이 고르는 배치 변수의 모양.

두 가지(docs/ARCHITECTURE.md 4절):

  "points"   — 집는 자리(start)·놓는 자리(goal)를 목표 영역 안에서 직접 고른다.
      {"kind": "points", "min_move_mm": 30,
       "start_area": null, "goal_area": null,          # null = spec.area
       "start_yaw": null | [lo, hi], "goal_yaw": null | [lo, hi], "yaw_period_deg": 360,
       "start_z_mm": 0, "goal_z_mm": 0,                # 화면 검사(in_view)에 쓰는 높이
       "discrete": [{"name": "color", "values": ["red", "blue"]}]}

  "fixtures" — 받침 같은 고정물을 놓고, 물건을 고정물의 칸(slot)에 둔다(받침 과제와 같은 θ).
      {"kind": "fixtures",
       "fixtures": [{"name": "rack", "count": 2, "size_mm": [170, 40], "height_mm": 60, "z_top_mm": 106.44,
                     "slots": 4, "pitch_mm": 37.18, "slot_axis": "length",     # 또는 "slots_xy": [[u, v], ...](고정물 프레임)
                     "hole_r_mm": 15, "yaw_range": null, "yaw_period_deg": 180,
                     "poses": null | [{"x":, "y":, "yaw":}, ...],              # 있으면 그 자리에 고정(뽑지 않는다)
                     "areas": null | [{"x": [lo, hi], "y": [lo, hi]}, ...],     # 인스턴스마다 가운데가 들 영역(없으면 spec.area)
                     "order": "x" | "fixed"}],                                # x = 같은 형식끼리 x 작은 쪽부터 번호(인식과 같게)
       "items": [{"name": "red", "role": "start", "on": "rack", "symbol": "R", "above_mm": 50, ...},
                 {"name": "yellow", "role": "obstacle", "symbol": "Y"},       # 장애물은 start 와 같은 고정물의 다른 칸
                 {"name": "ring", "role": "goal", "on": "rack"}],
       "same_fixture_allowed": true,
       "yaw_window": {"center_deg": 47, "half_deg": 54} | {"grid": {"x": [...], "y": [...], "center_deg": [[...]]}, "half_deg": 54},
       "discrete": [{"name": "color", "values": [...]}],                     # 추천이 함께 고르는 이산 변수
       "rule": {"by": "color", "goal": {"red": {"fixture": "rack", "index": 0}, ...}, "start_differs": true},
       "episode_yaw_offset_deg": null | -90}                                  # 에피소드 yaw → 고정물 줄 방향(아래)

배치 하나: start = (고정물 a 의 칸 ks), goal = (고정물 b 의 칸 kg). 특징 g = (start xy, ψ_a), q = (goal xy, ψ_b) — rackrec 과 같다.
"""
from __future__ import annotations

import math

import numpy as np

KINDS = ("points", "fixtures")


# ---------------------------------------------------------------- 각
def wrap(a, period=180.0):
    """[−p/2, p/2) 로 감기 — rackrec.wrap90 의 일반화(받침 줄 방향은 180° 주기)."""
    h = float(period) / 2.0
    return (np.asarray(a, float) + h) % float(period) - h


def canon(a, period=180.0):
    """(−p/2, p/2] — rackrec.canon(= rackgeo.canon_yaw) 의 일반화."""
    h = float(period) / 2.0
    y = (np.asarray(a, float) + h) % float(period) - h
    return np.where(y == -h, h, y)


def _area_tuple(a, fallback):
    if a is None:
        a = fallback
    if isinstance(a, dict):
        return (float(a["x"][0]), float(a["x"][1]), float(a["y"][0]), float(a["y"][1]))
    return tuple(float(v) for v in a)


# ---------------------------------------------------------------- 손목 창(줄 방향 창)
class YawWindow:
    """고정물 줄 방향(또는 물건 yaw)이 들어야 하는 창: 가운데 ψ_c(x, y) ± half.
    가운데는 상수(center_deg) 또는 격자(grid — 이중선형 보간, rackrec.World.psi_c 와 같은 식)."""

    def __init__(self, d: dict, period=180.0):
        self.period = float(period)
        self.half = float(d.get("half_deg", 90.0))
        g = d.get("grid")
        self.grid = None
        if g:
            self.grid = (np.asarray(g["x"], float), np.asarray(g["y"], float), np.asarray(g["center_deg"], float))
            if self.grid[2].shape != (len(self.grid[1]), len(self.grid[0])):
                raise ValueError("yaw_window.grid.center_deg 는 len(y) × len(x) 이어야 한다")
        self.const = float(d.get("center_deg", 0.0)) if self.grid is None else None

    def center(self, x, y):
        if self.grid is None:
            return np.full(np.shape(x), self.const, float)
        xs, ys, C = self.grid
        x, y = np.clip(np.asarray(x, float), xs[0], xs[-1]), np.clip(np.asarray(y, float), ys[0], ys[-1])
        i = np.clip(np.searchsorted(xs, x) - 1, 0, len(xs) - 2)
        j = np.clip(np.searchsorted(ys, y) - 1, 0, len(ys) - 2)
        tx, ty = (x - xs[i]) / (xs[i + 1] - xs[i]), (y - ys[j]) / (ys[j + 1] - ys[j])
        return (C[j, i] * (1 - tx) * (1 - ty) + C[j, i + 1] * tx * (1 - ty) + C[j + 1, i] * (1 - tx) * ty + C[j + 1, i + 1] * tx * ty)


class YawRange:
    """방향 칸을 세는 기준: 가운데 c0 · 폭 Psi(rackrec: 손목 창 가운데(목표 영역 가운데) · 2×창 반폭)."""

    def __init__(self, c0, Psi, period):
        self.c0, self.Psi, self.period = float(c0), float(min(Psi, period)), float(period)

    def n_bins(self, h_psi) -> int:
        return max(1, int(math.ceil(self.Psi / (2.0 * float(h_psi)) - 1e-9)))

    def bin(self, psi, h_psi):
        """rackrec.World.psi_bin 과 같은 식."""
        d = wrap(np.asarray(psi, float) - self.c0, self.period) + self.Psi / 2.0
        return np.clip((d // (2.0 * float(h_psi))).astype(int), 0, self.n_bins(h_psi) - 1)


# ---------------------------------------------------------------- 고정물
class FixtureType:
    def __init__(self, d: dict, idx: int, table_z: float):
        self.idx = idx
        self.name = str(d.get("name") or f"fixture{idx}")
        self.count = int(d.get("count", 1))
        L, W = (d.get("size_mm") or [100.0, 40.0])[:2]
        self.L, self.W = float(L), float(W)
        self.height = float(d.get("height_mm") or 0.0)
        self.z_top = float(d["z_top_mm"]) if d.get("z_top_mm") is not None else table_z + self.height
        self.z_table = self.z_top - self.height
        self.hole_r = float(d.get("hole_r_mm") or 0.0)
        self.period = float(d.get("yaw_period_deg") or 180.0)
        self.yaw_range = list(map(float, d["yaw_range"])) if d.get("yaw_range") is not None else None
        axis = str(d.get("slot_axis") or "length")
        self.row_deg = 0.0 if axis == "length" else 90.0           # 칸 줄 방향(고정물 프레임) — view_angle
        if d.get("slots_xy"):
            off = np.asarray(d["slots_xy"], float).reshape(-1, 2)
        else:
            n = int(d.get("slots", 1))
            pitch = float(d.get("pitch_mm") or 0.0)
            s = (np.arange(n) - (n - 1) / 2.0) * pitch             # rackgeo: 구멍 i 중심 = (i − (n−1)/2)·간격
            off = np.column_stack([s, np.zeros(n)]) if axis == "length" else np.column_stack([np.zeros(n), s])
        self.offsets = off
        self.n_slots = len(off)
        self.pitch = float(d.get("pitch_mm") or 0.0)
        self.m = float(np.hypot(off[:, 0], off[:, 1]).max()) if len(off) else 0.0   # 칸 줄 반 길이(rackrec: 1.5 × 간격)
        poses = d.get("poses") if d.get("poses") is not None else d.get("pose")
        if isinstance(poses, dict):
            poses = [poses]
        self.poses = [{"x": float(p["x"]), "y": float(p["y"]), "yaw": float(p.get("yaw", 0.0))} for p in poses] if poses else None
        if self.poses is not None and len(self.poses) < self.count:
            raise ValueError(f"고정물 {self.name}: poses 가 count 보다 적다")
        self.areas = d.get("areas")
        self.order = str(d.get("order") or ("fixed" if (self.poses or self.areas) else "x"))
        self.raw = d


class Instance:
    def __init__(self, ftype: FixtureType, k: int, area):
        self.type, self.k = ftype, k
        self.name = f"{ftype.name}{k}"
        self.pose = ftype.poses[k] if ftype.poses else None
        a = (ftype.areas or [None] * ftype.count)[k] if ftype.areas else None
        self.area = _area_tuple(a, area)


class Item:
    def __init__(self, d: dict, default_on: str | None):
        self.name = str(d.get("name") or d.get("role"))
        self.role = str(d.get("role") or "start")
        self.on = d.get("on") or default_on
        self.symbol = str(d.get("symbol") or self.name[:1].upper())
        self.above = float(d.get("above_mm") or 0.0)                  # 꽂혔을 때 윗판 → 꼭대기
        self.cap_r = float(d.get("cap_r_mm") or 0.0)
        self.cap_h = float(d.get("cap_h_mm") or 0.0)
        self.tube_r = float(d.get("tube_r_mm") or self.cap_r)
        self.h = float(d.get("h_mm") or 0.0)                          # 표시물(링) 높이
        self.w = float(d.get("w_mm") if d.get("w_mm") is not None else 3.0)       # 링 띠 폭(rackrec 기본)
        self.gap = float(d.get("gap_mm") if d.get("gap_mm") is not None else 1.5)  # 구멍 가장자리 → 링 안쪽
        self.raw = d


# ---------------------------------------------------------------- 전체
class Layout:
    def __init__(self, spec: dict):
        lay = spec.get("layout") or {"kind": "points"}
        self.raw = lay
        self.kind = str(lay.get("kind") or "points")
        if self.kind not in KINDS:
            raise ValueError(f"layout.kind 는 {KINDS} 중 하나: {self.kind}")
        if spec.get("area") is None:
            raise ValueError("추천에는 spec.area(목표 영역)가 있어야 한다")
        self.area = _area_tuple(spec["area"], None)
        sc = spec.get("scales") or {}
        self.h_xy = float(sc.get("h_xy_mm", 30.0))
        self.h_psi = float(sc.get("h_yaw_deg", 20.0))
        self.use_yaw = bool(sc.get("use_yaw", True))
        self.near_mm = float(spec.get("near_mm", 100.0))
        self.table_z = float(lay.get("table_z_mm") or 0.0)
        self.discrete = [{"name": str(v["name"]), "values": list(v["values"])} for v in lay.get("discrete") or []]
        self.rule = lay.get("rule")
        self.yaw_offset = lay.get("episode_yaw_offset_deg")
        if self.kind == "fixtures":
            self._fixtures(lay)
        else:
            self._points(lay)
        if self.rule:
            by = self.rule.get("by")
            if by not in [v["name"] for v in self.discrete]:
                raise ValueError(f"layout.rule.by={by} 가 layout.discrete 에 없다")

    # -- fixtures
    def _fixtures(self, lay):
        fl = lay.get("fixtures") or []
        if not fl:
            raise ValueError("layout.kind=fixtures 인데 fixtures 가 없다")
        self.types = [FixtureType(d, i, self.table_z) for i, d in enumerate(fl)]
        self.instances = [Instance(t, k, self.area) for t in self.types for k in range(t.count)]
        tn = {t.name: t for t in self.types}
        items = [Item(d, self.types[0].name) for d in (lay.get("items") or [{"name": "start", "role": "start"}, {"name": "goal", "role": "goal"}])]
        st = [it for it in items if it.role == "start"]
        gl = [it for it in items if it.role == "goal"]
        if not st or not gl:
            raise ValueError("layout.items 에 role start 와 goal 이 하나씩 있어야 한다")
        self.start, self.goal = st[0], gl[0]
        self.obstacles = [it for it in items if it.role == "obstacle"]
        for it in self.obstacles:
            it.on = self.start.on                                     # 장애물은 start 와 같은 고정물(rackrec: 노랑은 빨강 받침)
        for it in (self.start, self.goal):
            if it.on not in tn:
                raise ValueError(f"item {it.name}: on={it.on} 인 고정물이 없다")
        self.items = items
        self.start_type, self.goal_type = tn[self.start.on], tn[self.goal.on]
        if self.rule:
            for v, tgt in (self.rule.get("goal") or {}).items():
                if tgt.get("fixture") not in tn:
                    raise ValueError(f"layout.rule.goal.{v}: 고정물 {tgt.get('fixture')} 이 없다")
        if self.start_type.n_slots < 1 + len(self.obstacles):
            raise ValueError("start 고정물 칸이 start + 장애물 수보다 적다")
        self.same_allowed = bool(lay.get("same_fixture_allowed", True))
        self.window = YawWindow(lay["yaw_window"], self.start_type.period) if lay.get("yaw_window") else None
        self.period_s, self.period_g = self.start_type.period, self.goal_type.period
        self.yr_s = self._yaw_range(self.start_type)
        self.yr_g = self._yaw_range(self.goal_type)

    def _yaw_range(self, t: FixtureType) -> YawRange:
        if t.poses is not None:
            ys = [p["yaw"] for p in t.poses]
            return YawRange(float(np.mean(ys)), 2.0 * self.h_psi, t.period)   # 고정 — 방향 칸 하나 남짓
        if t.yaw_range is not None:
            lo, hi = t.yaw_range
            return YawRange((lo + hi) / 2.0, hi - lo, t.period)
        if self.window is not None:
            x0, x1, y0, y1 = self.area
            c0 = float(canon(self.window.center(np.array([(x0 + x1) / 2]), np.array([(y0 + y1) / 2]))[0], t.period))
            return YawRange(c0, 2.0 * self.window.half, t.period)   # rackrec: Psi = min(180, 2·jw_eff), psi_c0 = 목표 영역 가운데
        return YawRange(0.0, t.period, t.period)

    def type_uses_window(self, t: FixtureType) -> bool:
        return self.window is not None and t.poses is None and t.yaw_range is None

    def instance_names(self):
        return [I.name for I in self.instances]

    def top_z(self, t: FixtureType) -> float:
        """고정물 꼭대기 높이(물건이 꽂혔을 때) — in_view 의 윗면 모서리(rackrec: z_top + tube_above)."""
        ab = [it.above for it in getattr(self, "items", []) if it.on == t.name and it.role in ("start", "obstacle")]
        return t.z_top + (max(ab) if ab else 0.0)

    def start_z(self) -> float:
        """정책 입력 칸을 정할 start 높이(rackrec: 빨강 뚜껑 윗면) · goal 높이(링 칸 구멍 = 윗판)."""
        if self.kind == "points":
            return float(self.raw.get("start_z_mm") or 0.0)
        return self.start_type.z_top + self.start.above

    def goal_z(self) -> float:
        if self.kind == "points":
            return float(self.raw.get("goal_z_mm") or 0.0)
        return self.goal_type.z_top

    # -- points
    def _points(self, lay):
        self.types, self.instances, self.obstacles, self.items = [], [], [], []
        self.start = self.goal = None
        self.start_area = _area_tuple(lay.get("start_area"), spec_area(self.area))
        self.goal_area = _area_tuple(lay.get("goal_area"), spec_area(self.area))
        self.min_move = float(lay.get("min_move_mm") or 0.0)
        per = float(lay.get("yaw_period_deg") or 360.0)
        self.period_s = self.period_g = per
        self.start_yaw = list(map(float, lay["start_yaw"])) if lay.get("start_yaw") is not None else None
        self.goal_yaw = list(map(float, lay["goal_yaw"])) if lay.get("goal_yaw") is not None else None
        self.window = YawWindow(lay["yaw_window"], per) if lay.get("yaw_window") else None
        self.yr_s = YawRange(np.mean(self.start_yaw), self.start_yaw[1] - self.start_yaw[0], per) if self.start_yaw else YawRange(0, per, per)
        self.yr_g = YawRange(np.mean(self.goal_yaw), self.goal_yaw[1] - self.goal_yaw[0], per) if self.goal_yaw else YawRange(0, per, per)
        self.same_allowed = True

    # -- 방향 칸
    def n_psi(self, side: str) -> int:
        if not self.use_yaw or (self.kind == "points" and (self.start_yaw if side == "start" else self.goal_yaw) is None):
            return 1
        return (self.yr_s if side == "start" else self.yr_g).n_bins(self.h_psi)

    def psi_bin(self, psi, side: str):
        if self.n_psi(side) == 1:
            return np.zeros(np.shape(psi), int)
        return (self.yr_s if side == "start" else self.yr_g).bin(psi, self.h_psi)

    def yaw_used(self, side: str) -> bool:
        """거리·칸에 방향을 넣나 — points 에서 yaw 를 안 뽑으면 넣지 않는다(데이터 yaw 도 0 으로 본다)."""
        if not self.use_yaw:
            return False
        if self.kind == "points":
            return (self.start_yaw if side == "start" else self.goal_yaw) is not None
        return True


def spec_area(a):
    x0, x1, y0, y1 = a
    return {"x": [x0, x1], "y": [y0, y1]}


def parse(spec: dict) -> Layout:
    return Layout(spec)
