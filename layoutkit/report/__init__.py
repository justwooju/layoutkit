"""분석 결과(result dict, docs/ARCHITECTURE.md 3절) → 한 장 HTML 대시보드 · (선택) PNG 그림.

    from layoutkit.report import render, export_png
    render(result, "report.html")              # 말은 lang → result.spec.lang → ko
    export_png(result, "fig/")                 # matplotlib 있을 때만 — 없으면 [] 를 돌려준다

파이썬 표준 라이브러리만 쓴다(PNG 만 matplotlib 선택).
"""
from __future__ import annotations

import json
from pathlib import Path

from .html import build

__all__ = ["render", "export_png", "build", "load_result"]


def _lang(result: dict, lang: str | None) -> str:
    lg = lang or (result.get("spec") or {}).get("lang") or "ko"
    return lg if lg in ("ko", "en") else "ko"


def load_result(path) -> dict:
    """저장한 결과 JSON(--json) 읽기."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def render(result: dict, out_html, lang: str | None = None) -> Path:
    """result → HTML 파일. 만든 파일 경로를 돌려준다."""
    if isinstance(result, (str, Path)):
        result = load_result(result)
    out = Path(out_html)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(result, _lang(result, lang)), encoding="utf-8")
    return out


def export_png(result: dict, out_dir, lang: str | None = None) -> list[Path]:
    """주요 패널 PNG(지도·칸 지도·지름길·옮긴 거리·칸 번호·수집 기록). matplotlib 이 없으면 건너뛰고 []."""
    try:
        from . import figures
    except ImportError:
        return []
    if isinstance(result, (str, Path)):
        result = load_result(result)
    return figures.export(result, Path(out_dir), _lang(result, lang))
