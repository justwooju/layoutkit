"""layoutkit — 로봇 조작 시연 데이터셋의 배치(어디서 집어 어디에 놓았나) 분석·다음 배치 추천·한 장 HTML 화면.

    import layoutkit as lk
    v1 = lk.load_dataset("examples/rack_fr5/data/v1_tags.json", name="fr5_v1", weight=0.5)
    v2 = lk.load_dataset("examples/rack_fr5/data/v2_layouts_20261103.json", name="fr5_v2")
    res = lk.analyze([v1, v2], "examples/rack_fr5/spec.json")
    res["recommend"] = lk.recommend([v1, v2], "examples/rack_fr5/spec.json", result=res, n=3)   # recommend 패키지
    lk.render(res, "report.html")                                                               # report 패키지

필수 의존은 numpy 뿐. recommend·report 는 따로 된 하위 패키지다 — 없으면 그 함수만 ImportError 로 알린다.
"""
from __future__ import annotations

import importlib.util

__version__ = "0.1.0"

from .adapters import load_dataset, load_runs  # noqa: E402
from .analyze import analyze  # noqa: E402
from .data import Dataset, episode, merge  # noqa: E402
from .spec import load as load_spec  # noqa: E402

# 하위 패키지 layoutkit.recommend 와 함수 recommend 가 이름이 같다. 하위 패키지를 처음 불러올 때 파이썬이 이 패키지의 recommend 를
# 그 모듈로 덮으므로, 여기서 먼저 불러 두고(있으면) 아래에서 함수로 다시 정한다. 하위 패키지는 from layoutkit.recommend import … 로 쓴다.
_SUB_ERR = {}
for _pkg in ("recommend", "report"):
    try:
        if importlib.util.find_spec(f"{__name__}.{_pkg}") is not None:
            importlib.import_module(f"{__name__}.{_pkg}")
    except Exception as _e:                                          # 하위 패키지가 깨져도 분석은 된다
        _SUB_ERR[_pkg] = f"{type(_e).__name__}: {_e}"

__all__ = ["__version__", "load_dataset", "load_runs", "analyze", "recommend", "render", "export_png", "load_spec",
           "Dataset", "episode", "merge", "have_recommend", "have_report"]


def have_recommend() -> bool:
    return _has_func("recommend", "recommend")


def have_report() -> bool:
    return _has_func("report", "render")


def _module(pkg):
    import sys
    name = f"{__name__}.{pkg}"
    if name in sys.modules:
        return sys.modules[name]
    try:
        if importlib.util.find_spec(name) is None:
            return None
        return importlib.import_module(name)
    except Exception as e:
        _SUB_ERR[pkg] = f"{type(e).__name__}: {e}"
        return None
    finally:
        globals()["recommend"] = _recommend                          # 하위 패키지를 불러와도 함수 이름을 지킨다


def _has_func(pkg, fn) -> bool:
    mod = _module(pkg)
    return mod is not None and callable(getattr(mod, fn, None))


def _sub(pkg, fn):
    mod = _module(pkg)
    if mod is None:
        why = _SUB_ERR.get(pkg)
        raise ImportError(f"layoutkit.{pkg} 패키지가 " + (f"깨져 있다({why})" if why else "없다") +
                          f" — {fn}() 를 쓰려면 layoutkit/{pkg}/ 가 필요하다(분석만은 analyze() 로 된다)")
    f = getattr(mod, fn, None)
    if not callable(f):
        raise ImportError(f"layoutkit.{pkg} 에 {fn}() 가 아직 없다(만드는 중이거나 빠짐)")
    return f


def recommend(datasets, spec, result=None, n=3, **kw):
    """다음 배치 추천 → options(dict). layoutkit.recommend 가 있어야 한다.
    result 를 주면 추천이 채운 놓을 수 있는 칸(coverage.*.reach)으로 N_min·신호등 카드를 다시 계산해 둔다."""
    out = _sub("recommend", "recommend")(datasets, spec, result=result, n=n, **kw)
    if isinstance(result, dict) and result.get("coverage") and result.get("spec"):
        from .analyze import coverage as _cv
        if result.get("recommend") is None:
            result["recommend"] = out
        _cv.apply_reach(result)
    return out


_recommend = recommend


def render(result, out_html, lang=None, **kw):
    """result → HTML 한 장. layoutkit.report 가 있어야 한다."""
    lang = lang or ((result or {}).get("spec") or {}).get("lang") or "ko"
    return _sub("report", "render")(result, out_html, lang, **kw)


def export_png(result, out_dir, **kw):
    """result → PNG 그림들(matplotlib). layoutkit.report 가 있어야 한다."""
    return _sub("report", "export_png")(result, out_dir, **kw)
