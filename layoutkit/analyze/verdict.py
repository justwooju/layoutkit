"""신호등 카드 — docs/ARCHITECTURE.md 3절 표. 문턱은 spec.targets. 카드에는 code·args 만 두고 사람 말은 화면(report/i18n)이 만든다.

카드: {"id", "status": good|warn|bad|info, "value", "unit", "target", "code", "args"}
code 는 CODES[(id, status)] — 화면 사전(report/i18n.py CARD)의 키다. args 키도 그 틀의 자리 이름과 같다
(coupling: a·b·rho·target · predict: acc·chance · near: share·near_mm·target · coverage: filled_*·reach_*(reach 가 없으면 칸 수) ·
strata: name·value·share·target_share·dir(less|more) · dups: n·dup_mm · n_min: n_min·coupon). 값을 낼 수 없는 카드는 빠진다.
"""
from __future__ import annotations

import numpy as np

CODES = {                                                           # report/i18n.py CARD 의 키와 같게
    ("coupling", "good"): "coupling_ok", ("coupling", "warn"): "coupling_warn", ("coupling", "bad"): "coupling_high",
    ("predict", "good"): "predict_ok", ("predict", "warn"): "predict_warn", ("predict", "bad"): "predict_high",
    ("near", "good"): "near_ok", ("near", "warn"): "near_low", ("near", "bad"): "near_low",
    ("coverage", "good"): "coverage_ok", ("coverage", "warn"): "coverage_low", ("coverage", "bad"): "coverage_low",
    ("strata", "good"): "strata_ok", ("strata", "warn"): "strata_skew", ("strata", "bad"): "strata_skew",
    ("dups", "info"): "dups_info",
    ("n_min", "info"): "n_min_info",
}
ORDER = ("coupling", "predict", "near", "coverage", "strata", "dups", "n_min")


def _le(v, good, bad):
    """작을수록 좋은 값."""
    return "good" if v <= good + 1e-12 else ("warn" if v <= bad + 1e-12 else "bad")


def _ge(v, good, warn):
    """클수록 좋은 값."""
    return "good" if v >= good - 1e-12 else ("warn" if v >= warn - 1e-12 else "bad")


def _card(cid, status, value, unit, target, args):
    return {"id": cid, "status": status, "value": None if value is None else round(float(value), 3), "unit": unit,
            "target": target, "code": CODES[(cid, status)], "args": args}


def cards(result: dict, spec: dict) -> list[dict]:
    T = spec["targets"]
    out = []
    cp = result.get("coupling") or {}
    best = None
    for p in cp.get("pairs") or []:
        if p.get("rho") is not None and (best is None or abs(p["rho"]) > abs(best["rho"])):
            best = p
    if best is not None:
        v = abs(best["rho"])
        out.append(_card("coupling", _le(v, T["rho_max"], T["rho_bad"]), v, "|ρ|", f"≤ {T['rho_max']:g}",
                         {"pair": f"{best['a']}→{best['b']}", "a": best["a"], "b": best["b"], "rho": best["rho"],
                          "target": T["rho_max"], "rho_max": T["rho_max"], "rho_bad": T["rho_bad"]}))
    pr = cp.get("predict") or {}
    if pr.get("knn_acc") is not None:
        sd = cp.get("side") or {}
        out.append(_card("predict", _le(pr["knn_acc"], T["predict_good"], T["predict_bad"]), pr["knn_acc"], "acc",
                         f"≤ {T['predict_good']:g}",
                         {"acc": pr["knn_acc"], "chance": pr["chance"], "k": pr["k"], "side_acc": sd.get("acc"),
                          "split": sd.get("split"), "axis": sd.get("axis"), "left_is": sd.get("left_is")}))
    tr = result.get("transfer") or {}
    if tr.get("near_share") is not None:
        out.append(_card("near", _ge(tr["near_share"], T["near_share"], T["near_warn"]), tr["near_share"], "share",
                         f"≥ {T['near_share']:g}", {"share": tr["near_share"], "n_near": tr["near_n"], "near_mm": tr["near_mm"],
                                                    "target": T["near_share"]}))
    cov = result.get("coverage") or {}
    if cov.get("n_cells"):
        fr, basis = {}, "all"
        for role in ("start", "goal"):
            n = np.asarray(cov[role]["n"], int)
            r = cov[role].get("reach")
            if r is not None:
                basis = "reach"
                r = np.asarray(r, bool)
                fr[role] = (int(((n > 0) & r).sum()), int(r.sum()))
            else:
                fr[role] = (int((n > 0).sum()), int(cov["n_cells"]))
        ratio = {k: (a / b if b else 0.0) for k, (a, b) in fr.items()}
        worst = min(ratio, key=ratio.get)
        v = ratio[worst]
        out.append(_card("coverage", _ge(v, T["coverage_good"], T["coverage_warn"]), v, "share", f"≥ {T['coverage_good']:g}",
                         {"role": worst, "filled_start": fr["start"][0], "reach_start": fr["start"][1],
                          "filled_goal": fr["goal"][0], "reach_goal": fr["goal"][1], "basis": basis,
                          "share_start": round(ratio["start"], 3), "share_goal": round(ratio["goal"], 3)}))
    st = [s for s in (result.get("strata") or []) if s.get("max_dev") is not None]
    if st:
        s = max(st, key=lambda s: s["max_dev"])
        row = max((r for r in s["rows"] if r["share"] is not None), key=lambda r: abs(r["share"] - r["target"]))
        out.append(_card("strata", _le(s["max_dev"], T["strata_dev_good"], T["strata_dev_bad"]), s["max_dev"], "dev",
                         f"≤ {T['strata_dev_good']:g}", {"name": s["name"], "value": row["value"], "share": row["share"],
                                                          "target_share": row["target"], "n": row["n"],
                                                          "dir": "less" if row["share"] > row["target"] else "more"}))
    sp = result.get("spots") or {}
    n_used = sum(1 for e in result.get("episodes") or [] if "excluded" not in (e.get("flags") or []))
    if n_used:
        out.append(_card("dups", "info", sp.get("dup_episodes", 0) / n_used, "share", None,
                         {"n": sp.get("n_dups", 0), "pairs": sp.get("n_dups", 0), "episodes": sp.get("dup_episodes", 0),
                          "dup_mm": sp.get("dup_mm")}))
    if cov.get("n_min") is not None:
        out.append(_card("n_min", "info", cov["n_min"], "episodes", None,
                         {"n_min": cov["n_min"], "n_min_yaw": cov.get("n_min_yaw"), "basis": cov.get("n_min_basis"),
                          "coupon": cov.get("coupon_random"), "n_theory": cov.get("n_theory")}))
    return out
