"""주요 패널 PNG 내보내기(선택 — matplotlib 필요). 화면(html.py)과 같은 색·방향·말을 쓴다.

한국어 글꼴(Noto Sans CJK KR · Malgun Gothic · Apple SD Gothic Neo · NanumGothic 등)을 못 찾으면 영어로 그린다.
"""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                      # noqa: E402
from matplotlib import font_manager                  # noqa: E402
import matplotlib.patches                            # noqa: E402
import matplotlib.ticker                             # noqa: E402
from matplotlib.patches import Polygon, Rectangle    # noqa: E402

from . import i18n                                   # noqa: E402
from .html import (AREA_EDGE, AREA_FILL, OUTCOME, REC_INK, RUN_ORDER, SEQ, Ctx, _bin_edges, _feat, _fixture_decl,  # noqa: E402
                   _fixture_size,
                   _num, _orient, _pt, _side_screen, run_counts)

KO_FONTS = ("Noto Sans CJK KR", "Noto Sans KR", "Apple SD Gothic Neo", "Malgun Gothic", "NanumGothic", "Noto Sans CJK JP")


def _setup(lang: str) -> str:
    """글꼴 고르기. 한국어 글꼴이 없으면 'en' 으로 바꿔 돌려준다."""
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": "#9AA0A8", "axes.linewidth": 0.8, "axes.labelcolor": "#4A4F57",
                         "xtick.color": "#80868F", "ytick.color": "#80868F", "axes.titlesize": 10, "axes.titleweight": "bold",
                         "axes.spines.top": False, "axes.spines.right": False, "savefig.dpi": 160, "axes.unicode_minus": False})
    if lang != "ko":
        return lang
    names = {f.name for f in font_manager.fontManager.ttflist}
    for f in KO_FONTS:
        if f in names:
            plt.rcParams["font.family"] = [f, "DejaVu Sans"]
            return "ko"
    return "en"


def _hex(ax, cx, cy, r, orient, **kw):
    a0 = 90.0 if orient == "pointy" else 0.0
    pts = [(cx + r * math.cos(math.radians(a0 + 60 * k)), cy + r * math.sin(math.radians(a0 + 60 * k))) for k in range(6)]
    ax.add_patch(Polygon(pts, closed=True, **kw))


def _xlim(c: Ctx, ax, lo, hi):
    ax.set_xlim(hi, lo) if c.xl else ax.set_xlim(lo, hi)


def fig_map(c: Ctx, out: Path) -> Path:
    x0, x1, y0, y1 = c.area
    fig, ax = plt.subplots(figsize=(9.6, 4.4))
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=AREA_FILL, ec=AREA_EDGE, lw=0.8, zorder=0))
    if c.cov and c.cov.get("centers"):
        h = float(c.cov.get("h") or 30)
        for cx_, cy_ in c.cov["centers"]:
            _hex(ax, cx_, cy_, h * 0.97, _orient(c), fill=False, ec="#D9DDE2", lw=0.5, zorder=1)
    xs, ys = [x0, x1], [y0, y1]
    for d in c.ds:
        for e in c.eps:
            if c.ds_of(e) != d["k"]:
                continue
            s, g = _pt(e.get("start")), _pt(e.get("goal"))
            if s and g:
                ax.annotate("", xy=g, xytext=s, arrowprops=dict(arrowstyle="-|>", color=d["color"], lw=0.7, alpha=0.55,
                                                                mutation_scale=6, shrinkA=2, shrinkB=3), zorder=2)
            for p in (s, g):
                if p:
                    xs.append(p[0]); ys.append(p[1])
        S_ = [_pt(e.get("start")) for e in c.eps if c.ds_of(e) == d["k"] and _pt(e.get("start"))]
        G_ = [_pt(e.get("goal")) for e in c.eps if c.ds_of(e) == d["k"] and _pt(e.get("goal"))]
        if S_:
            ax.scatter(*zip(*S_), s=12, color=d["color"], lw=0.4, edgecolor="white", zorder=3, label=f"{d['name']} ●→○")
        if G_:
            ax.scatter(*zip(*G_), s=18, facecolor="white", edgecolor=d["color"], lw=1.0, zorder=3)
    for hd in (c.rec or {}).get("holdout") or []:                  # 시험 배치: 회색 ×
        for q in (_pt(hd.get("start")), _pt(hd.get("goal"))):
            if q:
                ax.plot(*q, "x", color="#7F7F7F", ms=4.5, mew=1.2, zorder=4)
    for o in ((c.rec or {}).get("options") or [])[:3]:
        s, g = _pt(o.get("start")), _pt(o.get("goal"))
        if not s:
            continue
        for f in o.get("fixtures") or []:
            fp = _pt(f)
            if fp:
                L, W = _fixture_size(c, f.get("name"))
                yaw = math.radians(float(f.get("yaw") or 0))
                u, v = (math.cos(yaw), math.sin(yaw)), (-math.sin(yaw), math.cos(yaw))
                pts = [(fp[0] + a * L / 2 * u[0] + b * W / 2 * v[0], fp[1] + a * L / 2 * u[1] + b * W / 2 * v[1])
                       for a, b in ((1, 1), (1, -1), (-1, -1), (-1, 1))]
                ax.add_patch(Polygon(pts, closed=True, fill=False, ec=REC_INK, lw=0.9, ls=(0, (4, 2)), alpha=0.75, zorder=4))
                dcl = _fixture_decl(c, f.get("name"), f.get("type"))
                n_s, pitch = int(dcl.get("slots") or 0), _num(dcl.get("pitch_mm"))
                for j in range(n_s if pitch else 0):                # 칸 구멍(긴 축 = yaw 방향)
                    o_ = (j - (n_s - 1) / 2) * pitch
                    ax.add_patch(matplotlib.patches.Circle((fp[0] + o_ * u[0], fp[1] + o_ * u[1]),
                                                           _num(dcl.get("hole_r_mm")) or pitch * 0.4, fill=False, ec=REC_INK,
                                                           lw=0.6, ls=(0, (2, 2)), alpha=0.6, zorder=4))
        if g:
            ax.annotate("", xy=g, xytext=s, arrowprops=dict(arrowstyle="-|>", color=REC_INK, lw=1.3, ls=(0, (4, 2)),
                                                            mutation_scale=9, shrinkA=4, shrinkB=5), zorder=5)
            ax.plot(*g, "o", mfc="white", mec=REC_INK, ms=8, mew=1.3, zorder=5)
        ax.plot(*s, "o", color=REC_INK, ms=6, zorder=6)
        ax.annotate(str(o.get("label") or ""), s, xytext=(7, 7), textcoords="offset points", fontsize=8, fontweight="bold",
                    color="white", bbox=dict(boxstyle="circle,pad=0.2", fc=REC_INK, ec="none"), zorder=7)
    pad = 18
    _xlim(c, ax, min(xs) - pad, max(xs) + pad)
    ax.set_ylim(min(ys) - pad, max(ys) + pad)
    ax.set_aspect("equal")
    ax.set_xlabel(c.x_label()); ax.set_ylabel(c.y_label())
    ax.set_title(c.t("map.title"), loc="left")
    ax.legend(loc="upper left", bbox_to_anchor=(1.0, 1.0), fontsize=7.5, frameon=False)
    return _save(fig, out / "map.png")


def fig_cells(c: Ctx, out: Path):
    cov = c.cov
    if not cov or not cov.get("centers"):
        return None
    C, h, orient = cov["centers"], float(cov.get("h") or 30), _orient(c)
    x0, x1, y0, y1 = c.area
    tots = {}
    for role in ("start", "goal"):
        rr = cov.get(role) or {}
        cbd = rr.get("count_by_ds") or {}
        tot = [0] * len(C)
        if cbd:
            for arr in cbd.values():
                for j, v in enumerate(arr):
                    tot[j] += int(round(_num(v) or 0))
        else:
            tot = [int(math.ceil(_num(v) or 0)) for v in (rr.get("count") or [0] * len(C))]
        tots[role] = (tot, rr.get("reach"))
    edges = _bin_edges(max(max(t[0]) for t in tots.values()) or 1)
    fig, axs = plt.subplots(1, 2, figsize=(9.6, 2.8))
    for ax, role in zip(axs, ("start", "goal")):
        tot, reach = tots[role]
        for j, (cx_, cy_) in enumerate(C):
            rch = True if reach is None else bool(reach[j])
            n = tot[j]
            if n > 0:
                b = max(q for q in range(len(edges)) if n >= edges[q])
                _hex(ax, cx_, cy_, h * 0.95, orient, fc=SEQ[b], ec="white", lw=0.8)
                ax.text(cx_, cy_, str(n), ha="center", va="center", fontsize=6.5, color="white" if b >= 3 else "#1A1A1A")
            elif rch:
                _hex(ax, cx_, cy_, h * 0.9, orient, fc="white", ec="#E69F00", lw=1.8)
            else:
                _hex(ax, cx_, cy_, h * 0.95, orient, fc="#F7F8F9", ec="#D5D9DE", lw=0.5)
            if not rch:
                _hex(ax, cx_, cy_, h * 0.95, orient, fill=False, ec="#B3B9C1", lw=0, hatch="////")
        filled = sum(1 for j in range(len(C)) if tot[j] > 0 and (reach is None or reach[j]))
        if reach is not None:
            nr = sum(1 for v in reach if v)
            ttl = c.t(f"cells.{role}", reach=nr, filled=filled, empty=nr - filled)
        else:
            ttl = c.t(f"cells.{role}_all", n=len(C), filled=sum(1 for v in tot if v))
        _xlim(c, ax, x0 - h, x1 + h)
        ax.set_ylim(y0 - h, y1 + h); ax.set_aspect("equal"); ax.axis("off")
        ax.set_title(ttl, fontsize=8.5)
    return _save(fig, out / "cells.png")


def fig_shortcut(c: Ctx, out: Path):
    cp = c.r.get("coupling") or {}
    pairs, side = cp.get("pairs") or [], cp.get("side")
    if not pairs:
        return None
    pr = pairs[0]
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(9.6, 3.6), gridspec_kw={"width_ratios": [1.2, 1]})
    for d in c.ds:
        P = [(_num(_feat(e, pr["a"])), _num(_feat(e, pr["b"]))) for e in c.eps if c.ds_of(e) == d["k"]]
        P = [p for p in P if p[0] is not None and p[1] is not None]
        if P:
            rho = (pr.get("rho_by_ds") or {}).get(d["name"])
            lab = f"{d['name']}  ρ = {rho:+.2f}" if rho is not None else d["name"]
            ax.scatter(*zip(*P), s=14, color=d["color"], alpha=0.8, lw=0.3, edgecolor="white", label=lab)
    if c.xl and pr["a"].endswith(".x"):
        ax.invert_xaxis()
    if side and _num(side.get("split")) is not None:
        ax.axvline(float(side["split"]), color="#80868F", ls=(0, (4, 3)), lw=0.8)
        ax.axhline(float(side["split"]), color="#80868F", ls=(0, (4, 3)), lw=0.8)
    ax.set_xlabel(f"{i18n.feature(c.lang, pr['a'])} [mm]"); ax.set_ylabel(f"{i18n.feature(c.lang, pr['b'])} [mm]")
    ax.legend(fontsize=7.5, frameon=False)
    ax.grid(color="#EEF0F3")
    ax.set_title(c.t("sc.scatter", a=i18n.feature(c.lang, pr["a"]), b=i18n.feature(c.lang, pr["b"])), loc="left")
    bx.axis("off")
    if side:
        M, order = _side_screen(c, side)
        names = [c.t("pos." + o) for o in order]
        for i in range(2):
            n = sum(M[i])
            for j in range(2):
                sh = M[i][j] / n if n else 0
                bx.add_patch(Rectangle((0.3 + j * 0.35, 0.55 - i * 0.38), 0.33, 0.36, transform=bx.transAxes,
                                       fc=(0, 114 / 255, 178 / 255, 0.06 + 0.55 * sh), ec="#D5465E" if (n >= 5 and sh >= .9) else "none",
                                       lw=2))
                bx.text(0.3 + j * 0.35 + 0.165, 0.55 - i * 0.38 + 0.18, f"{M[i][j]}", transform=bx.transAxes, ha="center",
                        va="center", fontsize=16, fontweight="bold", color="white" if sh > .62 else "#1A1A1A")
            bx.text(0.28, 0.55 - i * 0.38 + 0.18, c.t("sc.row", side=names[i]), transform=bx.transAxes, ha="right", va="center", fontsize=8)
        for j in range(2):
            bx.text(0.3 + j * 0.35 + 0.165, 0.95, c.t("sc.col", side=names[j]), transform=bx.transAxes, ha="center", fontsize=8)
        acc = _num((cp.get("predict") or {}).get("knn_acc")) or _num(side.get("acc"))
        if acc is not None:
            st = "good" if acc <= c.tg["predict_good"] else "warn" if acc <= c.tg["predict_bad"] else "bad"
            bx.text(0.0, 0.04, c.t("sc." + st, acc=f"{acc * 100:.0f}%"), transform=bx.transAxes, fontsize=8, wrap=True)
    return _save(fig, out / "shortcut.png")


def fig_transfer(c: Ctx, out: Path):
    near = float((c.r.get("transfer") or {}).get("near_mm") or c.sp.get("near_mm") or 100)
    fig, ax = plt.subplots(figsize=(4.8, 3.2))
    mx = 0
    for d in c.ds:
        v = sorted(_num(e.get("move_mm")) for e in c.eps if c.ds_of(e) == d["k"] and _num(e.get("move_mm")) is not None)
        if not v:
            continue
        mx = max(mx, v[-1])
        n = len(v)
        ns = sum(1 for m in v if m <= near) / n
        ax.step([0] + v, [0] + [(j + 1) / n for j in range(n)], where="post", color=d["color"], lw=1.8,
                label=c.t("tr.legend", name=d["name"], near=f"{ns * 100:.0f}%", med=f"{v[n // 2]:.0f}"))
    ax.axvspan(0, near, color="#EAF1F8", lw=0, zorder=0)
    ax.plot([0, near], [c.tg["near_share"]] * 2, color="#1A1A1A", ls=(0, (4, 3)), lw=1.2)
    ax.set_xlim(0, max(mx * 1.05, near * 1.2)); ax.set_ylim(0, 1.02)
    ax.set_xlabel(c.t("tr.x")); ax.set_ylabel(c.t("tr.y"))
    ax.legend(fontsize=7, frameon=False, loc="lower right")
    ax.grid(color="#EEF0F3")
    ax.set_title(c.t("tr.title"), loc="left", fontsize=9)
    return _save(fig, out / "transfer.png")


def fig_strata(c: Ctx, out: Path):
    strata = c.r.get("strata") or []
    if not strata:
        return None
    fig, axs = plt.subplots(1, len(strata), figsize=(2.6 * len(strata) + 0.6, 2.8), squeeze=False)
    for ax, s in zip(axs[0], strata):
        rows = s.get("rows") or []
        vals = [r.get("value") for r in rows]
        nb = len(c.ds)
        w = 0.8 / max(1, nb)
        for kk, d in enumerate(c.ds):
            L = [e for e in c.eps if c.ds_of(e) == d["k"] and (e.get("discrete") or {}).get(s["name"]) is not None]
            if not L:
                continue
            sh = [sum(1 for e in L if e["discrete"][s["name"]] == v) / len(L) for v in vals]
            ax.bar([j + (kk - (nb - 1) / 2) * w for j in range(len(vals))], sh, width=w * 0.9, color=d["color"], label=d["name"])
        for j, r in enumerate(rows):
            tv = _num(r.get("target"))
            if tv is not None:
                ax.plot([j - 0.45, j + 0.45], [tv, tv], color="#1A1A1A", ls=(0, (4, 3)), lw=1)
        ax.set_xticks(range(len(vals)), [str(v) for v in vals])
        ax.set_xlabel(i18n.name(c.lang, s["name"]))
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
        ax.grid(axis="y", color="#EEF0F3")
    axs[0][0].legend(fontsize=7, frameon=False)
    fig.suptitle(c.t("st.title"), x=0.02, ha="left", fontsize=9, fontweight="bold")
    return _save(fig, out / "strata.png")


def fig_runs(c: Ctx, out: Path):
    runs = c.r.get("runs")
    if not runs or not runs.get("by_day"):
        return None
    days = runs["by_day"]
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(9.6, 3.0), gridspec_kw={"width_ratios": [1, 1.3], "wspace": 0.9})
    cn = [run_counts(d) for d in days]
    cats = [k for k in RUN_ORDER if any(x.get(k) for x in cn)] + sorted({k for x in cn for k in x if k not in RUN_ORDER})
    bottom = [0] * len(days)
    for k in cats:
        v = [x.get(k, 0) for x in cn]
        ax.bar(range(len(days)), v, bottom=bottom, color=OUTCOME.get(k, OUTCOME["other"])[0], width=0.62, label=c.t("oc." + k))
        bottom = [b + x for b, x in zip(bottom, v)]
    for j, d in enumerate(days):
        ax.text(j, bottom[j] + 1, f"{d.get('kept', '')}/{bottom[j]}", ha="center", fontsize=7)
    ax.set_xticks(range(len(days)), [str(d.get("day"))[5:].replace("-", "/") for d in days])
    ax.set_ylim(0, max(max(bottom), 1) * 1.25)
    ax.legend(fontsize=6.5, frameon=False, loc="upper right")
    ax.set_title(c.t("runs.title"), loc="left", fontsize=9)
    rs = runs.get("reasons") or []
    if isinstance(rs, dict):
        rs = [{"code": k, "n": v} for k, v in rs.items()]
    rs = sorted([r for r in rs if r.get("n")], key=lambda r: r.get("n", 0))
    if rs:
        omap = {"goal_state_unknown": "unsure", "not_recorded": "norec", "aborted": "abort"}
        for j, r in enumerate(rs):
            bv = r.get("by_verdict") or {r.get("outcome") or omap.get(r.get("code"), "fail"): r["n"]}
            x0 = 0
            for k, v in sorted(bv.items(), key=lambda kv: RUN_ORDER.index(kv[0]) if kv[0] in RUN_ORDER else 99):
                bx.barh(j, v, left=x0, color=OUTCOME.get(k, OUTCOME["other"])[0], height=0.62)
                x0 += v
            bx.text(x0 + 0.3, j, str(r["n"]), va="center", fontsize=7)
        bx.set_yticks(range(len(rs)), [i18n.REASON.get(c.lang, {}).get(r.get("code"), r.get("code")) for r in rs], fontsize=7.5)
        bx.set_title(c.t("runs.reasons", n=sum(r["n"] for r in rs)), loc="left", fontsize=9)
    return _save(fig, out / "runs.png")


def _save(fig, path: Path) -> Path:
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def export(result: dict, out_dir: Path, lang: str = "ko") -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    lang = _setup(lang)
    c = Ctx(result, lang)
    paths = []
    for f in (fig_map, fig_cells, fig_shortcut, fig_transfer, fig_strata, fig_runs):
        p = f(c, out_dir)
        if p:
            paths.append(p)
    return paths
