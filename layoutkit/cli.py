"""명령 — python -m layoutkit … (또는 설치하면 layoutkit …). docs/ARCHITECTURE.md 6절.

  layoutkit analyze DATA... [--spec spec.json] [--weight NAME=0.5] [--runs R] [--out report.html] [--json result.json] [--png fig/] [--lang en]
  layoutkit recommend DATA... --spec spec.json [--n 3] [--seed 1] [--out report.html] [--json result.json]
  layoutkit compare A B ... [--spec ...] --out compare.html [--json result.json]
  layoutkit watch DIR... --spec spec.json --out report.html [--every 5] [--recommend] [--once] [--max-builds N] [--until-n N] [--stop-file F]
  layoutkit report result.json --out report.html [--lang en]
  layoutkit init-spec DATA... --out spec.json
  layoutkit demo [--out demo/]
  layoutkit pipeline config.json
DATA = 폴더(fr5rec·LeRobot 자동 판별) · .csv · .json · .jsonl, '이름=경로' 로 이름을 붙인다. 실행 기록(runs_*.csv · runs.jsonl)을 DATA 에
섞어 주면 실행 기록으로 쓴다. 표 열 대응은 --map start.x=red_x, 어댑터 옵션은 --opt 키=값(값은 JSON 이면 JSON).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from . import __version__


def _kv(items, conv=str) -> dict:
    out = {}
    for s in items or []:
        if "=" not in s:
            raise ValueError(f"'키=값' 이어야 한다: {s}")
        k, v = s.split("=", 1)
        out[k.strip()] = conv(v.strip())
    return out


def _jval(v):
    try:
        return json.loads(v)
    except ValueError:
        return v


def _opt(a) -> dict:
    o = _kv(getattr(a, "opt", None), _jval)
    m = _kv(getattr(a, "map", None))
    if m:
        o["map"] = m
    return o


def _summary(res: dict) -> str:
    L = [f"layoutkit {res.get('version')} · {res.get('created')}"]
    for d in res.get("datasets") or []:
        L.append(f"  데이터셋 {d['name']}: {d['n']}판(쓸 수 있음 {d['n_usable']}, 씀 {d['n_used']}) · 무게 {d['weight']:g}")
    for c in res.get("cards") or []:
        v = c["value"]
        vs = "—" if v is None else (f"{v:.3g}" if isinstance(v, float) and not float(v).is_integer() else f"{v:g}")
        L.append(f"  [{c['status']:>4}] {c['id']:<9} {vs:>7} {c.get('target') or '':<8} {c['code']}")
    cp = (res.get("coupling") or {}).get("side")
    if cp:
        L.append(f"  쪽 표(기준 {cp['axis']} {cp['split']:g}, 행 출발 {cp['rows']}, 열 목표 {cp['cols']}): {cp['table']} · 맞힘 {cp['acc']}")
    rc = res.get("recommend")
    if rc:
        for o in rc.get("options") or []:
            s, g = o.get("start") or {}, o.get("goal") or {}
            L.append(f"  추천 {o.get('label')}: 집기 ({s.get('x', float('nan')):.0f}, {s.get('y', float('nan')):.0f}) → "
                     f"놓기 ({g.get('x', float('nan')):.0f}, {g.get('y', float('nan')):.0f}) · {', '.join(o.get('why_codes') or [])}")
    return "\n".join(L)


def _build(a, data, recommend=False, out_html=None):
    from .automate.pipeline import build
    weights = _kv(a.weight, float)
    return build(data, a.spec, weights=weights, runs=a.runs, recommend=recommend, n=getattr(a, "n", 3),
                 seed=getattr(a, "seed", None), out_html=out_html, out_json=a.json, png=getattr(a, "png", None),
                 lang=getattr(a, "lang", None), kind=a.kind, opt=_opt(a),
                 outcomes=None if a.all_outcomes else ("success", None), say=lambda s: print(s, file=sys.stderr))


def _need(pkg):
    from . import have_recommend, have_report
    ok = have_report() if pkg == "report" else have_recommend()
    if not ok:
        raise ImportError(f"layoutkit.{pkg} 가 없다(또는 아직 함수가 없다) — "
                          + ("화면(--out)을 만들 수 없다. --json 으로 결과만 저장할 수 있다" if pkg == "report"
                             else "추천을 할 수 없다. analyze 는 된다"))


# ---------------------------------------------------------------- 명령
def cmd_analyze(a):
    if a.out:
        _need("report")
    res = _build(a, a.data, out_html=a.out)
    print(_summary(res))
    return 0


def cmd_recommend(a):
    _need("recommend")
    if a.out:
        _need("report")
    res = _build(a, a.data, recommend=True, out_html=a.out)
    print(_summary(res))
    return 0


def cmd_compare(a):
    if len(a.data) < 2:
        raise ValueError("compare 는 데이터셋이 둘 이상이어야 한다")
    if a.out:
        _need("report")
    res = _build(a, a.data, out_html=a.out)
    print(_summary(res))
    cm = res.get("compare") or {}
    for m in cm.get("metrics") or []:
        print(f"  {m['key']:<24} " + " · ".join(f"{k} {v}" for k, v in m["values"].items()) + f"  (차이 {m['diff']})")
    return 0


def cmd_report(a):
    from . import render
    from .analyze import load_result
    _need("report")
    res = load_result(a.result)
    render(res, a.out, a.lang)
    print(f"화면 저장: {a.out}", file=sys.stderr)
    return 0


def cmd_watch(a):
    from .automate.pipeline import build
    from .automate.watch import watch
    if not (a.out or a.json):
        raise ValueError("watch 는 --out 또는 --json 이 있어야 한다")
    if a.out:
        _need("report")
    if a.recommend:
        _need("recommend")
    weights = _kv(a.weight, float)
    notify = a.notify or (str(Path(a.out or a.json).with_suffix(".watch.json")))

    def fn():
        return build(a.data, a.spec, weights=weights, runs=a.runs, recommend=a.recommend, n=a.n, seed=a.seed, out_html=a.out,
                     out_json=a.json, lang=a.lang, kind=a.kind, opt=_opt(a), outcomes=None if a.all_outcomes else ("success", None),
                     say=lambda s: None)
    st = watch(a.data, fn, every=a.every, settle=a.settle, once=a.once, max_builds=a.max_builds, max_checks=a.max_checks,
               until_n=a.until_n, stop_file=a.stop_file, notify=notify, say=lambda s: print(s, file=sys.stderr))
    return 0 if not st.get("error") else 1


def guess_spec(episodes, pad_mm=30.0) -> dict:
    """데이터로 spec 짐작: area(범위 + 여유, 10 mm 단위로 바깥으로), strata(값 종류 2~8개인 정수 discrete), use_yaw, 칸 크기."""
    xs = [e[k]["x"] for e in episodes for k in ("start", "goal")]
    ys = [e[k]["y"] for e in episodes for k in ("start", "goal")]
    if not xs:
        raise ValueError("쓸 수 있는 에피소드(집은·놓은 자리)가 없다")
    lo = lambda v: math.floor((v - pad_mm) / 10.0) * 10.0   # noqa: E731
    hi = lambda v: math.ceil((v + pad_mm) / 10.0) * 10.0    # noqa: E731
    area = {"x": [lo(min(xs)), hi(max(xs))], "y": [lo(min(ys)), hi(max(ys))]}
    side = min(area["x"][1] - area["x"][0], area["y"][1] - area["y"][0])
    h = 30.0 if side >= 240 else max(5.0, round(side / 8.0, 1))
    strata = []
    keys = []
    for e in episodes:
        for k in e.get("discrete") or {}:
            if k not in keys:
                keys.append(k)
    for k in keys:
        vals = {(e.get("discrete") or {}).get(k) for e in episodes} - {None}
        if 2 <= len(vals) <= 8 and all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
            strata.append({"name": k, "values": sorted(vals)})
    has_yaw = any(e[r].get("yaw") is not None for e in episodes for r in ("start", "goal"))
    return {"task": "pick_place", "title": None, "area": area, "scales": {"h_xy_mm": h, "h_yaw_deg": 20.0, "use_yaw": has_yaw},
            "near_mm": 100.0, "strata": strata, "pairs": [["start.x", "goal.x"], ["start.y", "goal.y"]],
            "frame": {"x_left_positive": False, "note": "init-spec 짐작 — 화면 방향(x_left_positive)·area 를 확인한다"}}


def cmd_init_spec(a):
    from .automate.pipeline import load_datasets
    dsl, _ = load_datasets(a.data, kind=a.kind, opt=_opt(a))
    eps = [e for d in dsl for e in d.usable()]
    sp = guess_spec(eps)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(sp, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"spec 저장: {a.out} — area x {sp['area']['x']} · y {sp['area']['y']} · 칸 {sp['scales']['h_xy_mm']:g} mm · "
          f"strata {[s['name'] for s in sp['strata']]}", file=sys.stderr)
    return 0


def examples_dir() -> Path | None:
    p = Path(__file__).resolve().parents[1] / "examples"
    return p if p.is_dir() else None


def cmd_demo(a):
    from . import have_recommend, have_report
    from .automate.pipeline import build, export_episodes_csv
    ex = Path(a.examples) if a.examples else examples_dir()
    if ex is None or not (ex / "rack_fr5" / "spec.json").is_file():
        raise FileNotFoundError("예제 폴더(examples/rack_fr5)를 못 찾았다 — 저장소에서 실행하거나 --examples 로 알려 준다")
    rk = ex / "rack_fr5"
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    data = [f"fr5_v1={rk / 'data' / 'v1_tags.json'}", f"fr5_v2={rk / 'data' / 'v2_layouts_20261103.json'}"]
    runs = sorted((rk / "data").glob("runs_*.csv"))
    rec = have_recommend() and not a.no_recommend
    html = out / "report.html" if have_report() else None
    say = lambda s: print(s, file=sys.stderr)   # noqa: E731
    res = build(data, str(rk / "spec.json"), weights={"fr5_v1": 0.5}, runs=[str(r) for r in runs], recommend=rec, n=3,
                seed=a.seed, out_html=html, out_json=out / "result.json", lang=a.lang, say=say)
    export_episodes_csv(res, out / "episodes.csv")
    print(_summary(res))
    if not rec and not a.no_recommend:
        say("알림: layoutkit.recommend 가 없어 추천 없이 만들었다")
    if html is None:
        say("오류: layoutkit.report 가 없어 화면(report.html)을 못 만들었다 — result.json·episodes.csv 만 저장")
        return 2
    return 0


def cmd_pipeline(a):
    from .automate.pipeline import run_config
    res = run_config(a.config, say=lambda s: print(s, file=sys.stderr))
    print(_summary(res))
    return 0


# ---------------------------------------------------------------- 인자
def _data_args(p, need_spec=False):
    p.add_argument("data", nargs="+", help="데이터 경로(이름=경로 가능)")
    p.add_argument("--spec", required=need_spec, help="과제 선언 JSON·YAML")
    p.add_argument("--weight", action="append", default=[], metavar="NAME=W", help="데이터셋 무게(여러 번)")
    p.add_argument("--runs", action="append", default=[], metavar="RUNS", help="수집 실행 기록(runs_*.csv · runs.jsonl)")
    p.add_argument("--kind", default="auto", help="형식(auto · fr5rec · lerobot · table · fr5auto_runs)")
    p.add_argument("--map", action="append", default=[], metavar="KEY=COL", help="표 열 대응(예: start.x=red_x)")
    p.add_argument("--opt", action="append", default=[], metavar="KEY=VAL", help="어댑터 옵션(예: grip=6, units=\"m\")")
    p.add_argument("--all-outcomes", action="store_true", help="실패·불확실 판도 분석에 넣는다(기본: success·결과 없음만)")
    p.add_argument("--json", help="결과 JSON 저장")
    p.add_argument("--lang", choices=["ko", "en"], help="화면 말")


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="layoutkit", description="시연 데이터셋 배치 분석·추천·화면")
    ap.add_argument("--version", action="version", version=f"layoutkit {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("analyze", help="분석(→ JSON·HTML·PNG)")
    _data_args(p)
    p.add_argument("--out", help="화면 HTML")
    p.add_argument("--png", help="그림 폴더(matplotlib)")
    p.set_defaults(fn=cmd_analyze)
    p = sub.add_parser("recommend", help="분석 + 다음 배치 추천")
    _data_args(p, need_spec=True)
    p.add_argument("--n", type=int, default=3)
    p.add_argument("--seed", type=int)
    p.add_argument("--out")
    p.add_argument("--png")
    p.set_defaults(fn=cmd_recommend)
    p = sub.add_parser("compare", help="데이터셋 나란히")
    _data_args(p)
    p.add_argument("--out")
    p.add_argument("--png")
    p.set_defaults(fn=cmd_compare)
    p = sub.add_parser("watch", help="폴더 감시 → 다시 만들기")
    _data_args(p, need_spec=True)
    p.add_argument("--out")
    p.add_argument("--every", type=float, default=5.0, help="확인 주기(s)")
    p.add_argument("--settle", type=int, default=1, help="바뀐 지문이 이만큼 연속 같아야 다시 만든다")
    p.add_argument("--recommend", action="store_true")
    p.add_argument("--n", type=int, default=3)
    p.add_argument("--seed", type=int)
    p.add_argument("--once", action="store_true", help="한 번 만들고 끝")
    p.add_argument("--max-builds", type=int)
    p.add_argument("--max-checks", type=int)
    p.add_argument("--until-n", type=int, help="쓴 에피소드가 이만큼이면 끝")
    p.add_argument("--stop-file", help="이 파일이 생기면 끝")
    p.add_argument("--notify", help="알림 파일(기본: 출력 이름.watch.json)")
    p.set_defaults(fn=cmd_watch)
    p = sub.add_parser("report", help="저장한 결과로 화면만")
    p.add_argument("result")
    p.add_argument("--out", required=True)
    p.add_argument("--lang", choices=["ko", "en"])
    p.set_defaults(fn=cmd_report)
    p = sub.add_parser("init-spec", help="데이터로 spec 짐작")
    p.add_argument("data", nargs="+")
    p.add_argument("--out", required=True)
    p.add_argument("--kind", default="auto")
    p.add_argument("--map", action="append", default=[])
    p.add_argument("--opt", action="append", default=[])
    p.set_defaults(fn=cmd_init_spec)
    p = sub.add_parser("demo", help="예제 셋으로 화면 만들기")
    p.add_argument("--out", default="demo")
    p.add_argument("--examples", help="examples 폴더(기본: 저장소의 examples/)")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--lang", choices=["ko", "en"])
    p.add_argument("--no-recommend", action="store_true")
    p.set_defaults(fn=cmd_demo)
    p = sub.add_parser("pipeline", help="설정 파일 하나로 분석·비교·내보내기")
    p.add_argument("config")
    p.set_defaults(fn=cmd_pipeline)
    return ap


def main(argv=None) -> int:
    a = parser().parse_args(argv)
    try:
        return int(a.fn(a) or 0)
    except (ImportError, ValueError, FileNotFoundError, RuntimeError, KeyError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
