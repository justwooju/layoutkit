"""점수 재료 — 거리·가우스 과정 사후 분산·가중 상관·육각 칸·이산 칸·수고. 식은 rackrec(docs/RECOMMENDER.md 3.3~3.5)과 같다.

점수(rackrec 3.5):
  score = σ²_g + σ²_q + α σ²_r + β Σ_f 1/(1 + ñ_f) − η Δρ − γ E + Σ_cam w_cam·½(1/(1+m_start) + 1/(1+m_goal)) + w_vis·1[보임] − w_bad·P_bad
  σ² = 1 − k_cᵀ(K + Λ)⁻¹k_c (RBF k = exp(−½d²), Λ = diag(λ/w), λ = 0.05) · ñ = 무게 합 / (목표 비율 × 칸 수)
  Δρ = clip((m₁ − m₀)(Σw + 1), −1, 1), m = max(|ρ 합침|, |ρ 새 데이터셋만|)(새 데이터셋 판이 rho_v2_n 이상일 때)
"""
from __future__ import annotations

import itertools
import math

import numpy as np

from .layout import wrap


# ---------------------------------------------------------------- 거리·가우스 과정
def d2_xyp(A, B, h_xy, h_psi, period=180.0):
    """(x, y, ψ) 두 묶음 사이 거리² 행렬(눈금 맞춘). ψ 는 주기로 감는다(받침 180°). h_psi = inf 면 방향을 안 본다."""
    A, B = np.asarray(A, float).reshape(-1, 3), np.asarray(B, float).reshape(-1, 3)
    dx = (A[:, None, 0] - B[None, :, 0]) / h_xy
    dy = (A[:, None, 1] - B[None, :, 1]) / h_xy
    dp = wrap(A[:, None, 2] - B[None, :, 2], period) / h_psi
    return dx * dx + dy * dy + dp * dp


def d2_xy(A, B, h_xy):
    A, B = np.asarray(A, float).reshape(-1, 2), np.asarray(B, float).reshape(-1, 2)
    d = (A[:, None, :] - B[None, :, :]) / h_xy
    return (d * d).sum(axis=2)


def gp_var(D2_ss, D2_cs, w, lam=0.05):
    """가우스 과정 사후 분산 σ²(c) = 1 − k_cᵀ (K + Λ)⁻¹ k_c, k = exp(−½ d²), Λ = diag(λ / w). 판이 없으면 1. rackrec.gp_var."""
    n = D2_ss.shape[0]
    if n == 0:
        return np.ones(D2_cs.shape[0])
    w = np.maximum(np.asarray(w, float), 1e-6)
    Kss = np.exp(-0.5 * D2_ss) + np.diag(lam / w)
    Kcs = np.exp(-0.5 * D2_cs)
    try:
        L = np.linalg.cholesky(Kss)
        V = np.linalg.solve(L, Kcs.T)
        return np.clip(1.0 - (V * V).sum(axis=0), 0.0, 1.0)
    except np.linalg.LinAlgError:
        X = np.linalg.solve(Kss + 1e-9 * np.eye(n), Kcs.T)
        return np.clip(1.0 - (Kcs.T * X).sum(axis=0), 0.0, 1.0)


# ---------------------------------------------------------------- 상관
def wcorr(x, y, w=None):
    """무게 상관(Pearson). 판이 3개 아래거나 분산 0 이면 None."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    w = np.ones(len(x)) if w is None else np.asarray(w, float)
    if len(x) < 3 or w.sum() <= 0:
        return None
    mx, my = (w * x).sum() / w.sum(), (w * y).sum() / w.sum()
    cxy = (w * (x - mx) * (y - my)).sum()
    vx, vy = (w * (x - mx) ** 2).sum(), (w * (y - my) ** 2).sum()
    if vx <= 1e-12 or vy <= 1e-12:
        return None
    return float(cxy / math.sqrt(vx * vy))


def wcorr_add(x, y, w, xc, yc, wc=1.0):
    """판 하나(xc, yc, 무게 wc — 배열 가능)를 더했을 때 무게 상관(후보마다, 닫힌 꼴)."""
    x, y, w = np.asarray(x, float), np.asarray(y, float), np.asarray(w, float)
    xc, yc = np.asarray(xc, float), np.asarray(yc, float)
    S = w.sum() + wc
    sx, sy = (w * x).sum() + wc * xc, (w * y).sum() + wc * yc
    sxx, syy, sxy = (w * x * x).sum() + wc * xc * xc, (w * y * y).sum() + wc * yc * yc, (w * x * y).sum() + wc * xc * yc
    cxy = sxy - sx * sy / S
    vx, vy = sxx - sx * sx / S, syy - sy * sy / S
    return np.where((vx > 1e-12) & (vy > 1e-12), cxy / np.sqrt(np.maximum(vx * vy, 1e-24)), 0.0)


def coupling_term(D, gf, qf, pairs, rho_v2_n=10):
    """상관 항(rackrec 3.5): 판 하나를 더했을 때 max(|ρ 합침|, |ρ 새 데이터셋만|) 의 변화 × (무게 합 + 1), ±1 로 자름.
    pairs = [(start 축, goal 축)] (0 = x, 1 = y) — 여럿이면 그중 큰 |ρ| 로(rackrec 은 x 하나: spec.pairs 첫 짝이 기본).
    반환 {"d_rho": (N,), "rho1": |ρ 합침| 최대(후보를 더한 뒤, N), "rho0": |ρ 합침| 최대(지금) | None,
          "c_ok": 합침 |ρ| 를 안 키우는 후보(rackrec c_rho), "m0": 최소최대 기준값}."""
    N = len(gf)
    w = D["w"]
    rho0s, m0, m1, c_ok = [], 0.0, np.zeros(N), np.ones(N, bool)
    p1 = np.zeros(N)
    any_rho = False
    for sa, ga in pairs:
        r0 = wcorr(D["g"][:, sa], D["q"][:, ga], w)
        if r0 is None:
            continue
        any_rho = True
        r1 = wcorr_add(D["g"][:, sa], D["q"][:, ga], w, gf[:, sa], qf[:, ga], 1.0)
        a0, a1 = abs(r0), np.abs(r1)
        c_ok &= a1 <= a0 + 1e-12
        p1 = np.maximum(p1, a1)
        v2 = D["tgt"]
        if v2.sum() >= int(rho_v2_n):
            r20 = wcorr(D["g"][v2, sa], D["q"][v2, ga])
            if r20 is not None:
                r21 = wcorr_add(D["g"][v2, sa], D["q"][v2, ga], np.ones(int(v2.sum())), gf[:, sa], qf[:, ga], 1.0)
                a0, a1 = max(a0, abs(r20)), np.maximum(a1, np.abs(r21))
        m0 = max(m0, a0)
        m1 = np.maximum(m1, a1)
        rho0s.append(r0)
    if not any_rho:
        return {"d_rho": np.zeros(N), "rho1": np.zeros(N), "rho0": None, "c_ok": c_ok, "m0": None}
    d_rho = np.clip((m1 - m0) * (float(w.sum()) + 1.0), -1.0, 1.0)
    return {"d_rho": d_rho, "rho1": p1, "rho0": max(abs(r) for r in rho0s), "c_ok": c_ok, "m0": m0}


# ---------------------------------------------------------------- 육각 칸
def hex_cell_area(h) -> float:
    return 1.5 * math.sqrt(3.0) * float(h) ** 2


def n_hex(area_mm2, h) -> int:
    return int(math.ceil(float(area_mm2) / hex_cell_area(h) - 1e-9))


def hex_centers(area, h):
    """영역(x0, x1, y0, y1) 가운데에 맞춘 육각 배열의 칸 가운데(영역 안) — rackrec.hex_centers 와 같다."""
    x0, x1, y0, y1 = (float(v) for v in area)
    a, b = math.sqrt(3.0) * h, 1.5 * h
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    long_x = (x1 - x0) >= (y1 - y0)
    nu = int(max(x1 - x0, y1 - y0) / a) + 3
    nv = int(max(x1 - x0, y1 - y0) / b) + 3
    out = []
    for j in range(-nv, nv + 1):
        for i in range(-nu, nu + 1):
            u, v = i * a + (a / 2 if j % 2 else 0.0), j * b
            x, y = (cx + u, cy + v) if long_x else (cx + v, cy + u)
            if x0 - 1e-9 <= x <= x1 + 1e-9 and y0 - 1e-9 <= y <= y1 + 1e-9:
                out.append((x, y))
    return np.array(out, float).reshape(-1, 2)


def cell_of(P, C, area):
    """점마다 가장 가까운 칸 번호(영역 밖이면 −1)."""
    P = np.asarray(P, float).reshape(-1, 2)
    if len(P) == 0 or len(C) == 0:
        return np.full(len(P), -1, int)
    x0, x1, y0, y1 = area
    k = np.argmin(((P[:, None, :] - C[None, :, :]) ** 2).sum(axis=2), axis=1)
    ins = (P[:, 0] >= x0) & (P[:, 0] <= x1) & (P[:, 1] >= y0) & (P[:, 1] <= y1)
    return np.where(ins, k, -1)


def coupon(n) -> float:
    n = int(n)
    return float(n * sum(1.0 / k for k in range(1, n + 1))) if n > 0 else 0.0


class Cells:
    """(자리, 방향) 칸: 육각 자리 칸 × 방향 칸(rackrec.Recommender.cells). centers 를 주면(분석 결과) 그 칸을 쓴다."""

    def __init__(self, lay, centers=None):
        self.lay = lay
        self.h = lay.h_xy
        self.area = lay.area
        self.centers = np.asarray(centers, float).reshape(-1, 2) if centers is not None else hex_centers(lay.area, lay.h_xy)
        self.n_xy = len(self.centers)
        self.n_psi_s, self.n_psi_g = lay.n_psi("start"), lay.n_psi("goal")

    def ids(self, X, side):
        """X (N×3) → (자리 칸, (자리, 방향) 칸 번호) — 영역 밖 −1."""
        c = cell_of(X[:, :2], self.centers, self.area)
        npsi = self.n_psi_s if side == "start" else self.n_psi_g
        return c, np.where(c >= 0, c * npsi + self.lay.psi_bin(X[:, 2], side), -1)

    def n_ids(self, side):
        return self.n_xy * (self.n_psi_s if side == "start" else self.n_psi_g)


# ---------------------------------------------------------------- 이산 칸(고르게)
def families(spec, lay, D_disc_names=()):
    """이산 칸 묶음 [(이름, 값들, 목표 비율)]: spec.strata + (자동) 이동 종류(가까이 ≥ near_share) · start–장애물 이웃(50/50).
    rackrec.families(빨강 칸 · 링 칸 · 옮김 · 빨강-노랑)의 일반화 — 앞 둘은 spec.strata(start_slot · goal_slot)로 온다."""
    out = []
    for s in spec.get("strata") or []:
        vals = list(s["values"])
        sh = s.get("shares") or [1.0 / len(vals)] * len(vals)
        out.append((str(s["name"]), vals, [float(x) for x in sh]))
    names = {f[0] for f in out}
    if (spec.get("recommend") or {}).get("auto_strata", True):
        ns = float((spec.get("targets") or {}).get("near_share", 0.25))
        if "near" not in names:
            out.append(("near", [True, False], [ns, 1.0 - ns]))
        if lay.kind == "fixtures" and lay.obstacles and "adjacent" not in names:
            out.append(("adjacent", [True, False], [0.5, 0.5]))
    return out


def value_index(vals, x):
    """값 → 칸 번호(없으면 −1). 1 과 True 처럼 다른 형의 같은 값은 형까지 맞춘다(bool 칸에 숫자 0/1 이 섞이지 않게)."""
    for k, v in enumerate(vals):
        if x is None:
            return -1
        if isinstance(v, bool) != isinstance(x, bool):
            continue
        if v == x or str(v) == str(x):
            return k
    return -1


def strata_term(fams, D_vals, w, C_vals):
    """후보마다 β 항 Σ_f 1/(1 + ñ_f) 와 채움 표(rackrec 과 같은 식). D_vals/C_vals = {이름: 칸 번호 배열(−1 = 그 묶음에 안 듦)}.
    반환 (st (N,), fill [(채움 비율, 이름, k, 값, 무게 수, 목표)], per {이름: (cnt, pi)})."""
    N = len(next(iter(C_vals.values()))) if C_vals else 0
    st = np.zeros(N)
    fill, per = [], {}
    for name, vals, pi in fams:
        K_ = len(vals)
        sd = D_vals[name]
        sc = C_vals[name]
        wm = sd >= 0
        cnt = np.array([float(w[(sd == k) & wm].sum()) for k in range(K_)])
        eff = cnt / (np.asarray(pi) * K_)
        st += np.where(sc >= 0, 1.0 / (1.0 + eff[np.maximum(sc, 0)]), 0.0)   # 그 묶음에 안 드는 후보는 0(일반화)
        tot = float(w[wm].sum())
        for k in range(K_):
            fill.append((cnt[k] / max(1e-9, pi[k] * max(tot, 1.0)), name, k, vals[k], cnt[k], pi[k] * (tot + 1)))
        per[name] = (cnt, np.asarray(pi), tot)
    return st, fill, per


# ---------------------------------------------------------------- 수고
def _scene(cur, lay):
    """지금 탁자 장면 → {"fixtures": [(x, y, yaw)], "start": (i, k)|None, "obstacles": [(i, k)], "goal": (i, k)|None}.
    rackrec 모양(racks · red · yellow · slot)도 받는다."""
    if not cur:
        return None
    fx = cur.get("fixtures") if cur.get("fixtures") is not None else cur.get("racks")
    if not fx:
        return None
    F = [(float(f["x"]), float(f["y"]), float(f.get("yaw", f.get("psi", 0.0)))) for f in fx]
    st = cur.get("start", cur.get("red"))
    ob = cur.get("obstacles")
    if ob is None:
        ob = [cur["yellow"]] if cur.get("yellow") is not None else ([None] * len(lay.obstacles))
    gl = cur.get("goal", cur.get("slot"))
    return {"fixtures": F, "start": st, "obstacles": list(ob), "goal": gl}


def effort(C, cur, lay):
    """지금 탁자 장면에서 후보까지 수고(rackrec.effort): min_짝 Σ(‖Δp‖/100 mm + |Δψ|/45°) + 0.5·(옮길 물건) + 0.2·[goal 표시물 옮김].
    짝 = 움직이는 같은 형식 고정물끼리의 순열 중 작은 쪽. 장면을 모르면 0. 반환 (수고 (N,), 판마다 설명)."""
    N = C["n"]
    sc = _scene(cur, lay)
    if lay.kind != "fixtures" or sc is None:
        return np.zeros(N), ["effort: scene unknown → 0"] * N
    mov = [i for i, I in enumerate(lay.instances) if I.pose is None]
    if len(sc["fixtures"]) < len(mov):
        return np.zeros(N), ["effort: scene has fewer fixtures → 0"] * N
    cx = np.array(sc["fixtures"][:len(mov)], float)
    types = [lay.instances[i].type for i in mov]
    perms = [p for p in itertools.permutations(range(len(mov))) if all(types[a] is types[b] for a, b in zip(range(len(mov)), p))]
    best, best_pi = np.full(N, np.inf), np.zeros(N, int)
    parts = {}
    for pi, perm in enumerate(perms):
        e = np.zeros(N)
        tgt = np.array([mov[t] for t in perm])                         # 장면 ci 번 고정물 → 후보 인스턴스 tgt[ci]
        for ci, ti in enumerate(tgt):
            per = lay.instances[ti].type.period
            dp = np.hypot(C["P"][:, ti, 0] - cx[ci, 0], C["P"][:, ti, 1] - cx[ci, 1])
            da = np.abs(wrap(C["yaw"][:, ti] - cx[ci, 2], per))
            e += dp / 100.0 + da / 45.0
            parts[(pi, ci)] = (dp, da, ti)
        moved = np.zeros(N)
        wants = [(sc["start"], C["a"], C["ks"])] + [(v, C["a"], C["obs"][:, j]) for j, v in
                                                    enumerate((sc["obstacles"] + [None] * len(lay.obstacles))[:len(lay.obstacles)])]
        for v, ta, tk in wants:
            if v is None or int(v[0]) >= len(tgt):                     # 모름 · 셋째 고정물 → 옮길 것으로 센다(rackrec)
                moved += 1
                continue
            moved += ~((tgt[int(v[0])] == ta) & (int(v[1]) == tk))
        g = sc["goal"]
        g_mv = (np.ones(N) if g is None or int(g[0]) >= len(tgt) else
                (~((tgt[int(g[0])] == C["b"]) & (int(g[1]) == C["kg"]))).astype(float))
        e += 0.5 * moved + 0.2 * g_mv
        parts[(pi, "t")] = (moved, g_mv)
        m = e < best
        best[m], best_pi[m] = e[m], pi
    names = lay.instance_names()
    txt = []
    for i in range(N):
        pi = best_pi[i]
        s = []
        for ci in range(len(mov)):
            dp, da, ti = parts[(pi, ci)]
            s.append(f"{names[ti]} {dp[i]:.0f} mm·{da[i]:.0f}°")
        mv, gm = parts[(pi, "t")]
        txt.append(f"effort {best[i]:.2f}: " + " · ".join(s) + f" · items moved {int(mv[i])}" + (" · goal marker moved" if gm[i] else ""))
    return best, txt


def bad_view_penalty(C, bad, h_xy, h_psi, period=180.0):
    """인식이 고정물을 못 찾았던 배치 근처 — 후보 고정물마다 exp(−d²/2) 최댓값의 합, 2 로 자름(빼지 않고 점수만 낮춤). rackrec v1.1.3."""
    N = C["n"]
    if not bad or C["kind"] != "fixtures":
        return np.zeros(N)
    pen = np.zeros(N)
    for b in bad:
        for R_ in b.get("fixtures") or b.get("racks") or []:
            dx = (C["P"][:, :, 0] - float(R_["x"])) / h_xy
            dy = (C["P"][:, :, 1] - float(R_["y"])) / h_xy
            dp = wrap(C["yaw"] - float(R_.get("yaw", R_.get("psi", 0.0))), period) / h_psi
            pen += np.exp(-0.5 * (dx ** 2 + dy ** 2 + dp ** 2)).max(axis=1)
    return np.minimum(pen, 2.0)


def near_dups(D, h, hp, thr=0.3, periods=(180.0, 180.0)) -> int:
    """거의 같은 판 짝 수(start·goal 모두 thr·h 안 + 같은 칸 번호)."""
    n = len(D["g"])
    if n < 2:
        return 0
    dg = np.sqrt(d2_xyp(D["g"], D["g"], h, hp, periods[0]))
    dq = np.sqrt(d2_xyp(D["q"], D["q"], h, hp, periods[1]))
    same = (D["ks"][:, None] == D["ks"][None, :]) & (D["kg"][:, None] == D["kg"][None, :])
    m = (dg < thr) & (dq < thr) & same
    return int(np.triu(m, 1).sum())
