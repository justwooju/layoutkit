"""궤적 → 사건. 그리퍼가 닫힌 구간의 시작 = 집음, 다시 열린 순간 = 놓음 → 집은 자리(start)·놓은 자리(goal).

입력: 시각 t[s](없으면 프레임 번호 / hz) · EEF 위치 xyz(N×3, mm 또는 m — 자동 짐작) · 그리퍼 값 g(N) · yaw(N, 선택).

그리퍼 값의 뜻(폭인지 닫힘 명령인지)과 범위는 기록마다 다르므로:
- 문턱: 옵션(threshold) · 값 범위(grip_range = (lo, hi) → 가운데) · 자동(값을 두 무리로 나눈 두 가운데의 중간 — 1차원 2-평균).
  두 무리가 잡음보다 충분히 떨어져 있지 않으면(사이 / 무리 안 표준편차 < sep_ratio) 그리퍼가 한 번도 안 움직였다고 본다.
- 닫힘 방향: 옵션(closed_is = "low" | "high") · 자동(에피소드 첫머리는 열려 있다고 보고 그 반대 쪽).
- 잡음: 문턱 둘레 히스테리시스(사이의 hyst 배) + 짧은 깜빡임 지우기(닫힘·열림 구간이 min_*_s 또는 min_frames 보다 짧으면 무시).

자리: 집은 자리 = 닫힌 직후(닫힌 첫 프레임 앞 settle_s/2 ~ 뒤 settle_s) 팔이 거의 멈춘 프레임들의 EEF 중앙값,
놓은 자리 = 열리기 직전(열린 첫 프레임 앞 settle_s ~ 뒤 settle_s/2) 같은 방식. 멈춘 프레임이 없으면 그 창에서 가장 느린 프레임.
닫힌 구간이 여럿이면(다시 잡기) 기본은 가장 긴 구간(옮긴 구간)을 쓴다 — which 옵션.
"""
from __future__ import annotations

import math

import numpy as np

DEFAULTS = {
    "threshold": None,        # 그리퍼 문턱(값 단위) — None 이면 grip_range 가운데 또는 자동
    "grip_range": None,       # (lo, hi) 값 범위를 알면
    "closed_is": "auto",      # "low"(폭: 작을수록 닫힘) | "high"(닫힘 명령: 클수록 닫힘) | "auto"
    "units": "auto",          # 위치 단위 "mm" | "m" | "auto"(절댓값 최대가 5 아래면 m)
    "yaw_units": "deg",       # "deg" | "rad" | "auto"(절댓값 최대가 π 근처 아래면 rad)
    "hz": None,               # t 가 없을 때 프레임 주기
    "min_closed_s": 0.3,      # 이보다 짧은 닫힘은 깜빡임
    "min_open_s": 0.3,        # 닫힘 사이 이보다 짧은 열림은 깜빡임
    "min_frames": 2,          # 구간이 이 프레임 수보다 짧으면 깜빡임
    "hyst": 0.1,              # 히스테리시스 반폭 = 두 무리 사이 × hyst
    "sep_ratio": 5.0,         # 두 무리 사이 / 무리 안 표준편차 가 이보다 작으면 '안 움직임'
    "settle_s": 0.6,          # 자리를 재는 창 길이
    "still_mm_s": 15.0,       # 이보다 느리면 '멈춤'(xy 속력)
    "which": "longest",       # 닫힌 구간이 여럿일 때: longest | first | last | span(첫 구간의 집음 + 마지막 구간의 놓음)
}


def to_mm(xyz, units="auto"):
    """위치 → mm. 반환 (배열, 원래 단위)."""
    P = np.asarray(xyz, float).reshape(-1, 3)
    if units == "mm":
        return P, "mm"
    if units == "m":
        return P * 1000.0, "m"
    fin = P[np.isfinite(P).all(axis=1)]
    if len(fin) and float(np.abs(fin).max()) < 5.0:          # 로봇 작업 공간이 5 m 를 넘을 리 없다 → m
        return P * 1000.0, "m"
    return P, "mm"


def yaw_deg(yaw, units="deg"):
    if yaw is None:
        return None
    Y = np.asarray(yaw, float).reshape(-1)
    if units == "rad" or (units == "auto" and np.isfinite(Y).any() and float(np.nanmax(np.abs(Y))) <= math.pi + 0.05):
        return np.degrees(Y)
    return Y


def two_means(v):
    """1차원 2-평균(작은 쪽·큰 쪽 가운데에서 시작). 반환 (lo 가운데, hi 가운데, 무리 안 표준편차)."""
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    if len(v) < 2:
        return None
    lo, hi = float(v.min()), float(v.max())
    if hi - lo <= 1e-12:
        return lo, hi, 0.0
    for _ in range(50):
        thr = 0.5 * (lo + hi)
        a, b = v[v <= thr], v[v > thr]
        if len(a) == 0 or len(b) == 0:
            break
        nlo, nhi = float(a.mean()), float(b.mean())
        if abs(nlo - lo) < 1e-12 and abs(nhi - hi) < 1e-12:
            break
        lo, hi = nlo, nhi
    thr = 0.5 * (lo + hi)
    a, b = v[v <= thr], v[v > thr]
    ss = float(((a - lo) ** 2).sum() + ((b - hi) ** 2).sum())
    return lo, hi, math.sqrt(ss / max(1, len(v) - 2))


def _runs(mask):
    """참·거짓 줄 → [(값, 시작, 끝(제외))]."""
    out = []
    n = len(mask)
    i = 0
    while i < n:
        j = i
        while j < n and mask[j] == mask[i]:
            j += 1
        out.append((bool(mask[i]), i, j))
        i = j
    return out


def _dur(t, i, j):
    """구간 [i, j) 길이(s) — 끝 프레임 다음 칸까지(마지막이면 평균 간격 하나 더)."""
    if j < len(t):
        return float(t[j] - t[i])
    dt = float(np.median(np.diff(t))) if len(t) > 1 else 0.0
    return float(t[-1] - t[i] + dt)


def closed_mask(t, g, opt) -> tuple[np.ndarray, dict]:
    """그리퍼 값 → 프레임마다 닫힘 여부(잡음 지운 뒤) + 쓴 문턱·방향."""
    g = np.asarray(g, float)
    info = {"threshold": None, "closed_is": None, "moved": False}
    fin = np.isfinite(g)
    if fin.sum() < 2:
        return np.zeros(len(g), bool), info
    gf = np.where(fin, g, np.interp(np.arange(len(g)), np.flatnonzero(fin), g[fin]))
    tm = two_means(gf)
    lo, hi, sd = tm
    sep = hi - lo
    thr = opt.get("threshold")
    rng = opt.get("grip_range")
    if thr is None and rng is not None:
        thr = 0.5 * (float(rng[0]) + float(rng[1]))
        sep = max(sep, abs(float(rng[1]) - float(rng[0])) * 0.5)
    moved = sep > 1e-9 and (sd <= 1e-12 or sep / sd >= float(opt["sep_ratio"]))
    if thr is None:
        if not moved:
            return np.zeros(len(g), bool), info
        thr = 0.5 * (lo + hi)
    thr = float(thr)
    closed_is = opt.get("closed_is") or "auto"
    if closed_is == "auto":
        n0 = max(3, len(gf) // 10)
        head = float(np.median(gf[:n0]))
        closed_is = "low" if head > thr else "high"                 # 첫머리는 열려 있다
    sign = -1.0 if closed_is == "low" else 1.0
    s = sign * (gf - thr)                                            # > 0 이면 닫힘 쪽
    band = float(opt["hyst"]) * max(sep, 1e-12)
    m = np.zeros(len(gf), bool)
    state = bool(s[0] > 0)
    for i, v in enumerate(s):
        if v > band:
            state = True
        elif v < -band:
            state = False
        m[i] = state
    # 짧은 닫힘(깜빡임) 지우기 → 닫힘 사이 짧은 열림 메우기
    t = np.asarray(t, float)
    for val, min_s in ((True, float(opt["min_closed_s"])), (False, float(opt["min_open_s"]))):
        for v, i, j in _runs(m):
            if v != val:
                continue
            if val is False and (i == 0 or j == len(m)):             # 처음·끝의 열림은 메우지 않는다
                continue
            if _dur(t, i, j) < min_s or (j - i) < int(opt["min_frames"]):
                m[i:j] = not val
    info.update(threshold=thr, closed_is=closed_is, moved=bool(m.any()))
    return m, info


def _speed(t, P):
    """xy 속력(mm/s) — 가운데 차분."""
    if len(P) < 2:
        return np.zeros(len(P))
    t = np.asarray(t, float)
    dt = np.gradient(t)
    dt = np.where(np.abs(dt) < 1e-9, 1e-9, dt)
    vx, vy = np.gradient(P[:, 0]) / dt, np.gradient(P[:, 1]) / dt
    return np.hypot(vx, vy)


def _circ_median(a):
    """각(°) 중앙값 — 풀어서(unwrap) 중앙값 → (−180, 180]."""
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    if len(a) == 0:
        return None
    u = np.degrees(np.unwrap(np.radians(a)))
    m = float(np.median(u))
    m = (m + 180.0) % 360.0 - 180.0
    return 180.0 if m == -180.0 else m


def _spot(t, P, yaw, spd, t0, t1, still):
    """시각 창 [t0, t1] 안 멈춘 프레임들의 자리(중앙값)."""
    idx = np.flatnonzero((t >= t0 - 1e-9) & (t <= t1 + 1e-9))
    if len(idx) == 0:
        idx = np.array([int(np.argmin(np.abs(t - 0.5 * (t0 + t1))))])
    ok = idx[spd[idx] <= still]
    if len(ok) == 0:
        ok = idx[[int(np.argmin(spd[idx]))]]
    out = {"x": float(np.median(P[ok, 0])), "y": float(np.median(P[ok, 1])), "z": float(np.median(P[ok, 2]))}
    if yaw is not None:
        y = _circ_median(yaw[ok])
        if y is not None:
            out["yaw"] = y
    return out


def detect(t=None, xyz=None, grip=None, yaw=None, **opt) -> dict:
    """궤적 하나 → 사건·자리. 반환:
    {"ok", "start", "goal", "t_pick", "t_place", "segments": [{"i0", "i1", "t0", "t1"}], "threshold", "closed_is", "units",
     "flags": [...], "duration_s", "path_mm", "n_frames"}.
    flags: no_grip(그리퍼가 안 움직임) · held_at_start(처음부터 닫힘) · no_release(끝까지 안 열림) · regrasp(닫힌 구간 여럿)."""
    o = dict(DEFAULTS)
    o.update({k: v for k, v in opt.items() if v is not None or k in ("threshold", "grip_range")})
    P, units = to_mm(xyz, o["units"])
    n = len(P)
    if t is None:
        hz = float(o["hz"] or 10.0)
        t = np.arange(n) / hz
    t = np.asarray(t, float).reshape(-1)
    if len(t) != n or grip is None or len(grip) != n:
        raise ValueError(f"t·xyz·grip 길이가 다르다: {len(t)} · {n} · {None if grip is None else len(grip)}")
    Y = yaw_deg(yaw, o["yaw_units"]) if yaw is not None else None
    fin = np.isfinite(P).all(axis=1)
    if not fin.all() and fin.sum() >= 2:                              # 빠진 위치는 앞뒤로 메운다
        for k in range(3):
            P[:, k] = np.interp(np.arange(n), np.flatnonzero(fin), P[fin, k])
    seg_len = np.linalg.norm(np.diff(P, axis=0), axis=1) if n > 1 else np.zeros(0)
    out = {"ok": False, "start": None, "goal": None, "t_pick": None, "t_place": None, "segments": [], "threshold": None,
           "closed_is": None, "units": units, "flags": [], "n_frames": n,
           "duration_s": float(t[-1] - t[0]) if n > 1 else 0.0, "path_mm": float(np.nansum(seg_len))}
    if n < 2:
        out["flags"].append("too_short")
        return out
    m, info = closed_mask(t, grip, o)
    out["threshold"], out["closed_is"] = info["threshold"], info["closed_is"]
    segs = [(i, j) for v, i, j in _runs(m) if v]
    if not segs:
        out["flags"].append("no_grip")
        return out
    out["segments"] = [{"i0": int(i), "i1": int(j), "t0": float(t[i]), "t1": float(t[j]) if j < n else None} for i, j in segs]
    if len(segs) > 1:
        out["flags"].append("regrasp")
    w = o["which"]
    if w == "first":
        a = b = segs[0]
    elif w == "last":
        a = b = segs[-1]
    elif w == "span":
        a, b = segs[0], segs[-1]
    else:
        a = b = max(segs, key=lambda s: _dur(t, s[0], s[1]))
    spd = _speed(t, P)
    still, st = float(o["still_mm_s"]), float(o["settle_s"])
    i0 = a[0]
    if i0 == 0:
        out["flags"].append("held_at_start")
    tc = float(t[i0])
    out["start"] = _spot(t, P, Y, spd, tc - 0.5 * st, tc + st, still)
    out["t_pick"] = tc
    j = b[1]
    if j >= n:
        out["flags"].append("no_release")
        to = float(t[-1])
    else:
        to = float(t[j])
    out["goal"] = _spot(t, P, Y, spd, to - st, to + 0.5 * st, still)
    out["t_place"] = to
    out["ok"] = True
    return out
