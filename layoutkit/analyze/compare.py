"""데이터셋끼리 같은 지표 나란히 + 차이(마지막 − 처음). 칸·영역은 합친 분석과 같은 것을 쓴다(나란히 볼 수 있게).
쪽 기준선(side_acc·predict)은 데이터셋마다 그 데이터셋만 볼 때와 같게 정한다(spec.side_split 이 숫자면 그 값) —
그래야 데이터셋 하나만 분석한 숫자(v1 0.96 · v2 0.63)와 같다.

metrics: [{"key", "values": {데이터셋: 값}, "diff", "better": "lower" | "higher" | None}]
key: n · rho(가장 큰 |ρ|) · rho:<a>→<b>(부호 있음) · predict(knn 맞힘) · side_acc · near_share · move_median ·
     filled_start · filled_goal · spots_start · spots_goal · spots_pairs · strata_dev · same_fixture(같은 고정물 비율, 있으면)
"""
from __future__ import annotations

from . import coupling as CP
from . import coverage as CV
from . import distribution as DI

BETTER = {"rho": "lower", "predict": "lower", "side_acc": "lower", "near_share": "higher", "filled_start": "higher",
          "filled_goal": "higher", "spots_start": "higher", "spots_goal": "higher", "spots_pairs": "higher", "strata_dev": "lower"}


def metrics_one(eps, spec, area, axis) -> dict:
    m = {"n": len(eps)}
    best = None
    for a, b in spec.get("pairs") or []:
        r = CP.pair_rho(eps, a, b)
        m[f"rho:{a}→{b}"] = None if r is None else round(r, 3)
        if r is not None and (best is None or abs(r) > best):
            best = abs(r)
    m["rho"] = None if best is None else round(best, 3)
    split = CP.split_value(eps, spec, area, axis) if eps else None
    if eps and split is not None:
        m["side_acc"] = CP.side_table(eps, spec, split, axis)["acc"]
        m["predict"] = CP.knn_predict(eps, split, axis)["knn_acc"]
    else:
        m["side_acc"] = m["predict"] = None
    tr, _ = DI.transfer(eps, spec["near_mm"])
    m["near_share"], m["move_median"] = tr["near_share"], tr["median"]
    if eps:
        cov, _ = CV.coverage(eps, spec, area, [])
        m["filled_start"], m["filled_goal"] = cov["filled_start"], cov["filled_goal"]
        sp, _ = DI.spots(eps, float(spec["targets"]["dup_mm"]))
        m["spots_start"], m["spots_goal"], m["spots_pairs"] = sp["start"], sp["goal"], sp["pairs"]
    else:
        for k in ("filled_start", "filled_goal", "spots_start", "spots_goal", "spots_pairs"):
            m[k] = None
    st = [s["max_dev"] for s in DI.strata(eps, spec) if s["max_dev"] is not None]
    m["strata_dev"] = max(st) if st else None
    sf = [(e.get("discrete") or {}).get("same_fixture") for e in eps]
    sf = [v for v in sf if v is not None]
    if sf:
        m["same_fixture"] = round(sum(1 for v in sf if v) / len(sf), 3)
        m["same_fixture_n"] = sum(1 for v in sf if v)
    return m


def compare(by_ds: dict, spec, area, axis) -> dict | None:
    if len(by_ds) < 2:
        return None
    per = {d: metrics_one(E, spec, area, axis) for d, E in by_ds.items()}
    keys = []
    for m in per.values():
        for k in m:
            if k not in keys:
                keys.append(k)
    names = list(by_ds)
    out = []
    for k in keys:
        vals = {d: per[d].get(k) for d in names}
        a, b = vals[names[0]], vals[names[-1]]
        diff = round(b - a, 3) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
        better = BETTER.get(k.split(":")[0] if not k.startswith("rho:") else None)
        out.append({"key": k, "values": vals, "diff": diff, "better": better})
    return {"datasets": names, "metrics": out}
