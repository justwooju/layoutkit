"""analyze(datasets, spec, runs=None) → result(docs/ARCHITECTURE.md 3절 모양). 화면·추천·자동화는 이 dict 만 읽는다.

쓰는 에피소드 = 집은·놓은 자리가 둘 다 있고 outcome 이 outcomes(기본 success·None) 안인 것. 나머지 자리 있는 판은
episodes 에 "excluded" 깃발로 남고(화면 표), 자리 없는 판은 unusable 목록에만 남는다.
DESIGN 3절에 더한 키(빼지 않음): coverage.{start,goal}.n·outside·cells_yaw, coverage.yaw·n_theory·n_hex·n_min_yaw·n_min_basis·hull_m2·
filled_*_yaw, coupling.side.rows·cols·left_is·acc_w·n_cross, transfer.near_n, spots.n_dups·dup_episodes, strata[].n_known·n_other,
discrete(이산 값 셈), unusable, notes.
"""
from __future__ import annotations

import copy
import time
from pathlib import Path

import numpy as np

from .. import spec as SP
from ..data import Dataset, valid
from . import compare as CM
from . import coupling as CP
from . import coverage as CV
from . import distribution as DI
from . import runs as RU
from . import verdict as VD

DS_COLORS = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442", "#000000"]   # Okabe–Ito 순서. spec.dataset_colors {이름: 색} 또는 데이터셋 meta.color 가 먼저


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        return _jsonable(o.tolist())
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        f = float(o)
        return f if np.isfinite(f) else None
    if isinstance(o, float) and not np.isfinite(o):
        return None
    if isinstance(o, Path):
        return str(o)
    return o


def as_datasets(datasets) -> list[Dataset]:
    from ..adapters import Runs, load_dataset, parse_arg
    if isinstance(datasets, (Dataset, str, Path)):
        datasets = [datasets]
    out = []
    for d in datasets or []:
        if isinstance(d, Dataset):
            out.append(d)
        elif isinstance(d, (str, Path)):
            nm, p = parse_arg(str(d))
            x = load_dataset(p, name=nm)
            if isinstance(x, Runs):
                raise ValueError(f"{p}: 실행 기록이다 — analyze(..., runs=) 로 준다")
            out.append(x)
        else:
            raise TypeError(f"데이터셋이 아니다: {type(d).__name__}")
    names = [d.name for d in out]
    if len(set(names)) != len(names):
        raise ValueError(f"데이터셋 이름이 겹친다: {names} — '이름=경로' 또는 name= 으로 나눈다")
    return out


def _runs_list(runs):
    if runs is None:
        return None
    from ..adapters import Runs, load_runs
    if isinstance(runs, (str, Path)):
        return load_runs(runs)
    if isinstance(runs, (list, tuple)) and runs and isinstance(runs[0], (str, Path)):
        rows = []
        for r in runs:
            rows += load_runs(r)
        return Runs(rows)
    return list(runs)


def _spec_out(sp):
    from ..adapters import display_path
    s = copy.deepcopy(sp)
    if s.get("_source"):
        s["_source"] = display_path(s["_source"])
    return s


def analyze(datasets, spec=None, runs=None, outcomes=("success", None)) -> dict:
    """데이터셋들(Dataset · 경로 · '이름=경로') + spec(경로 · dict · None) → result dict."""
    from .. import __version__
    dsl = as_datasets(datasets)
    sp = SP.load(spec)                                               # dict·경로·None — 기본값을 채운다(이미 채운 것도 그대로)
    outcomes = tuple(outcomes) if outcomes is not None else None
    usable, used, unusable, notes = [], [], [], []
    for d in dsl:
        for e in d.episodes:
            if not valid(e):
                unusable.append({"id": e["id"], "dataset": d.name, "t": e.get("t"), "outcome": e.get("outcome")})
                continue
            e = copy.deepcopy(e)
            e["flags"] = list(e.get("flags") or [])
            usable.append(e)
            if outcomes is None or e.get("outcome") in outcomes:
                used.append(e)
            else:
                e["flags"].append("excluded")
    area = sp.get("area") or SP.area_from_data(used or usable)
    if not sp.get("area"):
        notes.append("area_from_data")
    by_ds = {d.name: [e for e in used if e["dataset"] == d.name] for d in dsl}
    names = [d.name for d in dsl]
    cov, per = CV.coverage(used, sp, area, names)
    # 안 쓴(결과로 뺀) 판도 칸 번호는 붙인다(화면 표·지도)
    C = np.asarray(cov["centers"], float).reshape(-1, 2)
    at = CV.area_tuple(area)
    ys = cov.get("yaw")
    for e in usable:
        if e["id"] in per:
            continue
        per[e["id"]] = {}
        for role in ("start", "goal"):
            per[e["id"]][f"cell_{role}"] = int(CV.cell_of([[e[role]["x"], e[role]["y"]]], C, at)[0])
            if ys:
                per[e["id"]][f"yaw_bin_{role}"] = CV.yaw_bin(e[role].get("yaw"), ys)
    cp = CP.coupling(used, sp, area, by_ds)
    tr, dist = DI.transfer(used, sp["near_mm"])
    spots, dup_ids = DI.spots(used, float(sp["targets"]["dup_mm"]))
    near_mm = float(sp["near_mm"])
    for e in usable:
        e.update(per.get(e["id"], {}))
        e["move_mm"] = round(float(np.hypot(e["goal"]["x"] - e["start"]["x"], e["goal"]["y"] - e["start"]["y"])), 1)
        if e["id"] in dup_ids:
            e["flags"].append("dup")
        if e.get("cell_start", 0) < 0 or e.get("cell_goal", 0) < 0:
            e["flags"].append("out_of_area")
        if e["move_mm"] <= near_mm:
            e["flags"].append("near")
    tl = sorted(usable, key=lambda e: (e.get("t") is None, str(e.get("t") or ""), e["id"]))
    colors = {}
    for i, d in enumerate(dsl):
        colors[d.name] = (sp.get("dataset_colors") or {}).get(d.name) or d.meta.get("color") or DS_COLORS[i % len(DS_COLORS)]
    ds_out = []
    for d in dsl:
        s = d.summary()
        ds_out.append({"name": d.name, "n": s["n"], "n_usable": s["n_usable"], "n_success": s["n_success"],
                       "n_used": len(by_ds[d.name]), "weight": d.weight, "color": colors[d.name],
                       "kind": d.meta.get("kind"), "path": d.meta.get("path"), "note": d.meta.get("note"),
                       "meta": {k: v for k, v in d.meta.items() if k not in ("kind", "path", "note", "color")}})
    side = cp.get("side") or {}
    result = {
        "tool": "layoutkit", "version": __version__, "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "spec": _spec_out(sp),
        "datasets": ds_out,
        "episodes": usable,
        "unusable": unusable,
        "area": {"x": [float(area["x"][0]), float(area["x"][1])], "y": [float(area["y"][0]), float(area["y"][1])]},
        "cards": [],
        "coverage": cov,
        "coupling": cp,
        "transfer": tr,
        "spots": spots,
        "strata": DI.strata(used, sp),
        "discrete": DI.discrete_counts(used),
        "ranges": DI.ranges(used),
        "timeline": [{"t": e.get("t"), "id": e["id"], "dataset": e["dataset"], "outcome": e.get("outcome"),
                      "flags": list(e["flags"])} for e in tl],
        "runs": RU.summarize(_runs_list(runs)),
        "recommend": None,
        "compare": CM.compare({k: v for k, v in by_ds.items() if v}, sp, area, side.get("axis", "x")),
        "notes": notes,
    }
    result["cards"] = VD.cards(result, sp)
    return _jsonable(result)


def save(result: dict, path) -> Path:
    """result → JSON 파일(한국어 그대로)."""
    import json
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)
    return p


def load_result(path) -> dict:
    import json
    return json.loads(Path(path).read_text(encoding="utf-8"))
