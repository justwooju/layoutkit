"""SVG 그리기 도구 — 순수 문자열 생성(외부 의존 없음).

축·눈금·격자·화살표·육각형·빗금·막대, 그리고 말풍선용 data-* 속성. 화면(html.py)과 시험이 이것만 쓴다.
좌표는 모두 SVG 사용자 단위(px). 데이터 → px 변환은 Scale 이 한다.
"""
from __future__ import annotations

import math
from html import escape as _esc

INK = "#1A1A1A"
INK2 = "#4A4F57"        # 보조 글자
MUTED = "#80868F"       # 흐린 글자
GRID = "#E6E8EC"
AXIS = "#9AA0A8"


def esc(s) -> str:
    """속성·글자 안전하게."""
    return _esc("" if s is None else str(s), quote=True)


def num(v, nd=1) -> str:
    """좌표 숫자를 짧게(파일 크기) — 소수 nd 자리, 뒤 0 제거."""
    s = f"{float(v):.{nd}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def attrs(a: dict | None = None, data: dict | None = None) -> str:
    """{"class": "x", "stroke_width": 2} → ' class="x" stroke-width="2"'. data={"i": 3} → ' data-i="3"'."""
    out = []
    for k, v in (a or {}).items():
        if v is None or v is False:
            continue
        k = k.rstrip("_").replace("_", "-")
        out.append(f' {k}="{esc(num(v) if isinstance(v, float) else v)}"')
    for k, v in (data or {}).items():
        if v is None:
            continue
        out.append(f' data-{k}="{esc(v)}"')
    return "".join(out)


def el(tag: str, a: dict | None = None, inner: str | None = None, data: dict | None = None) -> str:
    if inner is None:
        return f"<{tag}{attrs(a, data)}/>"
    return f"<{tag}{attrs(a, data)}>{inner}</{tag}>"


# ------------------------------------------------------------------ 눈금
def nice_step(span: float, n: int = 5) -> float:
    if span <= 0 or not math.isfinite(span):
        return 1.0
    raw = span / max(1, n)
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    if hi < lo:
        lo, hi = hi, lo
    st = nice_step(hi - lo, n)
    t0 = math.ceil(lo / st - 1e-9) * st
    out = []
    v = t0
    while v <= hi + 1e-9 * max(1.0, abs(hi)):
        out.append(round(v, 10))
        v += st
    return out


class Scale:
    """선형 눈금: 데이터 [d0, d1] → px [r0, r1]. r0 > r1 이면 뒤집힌 축(예: y 위로, +x 왼쪽)."""

    def __init__(self, d0, d1, r0, r1):
        self.d0, self.d1, self.r0, self.r1 = float(d0), float(d1), float(r0), float(r1)
        if self.d1 == self.d0:
            self.d1 = self.d0 + 1.0

    def __call__(self, v) -> float:
        return self.r0 + (float(v) - self.d0) * (self.r1 - self.r0) / (self.d1 - self.d0)

    def inv(self, p) -> float:
        return self.d0 + (float(p) - self.r0) * (self.d1 - self.d0) / (self.r1 - self.r0)

    @property
    def k(self) -> float:
        """px / 데이터 단위(부호 있음)."""
        return (self.r1 - self.r0) / (self.d1 - self.d0)

    def ticks(self, n=5):
        lo, hi = min(self.d0, self.d1), max(self.d0, self.d1)
        return ticks(lo, hi, n)


def fmt_tick(v: float, pct: bool = False) -> str:
    if pct:
        return f"{v * 100:.0f}%"
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v))}".replace("-", "−")
    return f"{v:g}".replace("-", "−")


def axis_x(sx: Scale, y: float, tick_vals=None, label: str | None = None, pct=False, grid_to: float | None = None,
           fmt=None) -> str:
    """아래 축: 눈금 글자 + (선택) 세로 격자(grid_to 까지)."""
    tv = sx.ticks() if tick_vals is None else tick_vals
    p = []
    x0, x1 = sorted((sx.r0, sx.r1))
    for v in tv:
        x = sx(v)
        if x < x0 - 0.5 or x > x1 + 0.5:
            continue
        if grid_to is not None:
            p.append(el("line", {"x1": x, "x2": x, "y1": grid_to, "y2": y, "class": "grid"}))
        p.append(el("text", {"x": x, "y": y + 14, "class": "tick", "text-anchor": "middle"}, esc(fmt(v) if fmt else fmt_tick(v, pct))))
    p.append(el("line", {"x1": x0, "x2": x1, "y1": y, "y2": y, "class": "axis"}))
    if label:
        p.append(el("text", {"x": (x0 + x1) / 2, "y": y + 31, "class": "alabel", "text-anchor": "middle"}, esc(label)))
    return "".join(p)


def axis_y(sy: Scale, x: float, tick_vals=None, label: str | None = None, pct=False, grid_to: float | None = None,
           fmt=None, label_dx: float = 40) -> str:
    """왼쪽 축: 눈금 글자 + (선택) 가로 격자(grid_to 까지)."""
    tv = sy.ticks() if tick_vals is None else tick_vals
    p = []
    y0, y1 = sorted((sy.r0, sy.r1))
    for v in tv:
        y = sy(v)
        if y < y0 - 0.5 or y > y1 + 0.5:
            continue
        if grid_to is not None:
            p.append(el("line", {"x1": x, "x2": grid_to, "y1": y, "y2": y, "class": "grid"}))
        p.append(el("text", {"x": x - 6, "y": y + 4, "class": "tick", "text-anchor": "end"}, esc(fmt(v) if fmt else fmt_tick(v, pct))))
    if label:
        cy = (y0 + y1) / 2
        p.append(el("text", {"x": x - label_dx, "y": cy, "class": "alabel", "text-anchor": "middle",
                             "transform": f"rotate(-90 {num(x - label_dx)} {num(cy)})"}, esc(label)))
    return "".join(p)


# ------------------------------------------------------------------ 모양
def hex_points(cx: float, cy: float, r: float, orient: str = "pointy") -> str:
    """육각형 꼭짓점 문자열. pointy = 꼭짓점이 위(줄이 가로), flat = 변이 위."""
    a0 = 90.0 if orient == "pointy" else 0.0
    pts = []
    for k in range(6):
        a = math.radians(a0 + 60 * k)
        pts.append(f"{num(cx + r * math.cos(a))},{num(cy - r * math.sin(a))}")
    return " ".join(pts)


def hexagon(cx, cy, r, orient="pointy", a: dict | None = None, data: dict | None = None) -> str:
    a = dict(a or {})
    a["points"] = hex_points(cx, cy, r, orient)
    return el("polygon", a, None, data)


def shrink(x1, y1, x2, y2, s1=0.0, s2=0.0):
    """선분 양 끝을 s1, s2 만큼 줄인다(점·고리와 겹치지 않게)."""
    d = math.hypot(x2 - x1, y2 - y1)
    if d < 1e-6 or d <= s1 + s2 + 1:
        return x1, y1, x2, y2
    ux, uy = (x2 - x1) / d, (y2 - y1) / d
    return x1 + ux * s1, y1 + uy * s1, x2 - ux * s2, y2 - uy * s2


def arrow_marker(mid: str, color: str, size: float = 6.0) -> str:
    """화살촉 marker 정의(<defs> 안에)."""
    return (f'<marker id="{esc(mid)}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="{num(size)}" markerHeight="{num(size)}" '
            f'orient="auto-start-reverse" markerUnits="userSpaceOnUse"><path d="M0,1 L10,5 L0,9 z" fill="{esc(color)}"/></marker>')


def hatch_pattern(pid: str, color: str = "#B5BBC3", gap: float = 5.0, width: float = 1.0) -> str:
    """45° 빗금 pattern 정의(<defs> 안에)."""
    return (f'<pattern id="{esc(pid)}" patternUnits="userSpaceOnUse" width="{num(gap)}" height="{num(gap)}" '
            f'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="{num(gap)}" stroke="{esc(color)}" '
            f'stroke-width="{num(width)}"/></pattern>')


def bar_v(x, y_base, w, h, r=3.0, a: dict | None = None, data: dict | None = None) -> str:
    """세로 막대 — 위만 둥글게(바닥은 각지게). h 는 위로 양수."""
    if h <= 0:
        return ""
    r = min(r, w / 2, h)
    y = y_base - h
    d = (f"M{num(x)},{num(y_base)} V{num(y + r)} Q{num(x)},{num(y)} {num(x + r)},{num(y)} H{num(x + w - r)} "
         f"Q{num(x + w)},{num(y)} {num(x + w)},{num(y + r)} V{num(y_base)} Z")
    aa = dict(a or {})
    aa["d"] = d
    return el("path", aa, None, data)


def bar_h(x_base, y, w, h, r=3.0, a: dict | None = None, data: dict | None = None) -> str:
    """가로 막대 — 오른쪽 끝만 둥글게. w 는 오른쪽으로 양수."""
    if w <= 0:
        return ""
    r = min(r, h / 2, w)
    x = x_base + w
    d = (f"M{num(x_base)},{num(y)} H{num(x - r)} Q{num(x)},{num(y)} {num(x)},{num(y + r)} V{num(y + h - r)} "
         f"Q{num(x)},{num(y + h)} {num(x - r)},{num(y + h)} H{num(x_base)} Z")
    aa = dict(a or {})
    aa["d"] = d
    return el("path", aa, None, data)


def rot_rect(cx, cy, length, width, yaw_deg, to_px) -> str:
    """세계 좌표의 돌린 사각형(가운데·길이·폭·yaw) → px 다각형 points. to_px(x, y) → (px, py)."""
    u = (math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg)))
    v = (-u[1], u[0])
    pts = []
    for a, b in ((1, 1), (1, -1), (-1, -1), (-1, 1)):
        x = cx + a * length / 2 * u[0] + b * width / 2 * v[0]
        y = cy + a * length / 2 * u[1] + b * width / 2 * v[1]
        px, py = to_px(x, y)
        pts.append(f"{num(px)},{num(py)}")
    return " ".join(pts)


def marker_shape(kind: str, x: float, y: float, r: float, a: dict | None = None, data: dict | None = None) -> str:
    """결과 모양: circle(성공) · cross(실패) · tri(불확실) · ring(모름) · square · diamond."""
    a = dict(a or {})
    if kind == "circle":
        return el("circle", {**a, "cx": x, "cy": y, "r": r}, None, data)
    if kind == "ring":
        return el("circle", {**a, "cx": x, "cy": y, "r": r * 0.85}, None, data)
    if kind == "square":
        return el("rect", {**a, "x": x - r * 0.85, "y": y - r * 0.85, "width": r * 1.7, "height": r * 1.7}, None, data)
    if kind == "tri":
        h = r * 1.15
        pts = f"{num(x)},{num(y - h)} {num(x + h)},{num(y + h * 0.8)} {num(x - h)},{num(y + h * 0.8)}"
        return el("polygon", {**a, "points": pts}, None, data)
    if kind == "diamond":
        pts = f"{num(x)},{num(y - r * 1.2)} {num(x + r * 1.2)},{num(y)} {num(x)},{num(y + r * 1.2)} {num(x - r * 1.2)},{num(y)}"
        return el("polygon", {**a, "points": pts}, None, data)
    if kind == "cross":
        s = r * 0.95
        d = (f"M{num(x - s)},{num(y - s)} L{num(x + s)},{num(y + s)} M{num(x - s)},{num(y + s)} L{num(x + s)},{num(y - s)}")
        return el("path", {**a, "d": d}, None, data)
    return el("circle", {**a, "cx": x, "cy": y, "r": r}, None, data)


def status_icon(status: str, size: float = 14.0) -> str:
    """상태 모양 아이콘(색만으로 뜻을 전하지 않게): 좋음 ✓ 원 · 주의 ! 세모 · 나쁨 ✕ 팔각 · 정보 i 원."""
    s = size
    col = {"good": "#009E73", "warn": "#E69F00", "bad": "#D55E00", "info": "#0072B2"}.get(status, "#7F7F7F")
    c = s / 2
    if status == "good":
        body = (f'<circle cx="{num(c)}" cy="{num(c)}" r="{num(c)}" fill="{col}"/>'
                f'<path d="M{num(s * .27)},{num(s * .52)} L{num(s * .44)},{num(s * .69)} L{num(s * .74)},{num(s * .34)}" '
                f'fill="none" stroke="#fff" stroke-width="{num(s * .14)}" stroke-linecap="round" stroke-linejoin="round"/>')
    elif status == "warn":
        body = (f'<path d="M{num(c)},{num(s * .04)} L{num(s * .98)},{num(s * .94)} L{num(s * .02)},{num(s * .94)} Z" fill="{col}" '
                f'stroke="{col}" stroke-linejoin="round" stroke-width="{num(s * .08)}"/>'
                f'<path d="M{num(c)},{num(s * .36)} V{num(s * .62)}" stroke="#1A1A1A" stroke-width="{num(s * .13)}" stroke-linecap="round"/>'
                f'<circle cx="{num(c)}" cy="{num(s * .78)}" r="{num(s * .07)}" fill="#1A1A1A"/>')
    elif status == "bad":
        pts = " ".join(f"{num(c + c * math.cos(math.radians(22.5 + 45 * k)))},{num(c + c * math.sin(math.radians(22.5 + 45 * k)))}"
                       for k in range(8))
        body = (f'<polygon points="{pts}" fill="{col}"/>'
                f'<path d="M{num(s * .33)},{num(s * .33)} L{num(s * .67)},{num(s * .67)} M{num(s * .67)},{num(s * .33)} '
                f'L{num(s * .33)},{num(s * .67)}" stroke="#fff" stroke-width="{num(s * .14)}" stroke-linecap="round"/>')
    else:
        body = (f'<circle cx="{num(c)}" cy="{num(c)}" r="{num(c)}" fill="{col}"/>'
                f'<circle cx="{num(c)}" cy="{num(s * .28)}" r="{num(s * .08)}" fill="#fff"/>'
                f'<path d="M{num(c)},{num(s * .45)} V{num(s * .76)}" stroke="#fff" stroke-width="{num(s * .14)}" stroke-linecap="round"/>')
    return (f'<svg class="sicon" width="{num(s)}" height="{num(s)}" viewBox="0 0 {num(s)} {num(s)}" aria-hidden="true">{body}</svg>')


def open_svg(w: float, h: float, cls: str = "", label: str = "", extra: dict | None = None) -> str:
    a = {"viewBox": f"0 0 {num(w)} {num(h)}", "class": cls or None, "role": "img", "aria-label": label or None,
         "xmlns": "http://www.w3.org/2000/svg", "preserveAspectRatio": "xMidYMid meet"}
    a.update(extra or {})
    return f"<svg{attrs(a)}>"
