"""놓을 수 있는 배치 검사(가르치기 없이 spec 만으로) — rackrec.World.checks 의 일반화.

후보 묶음 C(sample.py) 마다 아래 순서로 검사하고, 처음 걸린 검사를 센다(drop — 화면 '조건별로 빠진 수').
  자동: area(spec.area 안에 start·goal) · min_move(points) · yaw_window(layout.yaw_window — 쓰는 고정물의 줄 방향)
  spec.constraints 순서대로:
    {"type": "area", "x": [..], "y": [..], "what": "fixtures" | "points"}        더 좁은 영역(고정물이면 윗판 네 모서리)
    {"type": "reach", "min_mm": 150, "max_mm": 900, "origin": [0, 0]}          베이스에서 거리(고정물이면 모든 칸)
    {"type": "gap", "min_mm": 60}                                              고정물 윗판 사각형끼리 분리축(SAT) 틈
    {"type": "keepout", "polygon": [[x, y], ...] | "circle": {"x", "y", "r"}, "margin_mm": 0, "what": "fixtures"|"points"|"both"}
    {"type": "yaw_window", "center_deg": .., "half_deg": ..}                    layout.yaw_window 대신 따로 줄 때
    {"type": "in_view", "camera": "third", "margin_px": 16, "grow_mm": 20, "roi_px": [[u, v], ...]}
          고정물 바닥(탁자 높이, grow_mm 키움) 네 모서리가 화면(또는 roi) 안 · 꼭대기 높이(윗판 + 물건) 네 모서리가 화면 가장자리 안
    {"type": "view_angle", "camera": "third", "min_deg": 35}                    칸 줄과 위에서 본 시선 사이 각 ≥ min
    {"type": "goal_visible", "camera": "third", "min_frac": 0.7, "min_minor_px": 8, "policy_px": 256, "margin_px": 16}
          goal 표시물(링) 띠 16점이 화면 안이고 start·장애물 원기둥과 다른 고정물 몸통에 안 가림 · 정책 입력에서 짧은 지름 ≥ min
    {"type": "hook", "fn": "module:function", "args": {...}, "stage": "batch" | "final"}
          batch: fn(C, ctx, **args) → 불리언 (N,) · final: fn(option, ctx, **args) → bool 또는 (bool, 이유) — 고른 뒤 몇 개에만(비싼 검사)
카메라·치수가 없어 못 하는 검사는 건너뛰고 ctx.skipped 에 이유를 남긴다(결과 recommend.skipped_checks).

받침 spec 에서 rackrec 과 같은 통과 수를 내도록 식·문턱을 그대로 옮겼다. rackrec 은 ① 하나로 묶어 센 것(영역·탁자·손목 창)을
여기서는 area · yaw_window · reach · in_view 로 나눠 센다 — 통과 집합은 같고 drop 의 나눔만 다르다.
"""
from __future__ import annotations

import contextlib
import importlib
import math
import sys
import warnings
from pathlib import Path

import numpy as np

from .camera import cameras as _cameras
from .layout import Layout, wrap


class Context:
    """검사·점수에 필요한 것: spec · layout · 카메라 · 건너뛴 검사 · final 훅."""

    def __init__(self, spec: dict, lay: Layout):
        self.spec, self.lay = spec, lay
        self.cams, bad = _cameras(spec)
        self.skipped = list(bad)
        self.final_hooks = []
        self._fns = {}

    def cam(self, name):
        return self.cams.get(name) if name else (next(iter(self.cams.values())) if self.cams else None)

    def skip(self, msg):
        if msg not in self.skipped:
            self.skipped.append(msg)

    def load_fn(self, ref: str):
        """'module:function' → 함수. spec 파일 옆 폴더를 먼저 찾는다(예제 훅)."""
        if ref in self._fns:
            return self._fns[ref]
        mod, _, fn = str(ref).partition(":")
        if not mod or not fn:
            raise ValueError(f"hook fn 은 'module:function': {ref}")
        src = self.spec.get("_source")
        added = None
        if src:
            d = str(Path(src).resolve().parent)
            if d not in sys.path:
                sys.path.insert(0, d)
                added = d
        try:
            f = getattr(importlib.import_module(mod), fn)
        finally:
            if added and added in sys.path:
                sys.path.remove(added)
        self._fns[ref] = f
        return f


@contextlib.contextmanager
def _quiet():
    """화면 밖 점만 있는 후보의 nanmean 경고(빈 조각) 끄기 — 값은 rackrec 과 같다(뒤에서 0 으로)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        yield


# ---------------------------------------------------------------- 기하
def footprint(x, y, psi, L, W, grow=0.0):
    """윗판 사각형(위에서 본 네 모서리, 베이스 xy) — 배열 가능(…×4×2). rackrec.footprint 와 같다."""
    x, y, r = np.asarray(x, float), np.asarray(y, float), np.radians(np.asarray(psi, float))
    c, s = np.cos(r), np.sin(r)
    a, b = L / 2 + grow, W / 2 + grow
    out = []
    for u, v in ((-a, -b), (a, -b), (a, b), (-a, b)):
        out.append(np.stack([x + c * u - s * v, y + s * u + c * v], axis=-1))
    return np.stack(out, axis=-2)


def sat_gap_many(A, B):
    """두 볼록 다각형 묶음(N×k×2, N×m×2) 사이 분리축 틈(mm, 0 보다 크면 안 겹침 — 실제 거리의 하한). rackrec.sat_gap_many 일반화(꼭짓점 수 자유)."""
    A, B = np.asarray(A, float), np.asarray(B, float)
    if B.ndim == 2:
        B = np.broadcast_to(B, (A.shape[0],) + B.shape)
    best = np.full(A.shape[0], -np.inf)
    for Q in (A, B):
        k = Q.shape[1]
        for i in range(k):
            e = Q[:, (i + 1) % k] - Q[:, i]
            nrm = np.stack([-e[:, 1], e[:, 0]], axis=1) / np.maximum(np.hypot(e[:, 0], e[:, 1]), 1e-12)[:, None]
            pa, pb = np.einsum("nkd,nd->nk", A, nrm), np.einsum("nkd,nd->nk", B, nrm)
            best = np.maximum(best, np.maximum(pb.min(1) - pa.max(1), pa.min(1) - pb.max(1)))
    return best


def in_polygon(P, poly):
    """점(…×2)이 다각형 안인가(짝수-홀수 규칙, rackrec._in_roi 와 같은 식)."""
    P = np.asarray(P, float)
    shp = P.shape[:-1]
    P = np.nan_to_num(P.reshape(-1, 2), nan=-1e6)
    R_ = np.asarray(poly, float)
    inside = np.zeros(len(P), bool)
    for i in range(len(R_)):
        a, b = R_[i], R_[(i + 1) % len(R_)]
        c1 = (a[1] > P[:, 1]) != (b[1] > P[:, 1])
        xs = a[0] + (P[:, 1] - a[1]) * (b[0] - a[0]) / np.where(b[1] == a[1], 1e-12, b[1] - a[1])
        inside ^= c1 & (P[:, 0] < xs)
    return inside.reshape(shp)


def seg_dist(P, poly):
    """점(…×2)과 다각형 테두리 사이 거리."""
    P = np.asarray(P, float)
    R_ = np.asarray(poly, float)
    best = np.full(P.shape[:-1], np.inf)
    for i in range(len(R_)):
        a, b = R_[i], R_[(i + 1) % len(R_)]
        e = b - a
        t = np.clip(((P - a) @ e) / max(float(e @ e), 1e-12), 0.0, 1.0)
        d = np.linalg.norm(P - (a + t[..., None] * e), axis=-1)
        best = np.minimum(best, d)
    return best


def rect_point_dist(cx, cy, psi, L, W, px, py):
    """고정물 사각형(가운데·방향·크기)과 점 사이 거리(안이면 0)."""
    r = np.radians(psi)
    dx, dy = px - cx, py - cy
    u = np.cos(r) * dx + np.sin(r) * dy
    v = -np.sin(r) * dx + np.cos(r) * dy
    return np.hypot(np.maximum(np.abs(u) - L / 2, 0.0), np.maximum(np.abs(v) - W / 2, 0.0))


def _visible(cam, X, cyls, boxes, margin):
    """점마다 화면 안(가장자리 margin)이고 카메라 → 점 선분이 원기둥(cyls: (중심 N×2, r, z0, z1))·상자(boxes: (x, y, ψrad, L, W, z0, z1),
    x·y·ψ 는 N)에 안 막히면 보임 → 비율(N,). rackrec.World._visible 과 같은 식(물체 목록만 일반화)."""
    N, M = X.shape[:2]
    uv = cam.project(X.reshape(-1, 3))
    vis = (np.isfinite(uv).all(axis=1) & cam.inside(np.nan_to_num(uv, nan=-1e6), margin)).reshape(N, M)
    Cc = cam.center
    D = X - Cc[None, None, :]
    t_end = 1.0 - 1e-3
    for P, r, z0, z1 in cyls:
        cx, cy = P[:, None, 0], P[:, None, 1]
        ox, oy = Cc[0] - cx, Cc[1] - cy
        a = D[..., 0] ** 2 + D[..., 1] ** 2
        b = ox * D[..., 0] + oy * D[..., 1]
        c0 = ox * ox + oy * oy - r * r
        disc = b * b - a * c0
        sq = np.sqrt(np.maximum(disc, 0.0))
        t1, t2 = (-b - sq) / np.maximum(a, 1e-12), (-b + sq) / np.maximum(a, 1e-12)
        dz = D[..., 2]
        ta = (z0 - Cc[2]) / np.where(np.abs(dz) < 1e-9, 1e-9, dz)
        tb = (z1 - Cc[2]) / np.where(np.abs(dz) < 1e-9, 1e-9, dz)
        lo = np.maximum.reduce([t1, np.minimum(ta, tb), np.zeros_like(t1)])
        hi = np.minimum.reduce([t2, np.maximum(ta, tb), np.full_like(t1, t_end)])
        vis &= ~((disc > 0) & (lo < hi))
    for Px, Py, Ps, L, W, z0, z1 in boxes:
        cs, sn = np.cos(Ps)[:, None], np.sin(Ps)[:, None]
        o = np.stack([Cc[0] - Px[:, None], Cc[1] - Py[:, None]], axis=-1)
        lo_ = np.zeros((N, M))
        hi_ = np.full((N, M), t_end)
        for comp, half in ((0, L / 2), (1, W / 2)):
            if comp == 0:
                oo = o[..., 0] * cs + o[..., 1] * sn
                dd = D[..., 0] * cs + D[..., 1] * sn
            else:
                oo = -o[..., 0] * sn + o[..., 1] * cs
                dd = -D[..., 0] * sn + D[..., 1] * cs
            dd_ = np.where(np.abs(dd) < 1e-9, 1e-9, dd)
            ta, tb = (-half - oo) / dd_, (half - oo) / dd_
            lo_, hi_ = np.maximum(lo_, np.minimum(ta, tb)), np.minimum(hi_, np.maximum(ta, tb))
        dz = np.where(np.abs(D[..., 2]) < 1e-9, 1e-9, D[..., 2])
        ta, tb = (z0 - Cc[2]) / dz, (z1 - Cc[2]) / dz
        lo_, hi_ = np.maximum(lo_, np.minimum(ta, tb)), np.minimum(hi_, np.maximum(ta, tb))
        vis &= ~(lo_ < hi_)
    return vis.mean(axis=1)


def _minor(cam, Xr, policy_px):
    """표시물 바깥 테 점들의 상(타원)의 짧은 지름을 정책 입력(policy_px²)으로 줄인 값(px) — rackrec.World._minor. 2√(2 λ_min(Σ))."""
    N, M = Xr.shape[:2]
    uv = cam.project(Xr.reshape(-1, 3)).reshape(N, M, 2)
    s = np.array([float(policy_px) / cam.w, float(policy_px) / cam.h])
    u = uv * s[None, None, :]
    with np.errstate(invalid="ignore"), _quiet():
        m = u - np.nanmean(u, axis=1, keepdims=True)
    S =np.einsum("nki,nkj->nij", np.nan_to_num(m), np.nan_to_num(m)) / float(M)
    ev = np.linalg.eigvalsh(S)[:, 0]
    out = 2.0 * np.sqrt(np.maximum(2.0 * ev, 0.0))
    return np.where(np.isfinite(uv).all(axis=(1, 2)), out, 0.0)


# ---------------------------------------------------------------- 검사 하나씩: (C, c, ctx, info) → [(이름, 마스크)]
def _pts(C):
    return C["g"][:, :2], C["q"][:, :2]


def _chk_area(C, c, ctx, info):
    x0, x1 = map(float, c["x"])
    y0, y1 = map(float, c["y"])
    inA = lambda P: (P[..., 0] >= x0) & (P[..., 0] <= x1) & (P[..., 1] >= y0) & (P[..., 1] <= y1)   # noqa: E731
    what = c.get("what") or "points"
    m = np.ones(C["n"], bool)
    if what in ("points", "both"):
        g, q = _pts(C)
        m &= inA(g) & inA(q)
    if what in ("fixtures", "both") and C["kind"] == "fixtures":
        for i, I in enumerate(ctx.lay.instances):
            fp = footprint(C["P"][:, i, 0], C["P"][:, i, 1], C["yaw"][:, i], I.type.L, I.type.W)
            m &= np.all(inA(fp), axis=1)
    return [(c.get("_name", "area"), m)]


def _chk_min_move(C, c, ctx, info):
    g, q = _pts(C)
    return [(c.get("_name", "min_move"), np.hypot(*(q - g).T) >= float(c["min_mm"]))]


def _chk_yaw_window(C, c, ctx, info):
    lay = ctx.lay
    win = lay.window if c.get("_implicit") else None
    if win is None:
        from .layout import YawWindow
        win = YawWindow(c, lay.period_s)
    m = np.ones(C["n"], bool)
    if C["kind"] == "fixtures":
        for i, I in enumerate(lay.instances):
            if I.pose is not None or I.type.yaw_range is not None:
                continue
            used = (C["a"] == i) | (C["b"] == i)
            dpsi = np.abs(wrap(C["yaw"][:, i] - win.center(C["P"][:, i, 0], C["P"][:, i, 1]), I.type.period))
            m &= ~used | (dpsi <= win.half + 1e-6)              # rackrec: jw_eff + 1e-6
    else:
        for side, used in (("g", lay.start_yaw), ("q", lay.goal_yaw)):
            if used:
                X = C[side]
                m &= np.abs(wrap(X[:, 2] - win.center(X[:, 0], X[:, 1]), lay.period_s)) <= win.half + 1e-6
    return [(c.get("_name", "yaw_window"), m)]


def _chk_reach(C, c, ctx, info):
    lo, hi = float(c.get("min_mm", 0.0)), float(c.get("max_mm", np.inf))
    ox, oy = (c.get("origin") or [0.0, 0.0])[:2]
    if C["kind"] == "fixtures":
        H = C["H"]
        rr = np.hypot(H[..., 0] - ox, H[..., 1] - oy)
        with np.errstate(invalid="ignore"):
            okp = ((rr >= lo) & (rr <= hi)) | np.isnan(rr)
        m = np.all(okp, axis=(1, 2))                                 # rackrec: 받침 둘의 구멍 8개 모두
    else:
        g, q = _pts(C)
        rg, rq = np.hypot(g[:, 0] - ox, g[:, 1] - oy), np.hypot(q[:, 0] - ox, q[:, 1] - oy)
        m = (rg >= lo) & (rg <= hi) & (rq >= lo) & (rq <= hi)
    return [(c.get("_name", "reach"), m)]


def _chk_gap(C, c, ctx, info):
    if C["kind"] != "fixtures":
        ctx.skip("gap: points 배치에는 고정물이 없다")
        return []
    inst = ctx.lay.instances
    only = set(c.get("between") or [])
    ids = [i for i, I in enumerate(inst) if not only or I.type.name in only]
    m = np.ones(C["n"], bool)
    fps = {i: footprint(C["P"][:, i, 0], C["P"][:, i, 1], C["yaw"][:, i], inst[i].type.L, inst[i].type.W) for i in ids}
    for x in range(len(ids)):
        for y in range(x + 1, len(ids)):
            m &= sat_gap_many(fps[ids[x]], fps[ids[y]]) >= float(c["min_mm"])
    return [(c.get("_name", "gap"), m)]


def _chk_keepout(C, c, ctx, info):
    what = c.get("what") or ("fixtures" if C["kind"] == "fixtures" else "points")
    mg = float(c.get("margin_mm") or 0.0)
    m = np.ones(C["n"], bool)
    circ, poly = c.get("circle"), c.get("polygon")
    if what in ("points", "both"):
        for P in _pts(C):
            if circ:
                m &= np.hypot(P[:, 0] - float(circ["x"]), P[:, 1] - float(circ["y"])) >= float(circ["r"]) + mg
            if poly:
                m &= ~in_polygon(P, poly) & (seg_dist(P, poly) >= mg)
    if what in ("fixtures", "both") and C["kind"] == "fixtures":
        for i, I in enumerate(ctx.lay.instances):
            t = I.type
            if circ:
                d = rect_point_dist(C["P"][:, i, 0], C["P"][:, i, 1], C["yaw"][:, i], t.L, t.W, float(circ["x"]), float(circ["y"]))
                m &= d >= float(circ["r"]) + mg
            if poly:                                                 # 볼록 다각형 가정(SAT)
                fp = footprint(C["P"][:, i, 0], C["P"][:, i, 1], C["yaw"][:, i], t.L, t.W)
                m &= sat_gap_many(fp, np.asarray(poly, float)) >= mg
    return [(c.get("_name", "keepout"), m)]


def _chk_in_view(C, c, ctx, info):
    cam = ctx.cam(c.get("camera"))
    nm = c.get("_name", "in_view")
    if cam is None:
        ctx.skip(f"{nm}: no camera '{c.get('camera')}'")
        return []
    mg_px = float(c.get("margin_px", 16))
    grow = float(c.get("grow_mm", 0.0))
    roi = c.get("roi_px")
    m = np.ones(C["n"], bool)
    N = C["n"]
    if C["kind"] == "fixtures":
        for i, I in enumerate(ctx.lay.instances):
            t = I.type
            fp = footprint(C["P"][:, i, 0], C["P"][:, i, 1], C["yaw"][:, i], t.L, t.W, grow=grow)
            uv = cam.project(np.concatenate([fp, np.full((N, 4, 1), t.z_table)], axis=2))
            fin = np.isfinite(uv).all(axis=2)
            ins = in_polygon(uv, roi) if roi else cam.inside(np.nan_to_num(uv, nan=-1e6), mg_px)
            m &= np.all(fin & ins, axis=1)
            top = footprint(C["P"][:, i, 0], C["P"][:, i, 1], C["yaw"][:, i], t.L, t.W)
            uv2 = cam.project(np.concatenate([top, np.full((N, 4, 1), ctx.lay.top_z(t))], axis=2))
            m &= np.all(np.isfinite(uv2).all(axis=2) & cam.inside(uv2, mg_px), axis=1)
    else:
        g, q = _pts(C)
        for P, z in ((g, ctx.lay.start_z()), (q, ctx.lay.goal_z())):
            uv = cam.project(np.c_[P, np.full(N, z)])
            ins = in_polygon(uv, roi) if roi else cam.inside(uv, mg_px)
            m &= np.isfinite(uv).all(axis=1) & ins
    return [(nm, m)]


def _chk_view_angle(C, c, ctx, info):
    nm = c.get("_name", "view_angle")
    cam = ctx.cam(c.get("camera"))
    if cam is None:
        ctx.skip(f"{nm}: no camera '{c.get('camera')}'")
        return []
    if C["kind"] != "fixtures":
        ctx.skip(f"{nm}: points 배치에는 칸 줄이 없다")
        return []
    c3 = cam.center[:2]
    cmax = math.cos(math.radians(float(c.get("min_deg", 0.0))))
    m = np.ones(C["n"], bool)
    for i, I in enumerate(ctx.lay.instances):
        if I.type.n_slots < 2:
            continue
        vx, vy = C["P"][:, i, 0] - c3[0], C["P"][:, i, 1] - c3[1]
        nv = np.hypot(vx, vy) + 1e-9
        ang = np.radians(C["yaw"][:, i] + I.type.row_deg)
        m &= np.abs(np.cos(ang) * vx + np.sin(ang) * vy) / nv <= cmax   # rackrec.World.view_cut
    return [(nm, m)]


def goal_points(C, ctx, n_pts=16):
    """goal 표시물(링) 띠 점(가운데 반지름)·바깥 테 점 — rackrec._ring_pts."""
    lay = ctx.lay
    gt, gi = lay.goal_type, lay.goal
    r_mid = gt.hole_r + gi.gap + 0.5 * gi.w
    r_out = gt.hole_r + gi.gap + gi.w
    zr = gt.z_top + 0.5 * gi.h
    th = np.linspace(0, 2 * np.pi, n_pts, endpoint=False)
    q = C["q"][:, :2]
    N = len(q)
    X = np.stack([q[:, None, 0] + r_mid * np.cos(th)[None], q[:, None, 1] + r_mid * np.sin(th)[None], np.full((N, n_pts), zr)], axis=2)
    Xr = np.stack([q[:, None, 0] + r_out * np.cos(th)[None], q[:, None, 1] + r_out * np.sin(th)[None], np.full((N, n_pts), zr)], axis=2)
    return X, Xr


def occluders(C, ctx):
    """가리는 물체: start·장애물 원기둥(몸통·뚜껑) · goal 이 없는 다른 고정물 몸통(탁자 ~ 윗판)."""
    lay = ctx.lay
    st = lay.start_type
    zt = st.z_top
    idx = np.arange(C["n"])
    cyls = []
    for it, P in [(lay.start, C["g"][:, :2])] + [(o, C["H"][idx, C["a"], C["obs"][:, j]]) for j, o in enumerate(lay.obstacles)]:
        tube_r = it.tube_r or lay.start.tube_r
        cap_r = it.cap_r or lay.start.cap_r
        cap_h = it.cap_h or lay.start.cap_h
        above = it.above or lay.start.above
        if above <= 0:
            continue
        cyls.append((P, tube_r, zt, zt + above - cap_h))
        cyls.append((P, cap_r, zt + above - cap_h, zt + above))
    boxes = []
    for i, I in enumerate(lay.instances):
        m_other = C["b"] != i                                        # rackrec: 링이 없는 쪽 받침(other = 1 − b)
        if not m_other.any() or I.type.height <= 0:
            continue
        # goal 이 그 고정물인 후보는 상자를 화면 밖 아래로 보내 막지 않게
        Pz0 = np.where(m_other, I.type.z_table, -1e9)
        Pz1 = np.where(m_other, I.type.z_top, -1e9 + 1)
        boxes.append((C["P"][:, i, 0], C["P"][:, i, 1], np.radians(C["yaw"][:, i]), I.type.L, I.type.W, Pz0[:, None], Pz1[:, None]))
    return cyls, boxes


def _chk_goal_visible(C, c, ctx, info):
    nm = c.get("_name", "goal_visible")
    cam = ctx.cam(c.get("camera"))
    if cam is None:
        ctx.skip(f"{nm}: no camera '{c.get('camera')}'")
        return []
    if C["kind"] != "fixtures":
        ctx.skip(f"{nm}: points 배치에는 표시물·가림 모델이 없다")
        return []
    X, Xr = goal_points(C, ctx)
    cyls, boxes = occluders(C, ctx)
    v = _visible(cam, X, cyls, boxes, float(c.get("margin_px", 16)))
    b = _minor(cam, Xr, c.get("policy_px", 256))
    info[f"vis:{cam.name}"] = v
    info[f"minor:{cam.name}"] = b
    out = [(nm + ".frac", v >= float(c.get("min_frac", 0.7)))]
    if c.get("min_minor_px") is not None:
        out.append((nm + ".minor", np.nan_to_num(b) >= float(c["min_minor_px"])))
    return out


def _chk_hook(C, c, ctx, info):
    nm = c.get("_name", "hook")
    if c.get("stage", "batch") == "final":
        ctx.final_hooks.append(c)
        return []
    try:
        fn = ctx.load_fn(c["fn"])
    except Exception as e:                                            # 못 읽으면 건너뛴다(이유를 남긴다)
        ctx.skip(f"{nm}: {c.get('fn')} 를 못 읽음({type(e).__name__}: {e})")
        return []
    res = fn(C, ctx, **(c.get("args") or {}))
    if isinstance(res, tuple):
        res, extra = res
        if isinstance(extra, dict):
            info.update({f"{nm}:{k}": v for k, v in extra.items()})
    return [(nm, np.asarray(res, bool).reshape(C["n"]))]


CHECKS = {"area": _chk_area, "min_move": _chk_min_move, "yaw_window": _chk_yaw_window, "reach": _chk_reach, "gap": _chk_gap,
          "keepout": _chk_keepout, "in_view": _chk_in_view, "view_angle": _chk_view_angle, "goal_visible": _chk_goal_visible,
          "hook": _chk_hook}


def plan(ctx: Context) -> list[dict]:
    """검사 목록(순서대로): 자동 검사 + spec.constraints. 이름이 겹치면 뒤에 #2."""
    lay, sp = ctx.lay, ctx.spec
    x0, x1, y0, y1 = lay.area
    out = [{"type": "area", "x": [x0, x1], "y": [y0, y1], "what": "points", "_name": "area"}]
    if lay.kind == "points" and lay.min_move > 0:
        out.append({"type": "min_move", "min_mm": lay.min_move, "_name": "min_move"})
    if lay.window is not None:
        out.append({"type": "yaw_window", "_implicit": True, "_name": "yaw_window"})
    seen = {c["_name"] for c in out}
    for c in sp.get("constraints") or []:
        c = dict(c)
        t = c.get("type")
        if t not in CHECKS:
            ctx.skip(f"{t}: 모르는 제약 종류")
            continue
        nm = str(c.get("name") or t)
        k = 2
        base = nm
        while nm in seen:
            nm = f"{base}#{k}"
            k += 1
        seen.add(nm)
        c["_name"] = nm
        out.append(c)
    return out


def checks(C: dict, ctx: Context):
    """후보 묶음 → (통과 여부 (N,), 검사별로 처음 빠진 수 {이름: 수}, 보임 값 {vis:카메라, minor:카메라})."""
    ok = np.ones(C["n"], bool)
    drop, info = {}, {}
    ctx.final_hooks = []
    for c in plan(ctx):
        for name, m in CHECKS[c["type"]](C, c, ctx, info):
            m = np.asarray(m, bool)
            drop[name] = int((ok & ~m).sum())
            ok = ok & m
    return ok, drop, info


def final_check(opt: dict, ctx: Context):
    """final 훅(비싼 검사 — 고른 뒤 몇 개에만): 모두 통과하면 (True, []), 아니면 (False, 이유)."""
    why = []
    for c in ctx.final_hooks:
        nm = c.get("_name", "hook")
        try:
            fn = ctx.load_fn(c["fn"])
        except Exception as e:
            ctx.skip(f"{nm}: {c.get('fn')} 를 못 읽음({type(e).__name__}: {e})")
            continue
        r = fn(opt, ctx, **(c.get("args") or {}))
        okr, w = (r if isinstance(r, tuple) else (r, None))
        if not okr:
            why.append(f"{nm}: {w}" if w else nm)
    return (not why), why
