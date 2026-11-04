"""한 번 돌리기(build) + 설정 파일 하나로 여러 데이터셋 분석·비교·추천·내보내기(run_config).

설정(JSON, 또는 PyYAML 이 있으면 YAML) — 상대 경로는 설정 파일이 있는 폴더 기준:

    {
      "spec": "examples/rack_fr5/spec.json",
      "datasets": [{"name": "fr5_v1", "path": "examples/rack_fr5/data/v1_tags.json", "weight": 0.5},
                   {"name": "fr5_v2", "path": "examples/rack_fr5/data/v2_layouts_20261103.json", "kind": "table",
                    "opt": {"map": {"start": "red_xy", "goal": "ring_xy"}}}],
      "runs": ["examples/rack_fr5/data/runs_20261031_20261104.csv"],
      "recommend": {"n": 3, "seed": 1},            // 없거나 false 면 추천 안 함
      "outcomes": ["success", null],               // 분석에 쓸 결과(기본)
      "out": {"dir": "out", "json": "result.json", "html": "report.html", "csv": "episodes.csv", "cards_csv": "cards.csv",
              "png": "fig", "lang": "ko"}
    }
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .. import spec as SP
from ..adapters import Runs, load_dataset, load_runs, parse_arg


def load_datasets(items, weights=None, kind="auto", opt=None):
    """['이름=경로' | 경로 | {"name", "path", "weight", "kind", "opt"}] → (Dataset 목록, Runs | None)."""
    weights = dict(weights or {})
    dsl, runs = [], []
    for it in items or []:
        if isinstance(it, dict):
            nm, p = it.get("name"), it["path"]
            k = it.get("kind", kind)
            o = dict(opt or {}, **(it.get("opt") or {}))
            w = float(it.get("weight", weights.get(nm, 1.0) if nm else 1.0))
        else:
            nm, p = parse_arg(str(it))
            k, o, w = kind, dict(opt or {}), None
        x = load_dataset(p, kind=k, name=nm, weight=1.0 if w is None else w, **o)
        if isinstance(x, Runs):
            runs += list(x)
            continue
        if w is None and x.name in weights:                         # 이름이 정해진 뒤 --weight 이름=무게(읽을 때 무게 1 → 여기서 곱함)
            x = type(x)(x.name, x.episodes, weight=weights[x.name], meta=x.meta)
        dsl.append(x)
    return dsl, (Runs(runs) if runs else None)


def build(data, spec=None, weights=None, runs=None, recommend=False, n=3, seed=None, out_html=None, out_json=None,
          png=None, lang=None, kind="auto", opt=None, outcomes=("success", None), say=print) -> dict:
    """데이터 → analyze →(추천)→ JSON·HTML·PNG. 명령·감시·설정 실행이 모두 이것을 쓴다. 반환 result."""
    from .. import analyze as _an
    from .. import have_report, recommend as _rec, render as _render, export_png as _png
    from ..analyze import coverage as CV
    from ..analyze import save
    sp = SP.load(spec)
    if lang:
        sp["lang"] = lang
    dsl, runs_in = load_datasets(data, weights, kind, opt)
    if not dsl:
        raise ValueError("데이터셋이 없다")
    rr = list(runs_in or [])
    for r in runs or []:
        rr += load_runs(r) if isinstance(r, (str, Path)) else [r]
    res = _an(dsl, sp, runs=rr or None, outcomes=outcomes)
    if recommend:
        opts = _rec(dsl, sp, result=res, n=int(n), seed=seed)
        if res.get("recommend") is None:
            res["recommend"] = opts
        CV.apply_reach(res)                                          # 추천이 채운 reach 로 N_min·카드 다시
        from ..analyze import _jsonable
        res = _jsonable(res)
    if out_json:
        save(res, out_json)
        say(f"결과 저장: {out_json}")
    if out_html:
        if not have_report():
            raise ImportError("layoutkit.report 가 없다 — 화면(HTML)을 못 만든다. --json 으로 결과만 저장할 수 있다")
        _render(res, str(out_html), sp["lang"])
        say(f"화면 저장: {out_html}")
    if png:
        _png(res, str(png))
        say(f"그림 저장: {png}/")
    return res


# ---------------------------------------------------------------- 내보내기
EP_COLS = ["id", "dataset", "t", "outcome", "weight", "start_x", "start_y", "start_yaw", "goal_x", "goal_y", "goal_yaw",
           "move_mm", "cell_start", "cell_goal", "flags"]


def export_episodes_csv(res: dict, path) -> Path:
    """에피소드 표(한 줄 = 에피소드) — discrete 키는 열로 덧붙인다."""
    disc = []
    for e in res.get("episodes") or []:
        for k in e.get("discrete") or {}:
            if k not in disc:
                disc.append(k)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(EP_COLS + [f"d.{k}" for k in disc])
        for e in res.get("episodes") or []:
            s, g = e.get("start") or {}, e.get("goal") or {}
            w.writerow([e["id"], e["dataset"], e.get("t") or "", e.get("outcome") or "", e.get("weight"), s.get("x"), s.get("y"),
                        s.get("yaw", ""), g.get("x"), g.get("y"), g.get("yaw", ""), e.get("move_mm"), e.get("cell_start"),
                        e.get("cell_goal"), " ".join(e.get("flags") or [])] + [(e.get("discrete") or {}).get(k, "") for k in disc])
    return p


def export_cards_csv(res: dict, path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "status", "value", "unit", "target", "code", "args"])
        for c in res.get("cards") or []:
            w.writerow([c["id"], c["status"], c["value"], c["unit"], c.get("target") or "", c["code"],
                        json.dumps(c.get("args") or {}, ensure_ascii=False)])
    return p


def _read_cfg(path: Path) -> dict:
    txt = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as e:
            raise RuntimeError("YAML 설정은 PyYAML 이 필요하다(pip install pyyaml) — 아니면 JSON") from e
        return yaml.safe_load(txt) or {}
    return json.loads(txt)


def run_config(path, say=print) -> dict:
    """설정 파일 → build + CSV 내보내기. 반환 result."""
    cp = Path(path).expanduser()
    cfg = _read_cfg(cp)
    base = cp.parent

    def rel(p):
        q = Path(str(p)).expanduser()
        return q if q.is_absolute() else base / q
    items = []
    for d in cfg.get("datasets") or []:
        if isinstance(d, dict):
            items.append(dict(d, path=str(rel(d["path"]))))
        else:
            nm, p = parse_arg(str(d))
            items.append({"name": nm, "path": str(rel(p))} if nm else str(rel(p)))
    out = cfg.get("out") or {}
    od = rel(out.get("dir", "."))
    od.mkdir(parents=True, exist_ok=True)
    rc = cfg.get("recommend")
    spec = cfg.get("spec")
    spec = str(rel(spec)) if isinstance(spec, str) else spec
    oc = cfg.get("outcomes")
    res = build(items, spec, runs=[str(rel(r)) for r in (cfg.get("runs") or [])], recommend=bool(rc),
                n=int((rc or {}).get("n", 3)) if isinstance(rc, dict) else 3, seed=(rc or {}).get("seed") if isinstance(rc, dict) else None,
                out_json=od / out["json"] if out.get("json") else None, out_html=od / out["html"] if out.get("html") else None,
                png=od / out["png"] if out.get("png") else None, lang=out.get("lang"),
                outcomes=tuple(oc) if oc is not None else ("success", None), say=say)
    if out.get("csv"):
        say(f"에피소드 표: {export_episodes_csv(res, od / out['csv'])}")
    if out.get("cards_csv"):
        say(f"카드 표: {export_cards_csv(res, od / out['cards_csv'])}")
    return res
