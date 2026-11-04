"""화면(report) 시험 — fixture(result_rack.json)로 HTML 을 만들고 Playwright 로 열어 본다.

    python3 tests/test_report.py          # pytest 없이도 돈다(pytest 가 있으면 pytest tests/test_report.py)

확인: JS 오류 0 · 외부 요청 0 · 주요 요소 · 켜기/끄기·표 누르기·말풍선 · 추천 없을 때 상자 글 · 큰 데이터 파일 크기.
스크린샷: fig/dashboard_ko.png · fig/dashboard_en.png (1280 폭, 전체 페이지, deviceScaleFactor 1).
"""
from __future__ import annotations

import copy
import json
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from layoutkit.report import export_png, render     # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "result_rack.json"
FIG = ROOT / "fig"


def _result() -> dict:
    if not FIX.exists():
        sys.path.insert(0, str(FIX.parent))
        import make_fixture                         # noqa: E402
        make_fixture.main()
    return json.loads(FIX.read_text(encoding="utf-8"))


def _open(html: Path, shot: Path | None = None, width: int = 1280, actions=None) -> dict:
    """페이지를 열어 콘솔 오류·외부 요청·요소 수를 모은다. actions(page) 로 상호작용 확인."""
    from playwright.sync_api import sync_playwright
    out = {"errors": [], "external": []}
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": width, "height": 900}, device_scale_factor=1)
        pg.on("console", lambda m: out["errors"].append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: out["errors"].append(str(e)))
        pg.on("request", lambda r: out["external"].append(r.url) if not r.url.startswith(("file:", "data:", "about:")) else None)
        pg.goto(html.resolve().as_uri())
        pg.wait_for_timeout(200)
        q = {"cards": ".cards .card", "next": "section.next", "map": "#svg-map", "cellmaps": "svg.cellmap", "scatter": "svg.scatter",
             "side": "table.side", "cdf": "svg.cdf", "strata": "svg.strata", "compare": ".cmp .crow", "timeline": "svg.timeline",
             "runs": "svg.runsday", "rows": "#eps tbody tr", "rec": "#svg-map .rec"}
        out["count"] = {k: pg.locator(v).count() for k, v in q.items()}
        out["overflow"] = pg.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
        if shot:
            shot.parent.mkdir(parents=True, exist_ok=True)
            pg.screenshot(path=str(shot), full_page=True)
        if actions:
            out["actions"] = actions(pg)
        b.close()
    return out


def _interact(pg) -> dict:
    """켜기/끄기 → 표 줄 수, 표 줄 누르기 → 선택 표시, 지도 점 위 → 말풍선."""
    r = {}
    n0 = pg.locator("#eps tbody tr").count()
    pg.locator(".dschip input[data-d='0']").uncheck()
    r["rows_after_off"] = pg.locator("#eps tbody tr").count()
    r["map_hidden"] = pg.evaluate("getComputedStyle(document.querySelector('#svg-map .d0')).display")
    pg.locator(".dschip input[data-d='0']").check()
    r["rows_back"] = pg.locator("#eps tbody tr").count() == n0
    pg.locator("#eps tbody tr").nth(3).click()
    pg.wait_for_timeout(500)
    r["selchip"] = pg.locator(".selchip").is_visible()
    r["sel_clones"] = pg.locator("#svg-map .sel-layer > *").count()
    # 지도 첫 집는 점 위로(표 누르기 뒤 부드러운 스크롤이 끝난 다음)
    pg.wait_for_timeout(600)
    pg.locator("#svg-map").scroll_into_view_if_needed()
    box = pg.evaluate("""() => { const c = document.querySelector('#svg-map .sdot circle'); const b = c.getBoundingClientRect();
                             return [b.x + b.width / 2, b.y + b.height / 2]; }""")
    pg.mouse.move(box[0] + 4, box[1] + 4)
    pg.mouse.move(box[0], box[1])
    pg.wait_for_timeout(100)
    r["tip"] = pg.locator("#tip").is_visible() and "mm" in pg.locator("#tip").inner_text()
    pg.select_option("#f-oc", "success")
    r["filter_ok"] = pg.locator("#eps tbody tr").count() > 0
    pg.click("[data-mapmode=dots]")
    r["dots_mode"] = pg.evaluate("getComputedStyle(document.querySelector('#svg-map .arw')).display") == "none"
    return r


def test_dashboard_ko_en():
    res = _result()
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for lang in ("ko", "en"):
            html = render(res, td / f"report_{lang}.html", lang=lang)
            o = _open(html, FIG / f"dashboard_{lang}.png", actions=_interact if lang == "ko" else None)
            assert o["errors"] == [], o["errors"]
            assert o["external"] == [], o["external"]
            c = o["count"]
            assert c["cards"] == 5 and c["next"] == 1 and c["map"] == 1 and c["cellmaps"] == 2, c
            assert c["scatter"] == 2 and c["side"] == 3 and c["cdf"] == 1 and c["strata"] == 2, c
            assert c["compare"] >= 5 and c["timeline"] == 1 and c["runs"] == 1 and c["rec"] == 3, c
            assert c["rows"] == len(res["episodes"]), c
            assert not o["overflow"], "가로 스크롤이 생겼다"
            if lang == "ko":
                a = o["actions"]
                n1 = sum(1 for e in res["episodes"] if e["dataset"] == res["datasets"][1]["name"])
                assert a["rows_after_off"] == n1 and a["map_hidden"] == "none" and a["rows_back"], a
                assert a["selchip"] and a["sel_clones"] > 0 and a["tip"] and a["filter_ok"] and a["dots_mode"], a


def test_no_recommend_narrow():
    """추천 없음 → 상자에 안내 글. 좁은 화면(390 px)에서 가로로 넘치지 않는다."""
    res = copy.deepcopy(_result())
    res["recommend"] = None
    res["runs"] = None
    with tempfile.TemporaryDirectory() as td:
        html = render(res, Path(td) / "r.html")
        txt = html.read_text(encoding="utf-8")
        assert "추천 없음" in txt
        o = _open(html, width=390)
        assert o["errors"] == [] and o["count"]["rec"] == 0 and o["count"]["runs"] == 0, o
        assert not o["overflow"], "좁은 화면에서 가로 스크롤"


def test_big_file_size():
    """에피소드 3000 개여도 HTML 이 수 MB 안."""
    res = copy.deepcopy(_result())
    rng = random.Random(1)
    base = res["episodes"]
    eps = []
    for k in range(3000):
        e = copy.deepcopy(base[k % len(base)])
        e["id"] = f"{e['dataset']}/syn_{k:05d}"
        for role in ("start", "goal"):
            e[role]["x"] += rng.uniform(-20, 20)
            e[role]["y"] += rng.uniform(-15, 15)
        eps.append(e)
    res["episodes"] = eps
    res["timeline"] = []
    with tempfile.TemporaryDirectory() as td:
        html = render(res, Path(td) / "big.html")
        mb = html.stat().st_size / 1e6
        assert mb < 4.0, f"{mb:.1f} MB"
        o = _open(html)
        assert o["errors"] == [], o["errors"]


def test_real_analyze():
    """실제 analyze(+ recommend) 결과(받침 예제 v1+v2+수집 기록)로도 화면이 오류 없이 선다 — 모듈이 없으면 건너뜀."""
    try:
        import layoutkit as lk
        from layoutkit.analyze import analyze
    except ImportError:
        return
    ex = ROOT / "examples" / "rack_fr5"
    ds = [lk.load_dataset(str(ex / "data" / "v1_tags.json"), name="fr5_v1", weight=0.5),
          lk.load_dataset(str(ex / "data" / "v2_layouts_20261103.json"), name="fr5_v2")]
    spec = str(ex / "spec.json")
    res = analyze(ds, spec, runs=str(ex / "data" / "runs_20261031_20261104.csv"))
    try:
        from layoutkit.recommend import recommend
        rec = recommend(ds, spec, result=res)
        res["recommend"] = res.get("recommend") or rec
    except ImportError:
        pass
    with tempfile.TemporaryDirectory() as td:
        html = render(res, Path(td) / "real.html")
        o = _open(html)
        assert o["errors"] == [] and o["external"] == [], o
        c = o["count"]
        assert c["cards"] >= 4 and c["cellmaps"] == 2 and c["side"] == 3 and c["runs"] == 1, c
        assert c["rows"] == len(res["episodes"]), c
        if res.get("recommend"):
            assert c["rec"] == min(3, len(res["recommend"]["options"])), c
            txt = html.read_text(encoding="utf-8")
            for code in {w for o_ in res["recommend"]["options"] for w in o_.get("why_codes") or []}:
                assert f">{code}<" not in txt, f"이유 코드 {code} 의 글이 사전에 없다"


def test_export_png():
    try:
        import matplotlib                      # noqa: F401
    except ImportError:
        return                                 # 선택 의존 — 없으면 건너뜀
    with tempfile.TemporaryDirectory() as td:
        paths = export_png(_result(), td)
        names = {p.name for p in paths}
        assert {"map.png", "cells.png", "shortcut.png", "transfer.png", "strata.png", "runs.png"} <= names, names


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
