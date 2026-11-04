"""화면 개발용 가짜 분석 결과(result_rack.json) 만들기 — 받침 예제(v1 꼬리표 100판 + v2 19판 + 수집 기록 csv).

정확한 수학은 layoutkit.analyze 몫이다. 여기서는 DESIGN 3절 모양과 그럴듯한 값만 맞춘다(표준 라이브러리만).
단 v1 숫자(쪽 표 44/44·52/56, ρ −0.81, 자리 32/43/99, 칸 20/27)는 DESIGN 7절 값과 같게 나오는지 확인하고 넣는다.

    python3 tests/fixtures/make_fixture.py            # → tests/fixtures/result_rack.json
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from layoutkit import data as D          # noqa: E402
from layoutkit import spec as S          # noqa: E402

EX = ROOT / "examples" / "rack_fr5"
OUT = Path(__file__).resolve().parent / "result_rack.json"
DS_COLORS = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00"]   # 데이터셋 색 고정 순서


# ------------------------------------------------------------------ 읽기
def load_v1():
    raw = json.loads((EX / "data" / "v1_tags.json").read_text(encoding="utf-8"))
    eps = []
    for e in raw["episodes"]:
        m = e["meta"]
        tag = m["fr5rec"]["tag"]
        # 출발 받침 배열: scene "받침0[○○·○]  받침1[Y○○R]" 에서 출발 받침 칸 글자
        arr = None
        for part in tag["scene"].split():
            if part.startswith(f"받침{tag['src'][0]}["):
                arr = part.split("[", 1)[1].rstrip("]")
        eps.append(D.episode(f"fr5_v1/{e['ep']}", "fr5_v1", start={"x": tag["red_xy"][0], "y": tag["red_xy"][1], "yaw": m.get("task_yaw_deg")},
                             goal={"x": tag["slot_xy"][0], "y": tag["slot_xy"][1]}, t=m["fr5rec"]["started_at"],
                             outcome=m.get("outcome"), source="fr5rec",
                             discrete={"start_slot": tag["src"][1], "goal_slot": tag["dst"][1], "arrangement": arr,
                                       "same_fixture": tag["src"][0] == tag["dst"][0]}))
    return D.Dataset("fr5_v1", eps, weight=0.5, meta={"note": "고정 배치 몇 가지로 모은 100판"})


def load_v2():
    raw = json.loads((EX / "data" / "v2_layouts_20261103.json").read_text(encoding="utf-8"))
    eps = []
    for e in raw["episodes"]:
        eps.append(D.episode(f"fr5_v2/{e['ep']}", "fr5_v2", start={"x": e["red_xy"][0], "y": e["red_xy"][1]},
                             goal={"x": e["ring_xy"][0], "y": e["ring_xy"][1]}, t=e["t"], outcome=e["outcome"], source="table",
                             discrete={"start_slot": e["red_slot"], "goal_slot": e["ring_slot"], "arrangement": e["arrangement"],
                                       "same_fixture": e["same_rack"]}))
    return D.Dataset("fr5_v2", eps, weight=1.0, meta={"note": "배치 추천으로 모은 판"})


# ------------------------------------------------------------------ 간단한 셈(rackrec 과 같은 정의)
def hex_centers(area, h):
    x0, x1, y0, y1 = area
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
                out.append((round(x, 2), round(y, 2)))
    return out


def cell_of(p, C, area):
    x0, x1, y0, y1 = area
    if not (x0 <= p[0] <= x1 and y0 <= p[1] <= y1):
        return -1
    return min(range(len(C)), key=lambda k: (C[k][0] - p[0]) ** 2 + (C[k][1] - p[1]) ** 2)


def clusters(P, r=12.0):
    lab = [-1] * len(P)
    c = 0
    for i in range(len(P)):
        if lab[i] >= 0:
            continue
        for j in range(len(P)):
            if lab[j] < 0 and math.dist(P[i], P[j]) < r:
                lab[j] = c
        c += 1
    return lab


def wcorr(a, b, w):
    sw = sum(w)
    ma = sum(x * u for x, u in zip(a, w)) / sw
    mb = sum(x * u for x, u in zip(b, w)) / sw
    cov = sum(u * (x - ma) * (y - mb) for x, y, u in zip(a, b, w))
    va = sum(u * (x - ma) ** 2 for x, u in zip(a, w))
    vb = sum(u * (y - mb) ** 2 for y, u in zip(b, w))
    return cov / math.sqrt(va * vb) if va > 0 and vb > 0 else 0.0


def median(v):
    s = sorted(v)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def side_table(eps, split):
    """행 = 출발 쪽 [화면 왼쪽, 오른쪽], 열 = 목표 쪽 [오른쪽, 왼쪽] — 대각선이 '건너편으로 옮김'(analyze/coupling.py 와 같은 표기).
    받침 spec 은 x_left_positive 라 화면 왼쪽 = x > split. v1: [[44, 0], [4, 52]]."""
    t = [[0, 0], [0, 0]]
    for e in eps:
        r = 0 if e["start"]["x"] > split else 1
        c = 0 if e["goal"]["x"] <= split else 1
        t[r][c] += 1
    n = max(1, sum(map(sum, t)))
    return {"split": round(split, 1), "axis": "x", "rows": ["left", "right"], "cols": ["right", "left"], "left_is": "hi",
            "table": t, "acc": round(sum(max(r) for r in t) / n, 3), "n_cross": t[0][0] + t[1][1], "n": n}


def knn_acc(eps, split, k=5):
    """출발 xy 최근접 k 개(자기 빼고)의 다수결로 목표 쪽 맞히기."""
    if len(eps) <= k:
        return None
    P = [(e["start"]["x"], e["start"]["y"]) for e in eps]
    G = [e["goal"]["x"] > split for e in eps]
    ok = 0
    for i, p in enumerate(P):
        nb = sorted((math.dist(p, q), j) for j, q in enumerate(P) if j != i)[:k]
        vote = sum(1 for _, j in nb if G[j]) * 2 > k
        ok += vote == G[i]
    return round(ok / len(eps), 3)


def coupon(n):
    return round(n * sum(1.0 / k for k in range(1, n + 1)), 1) if n > 0 else 0.0


def status_of(v, good, bad, lower_better=True):
    if lower_better:
        return "good" if v <= good else "warn" if v <= bad else "bad"
    return "good" if v >= good else "warn" if v >= bad else "bad"


# ------------------------------------------------------------------ 수집 기록 csv → 날짜별 요약
def reason_code(r):
    """FR5-AutoCollect make_figures.reason_of 와 같은 묶음 — 코드만(글은 화면이 만든다)."""
    txt, v = r["reason"], r["verdict"]
    if v == "fail":
        if "뺄 때 받침이 같이 들렸다" in txt:
            return "fixture_lifted"
        if "받침이 움직였다" in txt:
            return "fixture_moved"
        if "튜브가 받침에 안 보인다" in txt:
            return "object_not_seen"
        return "other"
    return {"unsure": "goal_state_unknown", "norec": "not_recorded", "abort": "aborted"}.get(v)


def load_runs():
    """analyze/runs.py summarize 와 같은 모양(by_day 는 평평한 셈, 이유는 by_verdict, 시간은 durations.all)."""
    rows = list(csv.DictReader((EX / "data" / "runs_20261031_20261104.csv").open(encoding="utf-8")))
    days = sorted({r["time"][:10] for r in rows})
    by_day = []
    for d in days:
        rr = [r for r in rows if r["time"][:10] == d]
        D = {"day": d, "n": len(rr), "success": 0, "fail": 0, "unsure": 0, "other": 0,
             "kept": sum(1 for r in rr if r["kept"] == "success")}
        for r in rr:
            D[r["verdict"] if r["verdict"] in ("success", "fail", "unsure") else "other"] += 1
        ex = [float(r["exec_s"]) for r in rr if r["exec_s"]]
        D["exec_s_median"] = round(median(ex), 2) if ex else None
        by_day.append(D)
    reasons = {}
    for r in rows:
        if r["verdict"] == "success":
            continue
        c = reason_code(r)
        if c:
            R = reasons.setdefault(c, {"code": c, "n": 0, "by_verdict": {}})
            R["n"] += 1
            R["by_verdict"][r["verdict"]] = R["by_verdict"].get(r["verdict"], 0) + 1
    ex = [float(r["exec_s"]) for r in rows if r["exec_s"]]
    kept = {}
    for r in rows:
        kept[r["kept"] or "none"] = kept.get(r["kept"] or "none", 0) + 1
    return {"n": len(rows), "first": rows[0]["time"], "last": rows[-1]["time"], "kept": kept, "by_day": by_day,
            "reasons": sorted(reasons.values(), key=lambda x: (-x["n"], x["code"])),
            "durations": {"all": {"n": len(ex), "median": round(median(ex), 2), "min": round(min(ex), 2), "max": round(max(ex), 2)}}}


# ------------------------------------------------------------------ 가짜 추천(모양만) — 받침 둘, 빨강 칸 → 링 칸
def rack_at(name, p, k, psi_deg, pitch):
    """칸 k 가운데가 p 에 오도록 받침 가운데를 정한다(칸 k 가운데 = 받침 가운데 + (k − 1.5)·pitch·u)."""
    u = (math.cos(math.radians(psi_deg)), math.sin(math.radians(psi_deg)))
    return {"name": name, "x": round(p[0] - (k - 1.5) * pitch * u[0], 1), "y": round(p[1] - (k - 1.5) * pitch * u[1], 1),
            "yaw": psi_deg}


def slot_xy(rack, k, pitch):
    u = (math.cos(math.radians(rack["yaw"])), math.sin(math.radians(rack["yaw"])))
    return (rack["x"] + (k - 1.5) * pitch * u[0], rack["y"] + (k - 1.5) * pitch * u[1])


def rack_option(label, racks, ks, goal_rack, kg, pitch, why, score, parts):
    s = slot_xy(racks[0], ks, pitch)
    g = slot_xy(racks[goal_rack], kg, pitch)
    return {"label": label, "start": {"x": round(s[0], 1), "y": round(s[1], 1)}, "goal": {"x": round(g[0], 1), "y": round(g[1], 1)},
            "fixtures": racks,
            "discrete": {"start_slot": ks, "goal_slot": kg, "same_fixture": goal_rack == 0, "start_fixture": racks[0]["name"],
                         "goal_fixture": racks[goal_rack]["name"]},
            "score": score, "parts": parts, "why_codes": why, "cells": {}, "move_mm": round(math.dist(s, g), 1)}


# ------------------------------------------------------------------ 조립
def main():
    sp = S.load(EX / "spec.json")
    sp["_source"] = "examples/rack_fr5/spec.json"          # 절대 경로를 남기지 않는다
    v1, v2 = load_v1(), load_v2()
    dss = [v1, v2]
    eps = D.merge(dss)
    area = (sp["area"]["x"][0], sp["area"]["x"][1], sp["area"]["y"][0], sp["area"]["y"][1])
    h = float(sp["scales"]["h_xy_mm"])
    C = hex_centers(area, h)
    near_mm = float(sp["near_mm"])
    tg = sp["targets"]

    # 에피소드마다 칸·옮긴 거리
    for e in eps:
        e["cell_start"] = cell_of((e["start"]["x"], e["start"]["y"]), C, area)
        e["cell_goal"] = cell_of((e["goal"]["x"], e["goal"]["y"]), C, area)
        e["move_mm"] = round(math.dist((e["start"]["x"], e["start"]["y"]), (e["goal"]["x"], e["goal"]["y"])), 1)
    # 같은 자리 짝(출발·목표 둘 다 12 mm 안) — 뒤의 판에 dup 깃발
    dup_mm = float(tg["dup_mm"])
    dups = []
    for j, b in enumerate(eps):
        for a in eps[:j]:
            if a["dataset"] != b["dataset"]:
                continue
            ds_ = math.dist((a["start"]["x"], a["start"]["y"]), (b["start"]["x"], b["start"]["y"]))
            dg_ = math.dist((a["goal"]["x"], a["goal"]["y"]), (b["goal"]["x"], b["goal"]["y"]))
            if ds_ < dup_mm and dg_ < dup_mm:
                dups.append([a["id"], b["id"], round(max(ds_, dg_), 1)])
                if "dup" not in b["flags"]:
                    b["flags"].append("dup")
                break

    by = {d.name: [e for e in eps if e["dataset"] == d.name] for d in dss}
    W = [e["weight"] for e in eps]

    # 칸 채움
    def cov(role):
        cnt = [0.0] * len(C)
        cbd = {n: [0] * len(C) for n in by}
        for e in eps:
            k = e["cell_" + role]
            if k >= 0:
                cnt[k] += e["weight"]
                cbd[e["dataset"]][k] += 1
        return cnt, cbd
    cs, csd = cov("start")
    cg, cgd = cov("goal")
    # 놓을 수 있는 칸(가짜): 출발 42칸 = 영역 가운데에서 먼 5칸 뺌, 목표 26칸 = 카메라 쪽(y 큰 쪽)·가운데 가까운 칸
    cx, cy = (area[0] + area[1]) / 2, (area[2] + area[3]) / 2
    order_s = sorted(range(len(C)), key=lambda k: ((C[k][0] - cx) / 1.0) ** 2 + ((C[k][1] - cy) * 2.0) ** 2)
    reach_s = [False] * len(C)
    for k in order_s[:42]:
        reach_s[k] = True
    order_g = sorted(range(len(C)), key=lambda k: (C[k][0] - 30) ** 2 + ((C[k][1] - 600) * 2.2) ** 2)
    reach_g = [False] * len(C)
    for k in order_g[:26]:
        reach_g[k] = True

    def filled(cnt, mask=None):
        return sum(1 for k, c in enumerate(cnt) if c > 0 and (mask is None or mask[k]))

    f1s = filled(csd["fr5_v1"])
    f1g = filled(cgd["fr5_v1"])
    assert (f1s, f1g) == (20, 27), f"v1 채운 칸이 DESIGN 7절(20 · 27)과 다르다: {f1s} · {f1g}"
    assert len(C) == 47, len(C)
    emp_s = sum(1 for k in range(len(C)) if reach_s[k] and cs[k] == 0)
    emp_g = sum(1 for k in range(len(C)) if reach_g[k] and cg[k] == 0)

    def fill_dist(role):
        pts = [(e[role]["x"], e[role]["y"]) for e in eps]
        worst = 0.0
        for gx in range(int(area[0]), int(area[1]) + 1, 10):
            for gy in range(int(area[2]), int(area[3]) + 1, 10):
                worst = max(worst, min(math.dist((gx, gy), p) for p in pts))
        return round(worst, 1)

    coverage = {"h": h, "orient": "pointy", "centers": [list(c) for c in C], "n_cells": len(C),
                "start": {"count": [round(v, 2) for v in cs], "count_by_ds": csd, "reach": reach_s},
                "goal": {"count": [round(v, 2) for v in cg], "count_by_ds": cgd, "reach": reach_g},
                "yaw_bins": 0, "filled_start": filled(cs), "filled_goal": filled(cg),
                "filled_by_ds": {"fr5_v1": {"start": f1s, "goal": f1g},
                                 "fr5_v2": {"start": filled(csd["fr5_v2"]), "goal": filled(cgd["fr5_v2"])}},
                "reach_start": sum(reach_s), "reach_goal": sum(reach_g),
                "n_min": max(emp_s, emp_g), "coupon_random": coupon(sum(reach_s)),
                "fill_dist_mm": {"start": fill_dist("start"), "goal": fill_dist("goal")}}

    # 지름길
    pairs = []
    for a, b in sp["pairs"]:
        fa = lambda e, n=a: S.feature(e, n)      # noqa: E731
        fb = lambda e, n=b: S.feature(e, n)      # noqa: E731
        rho = wcorr([fa(e) for e in eps], [fb(e) for e in eps], W)
        rbd = {n: round(wcorr([fa(e) for e in L], [fb(e) for e in L], [1.0] * len(L)), 3) for n, L in by.items()}
        pairs.append({"a": a, "b": b, "rho": round(rho, 3), "rho_by_ds": rbd})
    assert abs(pairs[0]["rho_by_ds"]["fr5_v1"] - (-0.81)) < 0.006, pairs[0]
    xs = [e["start"]["x"] for e in eps]
    split = (min(xs) + max(xs)) / 2
    side = side_table(eps, split)
    side_ds = {}
    for n, L in by.items():                       # 데이터셋 하나만 볼 때의 쪽 표(분석 결과에는 없다 — 화면이 에피소드로 다시 셈)
        sx = [e["start"]["x"] for e in L]
        side_ds[n] = side_table(L, (min(sx) + max(sx)) / 2)
    t1 = side_ds["fr5_v1"]["table"]
    assert t1 == [[44, 0], [4, 52]], t1          # 왼쪽 → 오른쪽 44/44, 오른쪽 → 왼쪽 52/56
    knn = knn_acc(eps, split)
    gl = sum(1 for e in eps if e["goal"]["x"] > split) / len(eps)
    predict = {"knn_acc": knn, "chance": round(max(gl, 1 - gl), 3), "k": 5, "n": len(eps)}
    knn_ds = {n: knn_acc(L, side_ds[n]["split"]) for n, L in by.items()}
    coupling = {"pairs": pairs, "side": side, "predict": predict}

    # 옮긴 거리
    mv = [e["move_mm"] for e in eps]
    near_w = sum(e["weight"] for e in eps if e["move_mm"] <= near_mm) / sum(W)
    transfer = {"values": mv, "min": round(min(mv)), "median": round(median(mv)), "max": round(max(mv)),
                "near_share": round(near_w, 3), "near_mm": near_mm,
                "by_ds": {n: {"median": round(median([e["move_mm"] for e in L])),
                              "near_share": round(sum(1 for e in L if e["move_mm"] <= near_mm) / len(L), 3)} for n, L in by.items()}}

    # 서로 다른 자리
    def spots_of(L):
        ls = clusters([(e["start"]["x"], e["start"]["y"]) for e in L])
        lg = clusters([(e["goal"]["x"], e["goal"]["y"]) for e in L])
        return {"start": len(set(ls)), "goal": len(set(lg)), "pairs": len(set(zip(ls, lg)))}
    spots = spots_of(eps)
    spots.update({"dup_mm": dup_mm, "dups": dups[:200], "n_dups": len(dups),
                  "by_ds": {n: spots_of(L) for n, L in by.items()}})
    assert spots["by_ds"]["fr5_v1"] == {"start": 32, "goal": 43, "pairs": 99}, spots["by_ds"]["fr5_v1"]

    # 이산 칸
    strata = []
    for st in sp["strata"]:
        vals = st["values"]
        shares = st.get("shares") or [1.0 / len(vals)] * len(vals)
        rows = []
        for v, tshare in zip(vals, shares):
            n = sum(1 for e in eps if e["discrete"].get(st["name"]) == v)
            w = sum(e["weight"] for e in eps if e["discrete"].get(st["name"]) == v)
            rows.append({"value": v, "n": n, "share": round(w / sum(W), 3), "target": round(tshare, 3),
                         "n_by_ds": {nm: sum(1 for e in L if e["discrete"].get(st["name"]) == v) for nm, L in by.items()}})
        strata.append({"name": st["name"], "rows": rows, "max_dev": round(max(abs(r["share"] - r["target"]) for r in rows), 3)})
    assert [r["n_by_ds"]["fr5_v1"] for r in strata[0]["rows"]] == [31, 16, 8, 45]
    assert [r["n_by_ds"]["fr5_v1"] for r in strata[1]["rows"]] == [25, 22, 25, 28]

    ranges = {}
    for k in ("start.x", "start.y", "goal.x", "goal.y"):
        v = [S.feature(e, k) for e in eps]
        ranges[k] = [round(min(v)), round(max(v))]

    # 시험 배치 근처 깃발(가짜 두 판)
    for e in eps:
        if e["id"] in ("fr5_v2/ep_017", "fr5_v2/ep_011"):
            e["flags"].append("near_holdout")

    # 신호등 카드
    rmax = max(pairs, key=lambda p: abs(p["rho"]))
    cov_share = min(filled(cs, reach_s) / sum(reach_s), filled(cg, reach_g) / sum(reach_g))
    worst = max(strata, key=lambda s: s["max_dev"])
    wrow = max(worst["rows"], key=lambda r: abs(r["share"] - r["target"]))
    cards = [
        {"id": "coupling", "status": status_of(abs(rmax["rho"]), tg["rho_max"], tg["rho_bad"]), "value": round(abs(rmax["rho"]), 3),
         "unit": "|ρ|", "target": f"≤ {tg['rho_max']}", "code": None, "args": {"pair": f"{rmax['a']}→{rmax['b']}", "rho": rmax["rho"]}},
        {"id": "predict", "status": status_of(knn, tg["predict_good"], tg["predict_bad"]), "value": knn, "unit": "acc",
         "target": f"≤ {tg['predict_good']}", "code": None, "args": {"acc": knn, "chance": predict["chance"], "k": 5}},
        {"id": "near", "status": status_of(near_w, tg["near_share"], tg["near_warn"], lower_better=False), "value": round(near_w, 3),
         "unit": "", "target": f"≥ {tg['near_share']}", "code": None, "args": {"near_mm": near_mm, "share": round(near_w, 3)}},
        {"id": "coverage", "status": status_of(cov_share, tg["coverage_good"], tg["coverage_warn"], lower_better=False),
         "value": round(cov_share, 3), "unit": "", "target": f"≥ {tg['coverage_good']}", "code": None,
         "args": {"filled_start": filled(cs, reach_s), "reach_start": sum(reach_s), "filled_goal": filled(cg, reach_g),
                  "reach_goal": sum(reach_g), "empty_start": emp_s, "empty_goal": emp_g}},
        {"id": "strata", "status": status_of(worst["max_dev"], tg["strata_dev_good"], tg["strata_dev_bad"]),
         "value": worst["max_dev"], "unit": "", "target": f"≤ {tg['strata_dev_good']}", "code": None,
         "args": {"name": worst["name"], "value": wrow["value"], "share": wrow["share"], "target_share": wrow["target"],
                  "dir": "less" if wrow["share"] > wrow["target"] else "more"}},
        {"id": "dups", "status": "info", "value": round(len(dups) / len(eps), 3), "unit": "", "target": None,
         "code": "dups_info", "args": {"n": len(dups), "dup_mm": dup_mm}},
        {"id": "n_min", "status": "info", "value": coverage["n_min"], "unit": "", "target": None, "code": "n_min_info",
         "args": {"n_min": coverage["n_min"], "coupon": coverage["coupon_random"]}},
    ]
    code_of = {("coupling", "bad"): "coupling_high", ("coupling", "warn"): "coupling_warn", ("coupling", "good"): "coupling_ok",
               ("predict", "bad"): "predict_high", ("predict", "warn"): "predict_warn", ("predict", "good"): "predict_ok",
               ("near", "bad"): "near_low", ("near", "warn"): "near_low", ("near", "good"): "near_ok",
               ("coverage", "bad"): "coverage_low", ("coverage", "warn"): "coverage_low", ("coverage", "good"): "coverage_ok",
               ("strata", "bad"): "strata_skew", ("strata", "warn"): "strata_skew", ("strata", "good"): "strata_ok"}
    for c in cards:
        c["code"] = c["code"] or code_of[(c["id"], c["status"])]

    # 가짜 추천 3개 — 빈 칸(출발·목표) 쪽으로. A: 같은 받침 안 가까이, B·C: 같은 쪽(왼→왼, 오→오)으로 상관 낮추기
    pitch = float(sp["layout"]["fixtures"][0]["pitch_mm"])
    opts = [
        rack_option("A", [rack_at("rack0", (138.9, 630.0), 0, 180.0, pitch), {"name": "rack1", "x": -60.0, "y": 520.0, "yaw": 30.0}],
                    0, 0, 2, pitch, ["empty_start_cell", "empty_goal_cell", "adds_near"], 1.42,
                    {"var_start": 0.61, "var_goal": 0.22, "coupling": 0.31, "strata": 0.18, "effort": -0.10}),
        rack_option("B", [rack_at("rack0", (216.9, 505.0), 3, 0.0, pitch), rack_at("rack1", (190.9, 640.0), 1, 0.0, pitch)],
                    3, 1, 1, pitch, ["empty_start_cell", "empty_goal_cell", "lowers_coupling"], 1.17,
                    {"var_start": 0.40, "var_goal": 0.25, "coupling": 0.44, "strata": 0.12, "effort": -0.04}),
        rack_option("C", [rack_at("rack0", (-120.9, 545.0), 1, 0.0, pitch), rack_at("rack1", (-172.9, 645.0), 0, 0.0, pitch)],
                    1, 1, 0, pitch, ["empty_start_cell", "empty_goal_cell", "balances_strata"], 0.98,
                    {"var_start": 0.12, "var_goal": 0.52, "coupling": 0.15, "strata": 0.25, "effort": -0.06}),
    ]
    for o in opts:
        o["cells"] = {"start": cell_of((o["start"]["x"], o["start"]["y"]), C, area),
                      "goal": cell_of((o["goal"]["x"], o["goal"]["y"]), C, area)}
    recommend = {"options": opts,
                 "holdout": [{"start": {"x": 150.0, "y": 520.0}, "goal": {"x": -60.0, "y": 600.0}},
                             {"start": {"x": -40.0, "y": 480.0}, "goal": {"x": 10.0, "y": 560.0}}],
                 "skipped_checks": [], "n_cand": 4096, "n_feasible": 121, "seed": 20261102,
                 # (자리, 방향) 칸 기준 — recommend 가 내는 모양(값은 그럴듯하게)
                 "cells": {"h": h, "n_xy": len(C), "n_psi": [3, 3], "reach_start": 60, "reach_goal": 41, "reach_start_xy": sum(reach_s),
                           "reach_goal_xy": sum(reach_g), "n_min": 39, "reach_n_ok": 121, "reach_n": 16384}}

    same = {n: [bool(e["discrete"].get("same_fixture")) for e in L] for n, L in by.items()}
    M = [("n", None, {n: len(L) for n, L in by.items()}),
         ("rho:start.x→goal.x", None, pairs[0]["rho_by_ds"]),
         ("rho:start.y→goal.y", None, pairs[1]["rho_by_ds"]),
         ("rho", "lower", {n: max(abs(pairs[0]["rho_by_ds"][n]), abs(pairs[1]["rho_by_ds"][n])) for n in by}),
         ("side_acc", "lower", {n: side_ds[n]["acc"] for n in by}),
         ("predict", "lower", knn_ds),
         ("near_share", "higher", {n: v["near_share"] for n, v in transfer["by_ds"].items()}),
         ("move_median", None, {n: v["median"] for n, v in transfer["by_ds"].items()}),
         ("filled_start", "higher", {n: v["start"] for n, v in coverage["filled_by_ds"].items()}),
         ("filled_goal", "higher", {n: v["goal"] for n, v in coverage["filled_by_ds"].items()}),
         ("spots_start", "higher", {n: v["start"] for n, v in spots["by_ds"].items()}),
         ("spots_goal", "higher", {n: v["goal"] for n, v in spots["by_ds"].items()}),
         ("spots_pairs", "higher", {n: v["pairs"] for n, v in spots["by_ds"].items()}),
         ("same_fixture", None, {n: round(sum(v) / len(v), 3) for n, v in same.items()}),
         ("same_fixture_n", None, {n: sum(v) for n, v in same.items()})]
    names = list(by)
    compare = {"datasets": names, "metrics": [
        {"key": k, "values": v, "better": b,
         "diff": round(v[names[-1]] - v[names[0]], 3) if None not in (v[names[0]], v[names[-1]]) else None} for k, b, v in M]}

    timeline = [{"t": e["t"], "id": e["id"], "dataset": e["dataset"], "outcome": e["outcome"]}
                for e in sorted(eps, key=lambda e: e["t"] or "")]
    datasets = []
    for i, d in enumerate(dss):
        s = d.summary()
        s.pop("meta", None)
        s["color"] = DS_COLORS[i % len(DS_COLORS)]
        datasets.append(s)

    result = {"tool": "layoutkit", "version": "0.1.0", "created": "2026-11-04T16:00:00", "spec": sp, "datasets": datasets,
              "episodes": eps, "area": sp["area"], "cards": cards, "coverage": coverage, "coupling": coupling,
              "transfer": transfer, "spots": spots, "strata": strata, "ranges": ranges, "timeline": timeline,
              "runs": load_runs(), "recommend": recommend, "compare": compare}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: 에피소드 {len(eps)} · 칸 {len(C)} · 채움 {coverage['filled_start']}/{coverage['filled_goal']} · "
          f"ρ {pairs[0]['rho']:+.2f} · knn {knn} · 가까이 {near_w:.0%}")
    return result


if __name__ == "__main__":
    main()
