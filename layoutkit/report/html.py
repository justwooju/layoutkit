"""한 장 HTML 조립 — 신호등 카드·다음에 할 일·지도·칸 지도·지름길·옮긴 거리·이산 칸·비교·시간표·에피소드 표.

입력은 분석 결과 dict(docs/ARCHITECTURE.md 3절) 하나. 외부 요청 없음: 인라인 SVG + 인라인 CSS + 바닐라 JS.
그림 좌표는 파이썬(svg.py)이 정하고, JS 는 말풍선·켜기/끄기·강조·표 정렬/거르기만 한다.
"""
from __future__ import annotations

import itertools
import json
import math
from bisect import bisect_right

from . import i18n
from . import svg as S
from .svg import esc, num

# 색 — Okabe–Ito. 데이터셋 순서 고정(파랑부터), 상태 색은 따로.
DS_ORDER = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00"]
STATUS = {"good": "#009E73", "warn": "#E69F00", "bad": "#D55E00", "info": "#0072B2"}
OUTCOME = {"success": ("#009E73", "circle"), "fail": ("#D55E00", "cross"), "unsure": ("#E69F00", "tri"),
           "norec": ("#BDBDBD", "square"), "abort": ("#7F7F7F", "diamond"), "other": ("#9AA0A8", "square"),
           None: ("#9AA0A8", "ring")}
SEQ = ["#D6ECF9", "#A6D4F1", "#62B5E5", "#2A8CC6", "#0B5F98"]     # 셈 진하기: 하늘 → 파랑 한 색 단계
AREA_FILL, AREA_EDGE = "#F1F3F5", "#C5CAD1"
REC_INK = "#1A1A1A"
TARGET_DEFAULTS = {"rho_max": 0.3, "rho_bad": 0.5, "near_share": 0.25, "near_warn": 0.10, "predict_good": 0.65,
                   "predict_bad": 0.80, "coverage_good": 0.80, "coverage_warn": 0.50, "strata_dev_good": 0.10,
                   "strata_dev_bad": 0.25, "dup_mm": 12.0}
THUMB_MAX = 40_000            # 썸네일 data URI 하나 최대 글자 수(파일 크기 지키기)
THUMB_TOTAL = 3_000_000
_IDS = itertools.count(1)


class _Safe(dict):
    def __missing__(self, k):
        return "?"


def _fmt(tpl: str, **kw) -> str:
    try:
        return tpl.format_map(_Safe(kw))
    except (ValueError, IndexError):
        return tpl


def pct(v, nd=0) -> str:
    if v is None:
        return "—"
    return f"{float(v) * 100:.{nd}f}%"


def signed(v, nd=2) -> str:
    if v is None:
        return "—"
    return f"{float(v):+.{nd}f}".replace("-", "−")


def _num(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _pt(p):
    if not isinstance(p, dict):
        return None
    x, y = _num(p.get("x")), _num(p.get("y"))
    return (x, y) if x is not None and y is not None else None


# ================================================================== 문맥
class Ctx:
    """결과 + 말 + 공통 계산(데이터셋 색, 에피소드 번호, 지도 방향)."""

    def __init__(self, result: dict, lang: str):
        self.r = result
        self.lang = lang
        self.sp = result.get("spec") or {}
        self.tg = dict(TARGET_DEFAULTS)
        self.tg.update((self.sp.get("targets") or {}))
        fr = self.sp.get("frame") or {}
        self.xl = bool(fr.get("x_left_positive", False))
        self.eps = list(result.get("episodes") or [])
        # 데이터셋 — 분석이 정한 색(datasets[].color: spec.dataset_colors > meta.color > Okabe–Ito 순서), 없으면 결과 순서대로
        dss = list(result.get("datasets") or [])
        seen = [d.get("name") for d in dss]
        for e in self.eps:
            if e.get("dataset") not in seen:
                seen.append(e.get("dataset"))
                dss.append({"name": e.get("dataset"), "n": None, "weight": 1.0})
        self.ds = []
        for k, d in enumerate(dss):
            n_eps = sum(1 for e in self.eps if e.get("dataset") == d.get("name"))
            self.ds.append({"k": k, "name": str(d.get("name")), "color": d.get("color") or DS_ORDER[k % len(DS_ORDER)],
                            "n": d.get("n") if d.get("n") is not None else n_eps, "weight": d.get("weight"),
                            "n_success": d.get("n_success")})
        self.dk = {d["name"]: d["k"] for d in self.ds}
        a = result.get("area") or self.sp.get("area")
        if not a:
            xs = [p[0] for e in self.eps for p in (_pt(e.get("start")), _pt(e.get("goal"))) if p]
            ys = [p[1] for e in self.eps for p in (_pt(e.get("start")), _pt(e.get("goal"))) if p]
            a = {"x": [min(xs or [-100]) - 30, max(xs or [100]) + 30], "y": [min(ys or [-100]) - 30, max(ys or [100]) + 30]}
        self.area = (float(a["x"][0]), float(a["x"][1]), float(a["y"][0]), float(a["y"][1]))
        self.cov = result.get("coverage") or None
        self.rec = result.get("recommend") or None
        self.units = self.sp.get("units") or "mm"

    def t(self, key, **kw):
        return i18n.t(self.lang, key, **kw)

    def x_label(self):
        fr = self.sp.get("frame") or {}
        if self.lang == (self.sp.get("lang") or "ko") and fr.get("x_label"):
            return fr["x_label"]
        return "x [mm]  (+x = robot's left)" if (self.xl and self.lang == "en") else self.t("frame.x")

    def y_label(self):
        fr = self.sp.get("frame") or {}
        if self.lang == (self.sp.get("lang") or "ko") and fr.get("y_label"):
            return fr["y_label"]
        return self.t("frame.y")

    def ds_of(self, e):
        return self.dk.get(e.get("dataset"), 0)

    def pos_words(self, x, y):
        """목표 영역 안 위치 → '지도 왼쪽 위' 같은 말(화면 기준)."""
        x0, x1, y0, y1 = self.area
        fx = (x - x0) / max(1e-9, x1 - x0)
        if self.xl:
            fx = 1 - fx
        fy = 1 - (y - y0) / max(1e-9, y1 - y0)          # 위 = y 큰 쪽
        h = "left" if fx < 1 / 3 else "right" if fx > 2 / 3 else "center"
        v = "top" if fy < 1 / 3 else "bottom" if fy > 2 / 3 else "center"
        hw, vw = self.t("pos." + h), self.t("pos." + v)
        if h == "center" and v == "center":
            p = hw
        elif v == "center":
            p = hw
        elif h == "center":
            p = f"{hw} {vw}" if self.lang == "ko" else f"{vw} {hw}"
        else:
            p = f"{hw} {vw}" if self.lang == "ko" else f"{vw} {hw}"
        return self.t("pos.map", p=p)


# ================================================================== 머리줄
def sec_header(c: Ctx) -> str:
    title = c.sp.get("title") or c.sp.get("task") or "layoutkit"
    chips = []
    for d in c.ds:
        w = d.get("weight")
        wtxt = f" · {c.t('weight')} {w:g}" if isinstance(w, (int, float)) else ""
        chips.append(f'<label class="dschip" title="{esc(c.t("toggle_hint"))}"><input type="checkbox" checked data-d="{d["k"]}">'
                     f'<span class="sw" style="background:{d["color"]}"></span><b>{esc(d["name"])}</b>'
                     f'<span class="muted"> · {d["n"]}{esc(c.t("episodes_unit"))}{esc(wtxt)}</span></label>')
    created = str(c.r.get("created") or "").replace("T", " ")
    return (f'<header class="top"><div class="ttl"><h1>{esc(title)}</h1>'
            f'<div class="meta">{esc(c.t("made"))} {esc(created)} · layoutkit {esc(c.r.get("version") or "")}'
            f' <button class="btn small" id="btn-print" type="button">{esc(c.t("print"))}</button></div></div>'
            f'<div class="dsrow"><span class="muted lbl">{esc(c.t("datasets"))}</span>{"".join(chips)}</div></header>')


# ================================================================== 신호등 카드
def _gauge_cfg(c: Ctx, card):
    tg, cid = c.tg, card.get("id")
    v = _num(card.get("value"))
    if v is None:
        return None
    if cid == "coupling":
        return {"lo": 0, "hi": 1, "target": tg["rho_max"], "lower": True, "pct": False, "tlabel": f"≤ {tg['rho_max']:.2f}"}
    if cid == "predict":
        ch = _num((card.get("args") or {}).get("chance")) or 0.5
        return {"lo": 0, "hi": 1, "target": tg["predict_good"], "lower": True, "pct": True, "chance": ch,
                "tlabel": f"≤ {pct(tg['predict_good'])}"}
    if cid == "near":
        return {"lo": 0, "hi": max(0.5, v * 1.15), "target": tg["near_share"], "lower": False, "pct": True,
                "tlabel": f"≥ {pct(tg['near_share'])}"}
    if cid == "coverage":
        return {"lo": 0, "hi": 1, "target": tg["coverage_good"], "lower": False, "pct": True, "tlabel": f"≥ {pct(tg['coverage_good'])}"}
    if cid == "strata":
        return {"lo": 0, "hi": max(0.4, v * 1.15), "target": tg["strata_dev_good"], "lower": True, "pct": True,
                "tlabel": f"≤ {tg['strata_dev_good'] * 100:.0f}%p"}
    if 0 <= v <= 1 and card.get("status") != "info":
        tv = None
        m = str(card.get("target") or "").replace("≤", "").replace("≥", "").strip()
        tv = _num(m)
        return {"lo": 0, "hi": 1, "target": tv, "lower": "≤" in str(card.get("target") or ""), "pct": False,
                "tlabel": str(card.get("target") or "")}
    return None


def _gauge_svg(c: Ctx, cfg, v, status, W=180) -> str:
    H = 40
    sx = S.Scale(cfg["lo"], cfg["hi"], 2, W - 2)
    col = STATUS.get(status, "#7F7F7F")
    vv = min(max(v, cfg["lo"]), cfg["hi"])
    p = [S.open_svg(W, H, "gauge", "")]
    p.append(S.el("rect", {"x": 2, "y": 8, "width": W - 4, "height": 9, "rx": 4.5, "fill": "#E9ECF0"}))
    wv = max(0.0, sx(vv) - 2)
    if wv > 0:
        p.append(S.el("rect", {"x": 2, "y": 8, "width": max(wv, 3), "height": 9, "rx": 4.5, "fill": col}))
    # 글자 폭 어림(11px 글꼴: 한글 ≈ 11, 그 밖 ≈ 6.3) — 계기 밖으로 잘리지 않게 붙는 쪽을 고른다
    def tw(s):
        return sum(11.0 if ord(ch) > 0x2E80 else 6.3 for ch in s)

    def place(x, s, prefer):
        w = tw(s)
        if prefer == "middle" and x - w / 2 >= 0 and x + w / 2 <= W:
            return x, "middle"
        if prefer in ("start", "middle") and x + 3 + w <= W:
            return x + 3, "start"
        if x - 3 - w >= 0:
            return x - 3, "end"
        return (W, "end") if x > W / 2 else (0, "start")
    tlab = f"{c.t('target')} {cfg['tlabel']}" if cfg.get("target") is not None else ""
    if cfg.get("chance") is not None:
        xc = sx(cfg["chance"])
        p.append(S.el("line", {"x1": xc, "x2": xc, "y1": 4, "y2": 21, "stroke": "#80868F", "stroke-width": 1.2,
                               "stroke-dasharray": "2 2"}))
        clab = f"{c.t('chance')} {pct(cfg['chance'])}"
        near_t = cfg.get("target") is not None and abs(sx(cfg["target"]) - xc) < tw(tlab) / 2 + tw(clab) / 2 + 6
        x_, a_ = place(xc, clab, "end" if (near_t and sx(cfg["target"]) >= xc) else "middle")
        if near_t and sx(cfg["target"]) >= xc:
            x_, a_ = xc - 3, "end"
        p.append(S.el("text", {"x": x_, "y": 33, "class": "gt", "text-anchor": a_}, esc(clab)))
    if cfg.get("target") is not None:
        xt = sx(cfg["target"])
        p.append(S.el("line", {"x1": xt, "x2": xt, "y1": 3, "y2": 22, "stroke": "#1A1A1A", "stroke-width": 2}))
        near_c = cfg.get("chance") is not None and xt >= sx(cfg["chance"])
        x_, a_ = place(xt, tlab, "start" if near_c else "middle")
        if near_c and a_ == "end" and x_ < xt:        # 우연 글자와 겹치지 않게 오른쪽 끝에 붙인다
            x_, a_ = W, "end"
        p.append(S.el("text", {"x": x_, "y": 33, "class": "gt gtb", "text-anchor": a_}, esc(tlab)))
    p.append("</svg>")
    return "".join(p)


def _card_value(c: Ctx, card):
    """(큰 값, 단위, 보조 줄)."""
    cid, v, a = card.get("id"), _num(card.get("value")), card.get("args") or {}
    if cid == "coupling":
        pair = str(a.get("pair") or "")
        sub = " ↔ ".join(i18n.feature(c.lang, s) for s in pair.split("→")) if pair else ""
        return (f"{v:.2f}" if v is not None else "—"), "|ρ|", sub
    if cid in ("predict", "near"):
        return pct(v), "", ""
    if cid == "coverage":
        sub = ""
        if a.get("reach_start") is not None:
            sub = (f"{c.t('feat.start')} {a.get('filled_start')}/{a.get('reach_start')} · "
                   f"{c.t('feat.goal')} {a.get('filled_goal')}/{a.get('reach_goal')}")
        return pct(v), "", sub
    if cid == "strata":
        return (f"{v * 100:.0f}" if v is not None else "—"), c.t("unit.pp"), i18n.name(c.lang, a.get("name"))
    if cid == "dups":
        return str(a.get("n", "—")), c.t("unit.pairs"), ""
    if cid == "n_min":
        return str(card.get("value")), c.t("unit.eps"), ""
    if v is None:
        return str(card.get("value") or "—"), str(card.get("unit") or ""), ""
    return (f"{v:.2f}" if abs(v) < 10 else f"{v:.0f}"), str(card.get("unit") or ""), ""


def card_texts(c: Ctx, card):
    """(제목, 왜, 할 일) — code 사전에 없으면 상태별 일반 문장."""
    cid, st = card.get("id"), card.get("status") or "info"
    a = dict(card.get("args") or {})
    title = c.t("card." + str(cid)) if ("card." + str(cid)) in i18n.T["ko"] else str(cid)
    val, unit, _ = _card_value(c, card)
    cfg = _gauge_cfg(c, card)
    target = cfg["tlabel"] if cfg else (card.get("target") or "")
    kw = {"title": title, "value": f"{val}{(' ' + unit) if unit else ''}", "target": target}
    if cid == "coupling":
        pr = str(a.get("pair") or "start.x→goal.x").split("→")
        kw.update(a=i18n.feature(c.lang, pr[0]), b=i18n.feature(c.lang, pr[-1]),
                  rho=signed(a.get("rho", card.get("value"))))
    elif cid == "predict":
        kw.update(acc=pct(a.get("acc", card.get("value"))), chance=pct(_num(a.get("chance")) or 0.5))
    elif cid == "near":
        kw.update(near_mm=f"{_num(a.get('near_mm')) or c.sp.get('near_mm') or 100:.0f}", share=pct(a.get("share", card.get("value"))))
    elif cid == "coverage":
        kw.update({k: a.get(k, "?") for k in ("filled_start", "reach_start", "filled_goal", "reach_goal")})
        if a.get("reach_start") is None and c.cov:
            kw.update(filled_start=c.cov.get("filled_start"), reach_start=c.cov.get("n_cells"),
                      filled_goal=c.cov.get("filled_goal"), reach_goal=c.cov.get("n_cells"))
    elif cid == "strata":
        sh = _num(a.get("share"))
        ts = _num(a.get("target_share", a.get("target")))
        dr = a.get("dir") if a.get("dir") in ("less", "more") else ("less" if (sh or 0) > (ts or 0) else "more")
        kw.update(name=i18n.name(c.lang, a.get("name")), share=pct(sh), target_share=pct(ts),
                  dir=i18n.CARD.get(c.lang, i18n.CARD["ko"])["dir." + dr])
        kw["value"] = a.get("value", "?")
        if card.get("code") == "strata_ok":
            kw["value"] = f"{(_num(card.get('value')) or 0) * 100:.0f}%p"
    elif cid == "dups":
        kw.update(n=a.get("n", "?"), dup_mm=f"{_num(a.get('dup_mm')) or c.tg['dup_mm']:.0f}")
    elif cid == "n_min":
        kw.update(n_min=a.get("n_min", card.get("value")), coupon=f"{_num(a.get('coupon')) or 0:.0f}")
        rc = (c.rec or {}).get("cells") or {}
        if rc.get("n_min") is not None:            # 추천이 센 (자리, 방향) 칸 기준 — 추천이 실제로 채우려는 칸
            kw["n_min"] = rc["n_min"]
            card = dict(card, code="n_min_rec")
    for k, v in a.items():
        kw.setdefault(k, v)
    tbl = i18n.CARD.get(c.lang, i18n.CARD["ko"])
    pair = tbl.get(str(card.get("code"))) or tbl.get("_" + st) or tbl["_info"]
    return title, _fmt(pair[0], **kw), _fmt(pair[1], **kw)


def sec_cards(c: Ctx) -> str:
    cards = [cd for cd in (c.r.get("cards") or []) if (cd.get("status") or "info") != "info"]
    if not cards:
        return ""
    out = ['<section class="cards" aria-label="cards">']
    for cd in cards:
        st = cd.get("status") or "info"
        title, why, todo = card_texts(c, cd)
        val, unit, sub = _card_value(c, cd)
        cfg = _gauge_cfg(c, cd)
        g = _gauge_svg(c, cfg, _num(cd.get("value")), st) if cfg else ""
        out.append(
            f'<article class="card {esc(st)}" data-card="{esc(cd.get("id"))}">'
            f'<div class="chead"><span class="cname">{esc(title)}</span>'
            f'<span class="badge {esc(st)}">{S.status_icon(st, 14)}{esc(c.t("status." + st))}</span></div>'
            f'<div class="val">{esc(val)}<small>{esc(unit)}</small></div>'
            f'<div class="vsub">{esc(sub) if sub else "&nbsp;"}</div>{g}'
            f'<p class="why">{esc(why)}</p><p class="todo"><b>{esc(c.t("todo"))}</b> {esc(todo)}</p></article>')
    out.append("</section>")
    return "".join(out)


# ================================================================== 다음에 할 일
def rec_sentence(c: Ctx, o) -> str:
    lay = c.sp.get("layout") or {}
    items = lay.get("items") or []
    st_item = next((it.get("name") for it in items if it.get("role") == "start"), None)
    gl_item = next((it.get("name") for it in items if it.get("role") == "goal"), None)
    item = i18n.name(c.lang, st_item or "object")
    goal = i18n.name(c.lang, gl_item or "target")
    s, g = _pt(o.get("start")), _pt(o.get("goal"))
    if not s:
        return esc(o.get("label") or "")
    empty = ""
    k = (o.get("cells") or {}).get("start")
    if c.cov and isinstance(k, int) and 0 <= k < len(c.cov.get("start", {}).get("count") or []):
        if not (c.cov["start"]["count"][k] or 0):     # 칸 지도(자리 칸)와 같은 기준
            empty = c.t("rec.empty")
    elif (o.get("cells") or {}).get("start_count") is not None and not _num(o["cells"]["start_count"]):
        empty = c.t("rec.empty")
    xy = f"x {s[0]:.0f}, y {s[1]:.0f}"
    ko = c.lang == "ko"
    p1 = c.t("rec.put", item_obj=i18n.ko_obj(item, "eul") if ko else item, item=item, pos=c.pos_words(*s), empty=empty, xy=xy)
    disc = o.get("discrete") or {}
    goal_top = i18n.ko_obj(goal, "eun") if ko else goal
    fixs = lay.get("fixtures") or []
    if lay.get("kind") == "fixtures" and disc.get("goal_slot") is not None:
        fx = i18n.name(c.lang, (fixs[0].get("name") if fixs else "rack"))
        if disc.get("same_fixture"):
            p2 = c.t("rec.goal_same", goal_top=goal_top, fixture=fx, slot=disc.get("goal_slot"))
        else:
            p2 = c.t("rec.goal_other", goal_top=goal_top, fixture=fx, slot=disc.get("goal_slot"),
                     pos=c.pos_words(*g) if g else "")
    elif g:
        p2 = c.t("rec.goal_point", goal_top=goal_top, pos=c.pos_words(*g), xy=f"x {g[0]:.0f}, y {g[1]:.0f}")
    else:
        p2 = ""
    mv = _num(o.get("move_mm"))
    if mv is None and g:
        mv = math.dist(s, g)
    tail = [c.t("rec.move", mm=f"{mv:.0f}")] if mv is not None else []
    wa = o.get("why_args") or {}
    whys = []
    for w in o.get("why_codes") or []:
        txt = i18n.WHY.get(c.lang, {}).get(w, w)
        if w == "lowers_coupling" and isinstance(wa.get("rho"), (list, tuple)) and len(wa["rho"]) == 2:
            txt += f" ({abs(_num(wa['rho'][0]) or 0):.2f} → {abs(_num(wa['rho'][1]) or 0):.2f})"
        whys.append(txt)
    head = f"{p1}, {p2}" if p2 else p1
    return head, tail, whys


def sec_next(c: Ctx) -> str:
    infos = [cd for cd in (c.r.get("cards") or []) if (cd.get("status") or "info") == "info"]
    notes = []
    for cd in infos:
        title, why, todo = card_texts(c, cd)
        if c.lang == "en":
            todo = todo[:1].upper() + todo[1:]
        notes.append(f'<li>{S.status_icon("info", 13)}<span><b>{esc(title)}</b> — {esc(why)}. {esc(todo)}.</span></li>')
    opts = (c.rec or {}).get("options") or []
    body = []
    if opts:
        body.append('<ol class="recs">')
        for o in opts[:3]:
            r = rec_sentence(c, o)
            if isinstance(r, str):
                body.append(f"<li>{r}</li>")
                continue
            head, tail, whys = r
            tags = "".join(f'<span class="tag">{esc(w)}</span>' for w in whys)
            body.append(f'<li data-rec="{esc(o.get("label") or "")}"><span class="rlabel">{esc(o.get("label") or "")}</span><div><div class="rtxt">{esc(head)}'
                        f'{(" — " + esc(" · ".join(tail))) if tail else ""}</div><div class="rtags">{tags}</div></div></li>')
        body.append("</ol>")
        meta = []
        if c.rec.get("n_cand") is not None and c.rec.get("n_feasible") is not None:
            meta.append(c.t("next.feasible", n_cand=c.rec["n_cand"], n_feasible=c.rec["n_feasible"]))
        if c.rec.get("holdout"):
            meta.append(c.t("next.holdout", n=len(c.rec["holdout"])))
        if c.rec.get("skipped_checks"):
            meta.append(c.t("next.skipped", checks=", ".join(map(str, c.rec["skipped_checks"]))))
        meta.append(c.t("next.on_map"))
        body.append(f'<p class="muted small">{esc(" · ".join(meta))}</p>')
    else:
        body.append(f'<p class="norec">{esc(c.t("next.none"))}<br><code>{esc(c.t("next.cmd"))}</code></p>')
    nb = f'<div class="notes"><h3>{esc(c.t("next.notes"))}</h3><ul>{"".join(notes)}</ul></div>' if notes else ""
    return (f'<section class="next"><div class="nmain"><h2>{esc(c.t("next.title"))}</h2>{"".join(body)}</div>{nb}</section>')


# ================================================================== 패널 틀
def panel(pid: str, title: str, body: str, sub: str = "", tools: str = "", wide: bool = True) -> str:
    return (f'<details class="panel{"" if wide else " half"}" id="{esc(pid)}" open><summary><h2>{esc(title)}</h2>'
            f'{("<span class=sub>" + esc(sub) + "</span>") if sub else ""}<span class="chev" aria-hidden="true"></span></summary>'
            f'{("<div class=tools>" + tools + "</div>") if tools else ""}<div class="pbody">{body}</div></details>')


def legend(items) -> str:
    """items: [(swatch html, 글)]."""
    return '<div class="legend">' + "".join(f'<span class="li">{sw}<span>{esc(tx)}</span></span>' for sw, tx in items) + "</div>"


def sw_dot(color, hollow=False):
    if hollow:
        return f'<svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="4.2" fill="#fff" stroke="{color}" stroke-width="1.8"/></svg>'
    return f'<svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="4.5" fill="{color}"/></svg>'


def sw_box(fill, stroke=None, sw=1.0, pattern=False, dash=None):
    st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    if dash:
        st += f' stroke-dasharray="{dash}"'
    inner = ""
    if pattern:
        pid = f"lgh{next(_IDS)}"
        return (f'<svg width="16" height="12" aria-hidden="true"><defs>{S.hatch_pattern(pid, "#AEB4BC", 4, 1)}</defs>'
                f'<rect x="1" y="1" width="14" height="10" rx="2" fill="url(#{pid})"{st}/></svg>')
    return f'<svg width="16" height="12" aria-hidden="true"><rect x="1" y="1" width="14" height="10" rx="2" fill="{fill}"{st}/></svg>'


def sw_line(color, dash=None, w=2):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<svg width="22" height="12" aria-hidden="true"><line x1="1" y1="6" x2="21" y2="6" stroke="{color}" stroke-width="{w}"{d}/></svg>'


def sw_shape(kind, color):
    return (f'<svg width="12" height="12" aria-hidden="true">'
            f'{S.marker_shape(kind, 6, 6, 4.2, {"fill": "none" if kind in ("cross", "ring") else color, "stroke": color, "stroke-width": 1.8 if kind in ("cross", "ring") else 0})}</svg>')


# ================================================================== 지도
def _map_frame(c: Ctx, W=1040, max_h=430, ml=58, mr=16, mt=14, mb=48):
    x0, x1, y0, y1 = c.area
    xs, ys = [x0, x1], [y0, y1]
    for e in c.eps:
        for p in (_pt(e.get("start")), _pt(e.get("goal"))):
            if p:
                xs.append(p[0]); ys.append(p[1])
    for o in ((c.rec or {}).get("options") or [])[:3] + list((c.rec or {}).get("holdout") or []):
        for p in (_pt(o.get("start")), _pt(o.get("goal"))):
            if p:
                xs.append(p[0]); ys.append(p[1])
    for o in ((c.rec or {}).get("options") or [])[:3]:          # 집는·놓는 칸이 있는 고정물만 범위에(나머지는 잘라 그린다)
        d_ = o.get("discrete") or {}
        used = {(o.get("start") or {}).get("fixture"), (o.get("goal") or {}).get("fixture"), d_.get("start_fixture"),
                d_.get("goal_fixture")} - {None}
        for f in o.get("fixtures") or []:
            fp = _pt(f)
            if fp and f.get("name") in used:
                L, Wd = _fixture_size(c, f.get("name"), f.get("type"))
                yw = math.radians(float(f.get("yaw") or 0))
                u, v = (math.cos(yw), math.sin(yw)), (-math.sin(yw), math.cos(yw))
                for a_, b_ in ((1, 1), (1, -1), (-1, -1), (-1, 1)):        # 돌린 사각형 네 모서리
                    xs.append(fp[0] + a_ * L / 2 * u[0] + b_ * Wd / 2 * v[0])
                    ys.append(fp[1] + a_ * L / 2 * u[1] + b_ * Wd / 2 * v[1])
    pad = 18.0
    X0, X1, Y0, Y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
    k = min((W - ml - mr) / (X1 - X0), max_h / (Y1 - Y0))
    pw, ph = (X1 - X0) * k, (Y1 - Y0) * k
    Wt = ml + pw + mr
    sx = S.Scale(X1, X0, ml, ml + pw) if c.xl else S.Scale(X0, X1, ml, ml + pw)
    sy = S.Scale(Y0, Y1, mt + ph, mt)
    return sx, sy, Wt, mt + ph + mb, (X0, X1, Y0, Y1)


def _fixture_decl(c: Ctx, name, ftype=None) -> dict:
    """spec.layout.fixtures 에서 이 고정물의 선언(type 먼저, 없으면 이름 앞부분, 없으면 첫 것)."""
    fixs = (c.sp.get("layout") or {}).get("fixtures") or []
    for f in fixs:
        if ftype is not None and str(ftype) == str(f.get("name")):
            return f
    for f in fixs:
        if str(name or "").startswith(str(f.get("name"))):
            return f
    return fixs[0] if fixs else {}


def _fixture_size(c: Ctx, name, ftype=None):
    return _fixture_decl(c, name, ftype).get("size_mm") or [100, 40]


def _fixture_svg(c: Ctx, f, to_px, k_px) -> str:
    """고정물 하나: 윤곽(점선) + 칸 구멍(점선 원, 긴 축 = yaw 방향, 간격 pitch)."""
    fp = _pt(f)
    if not fp:
        return ""
    d = _fixture_decl(c, f.get("name"), f.get("type"))
    L, Wd = (d.get("size_mm") or [100, 40])[:2]
    yaw = float(f.get("yaw") or 0)
    out = [S.el("polygon", {"points": S.rot_rect(fp[0], fp[1], float(L), float(Wd), yaw, to_px), "class": "rfix", "fill": "none",
                            "stroke": REC_INK, "stroke-width": 1.1, "stroke-dasharray": "5 3"})]
    n, pitch = int(d.get("slots") or 0), _num(d.get("pitch_mm"))
    if n > 0 and pitch:
        u = (math.cos(math.radians(yaw)), math.sin(math.radians(yaw)))
        if d.get("slot_axis") == "width":
            u = (-u[1], u[0])
        r = (_num(d.get("hole_r_mm")) or min(pitch, float(Wd)) * 0.4) * abs(k_px)
        for j in range(n):
            o = (j - (n - 1) / 2) * pitch
            px, py = to_px(fp[0] + o * u[0], fp[1] + o * u[1])
            out.append(S.el("circle", {"cx": px, "cy": py, "r": r, "class": "rfix", "fill": "none", "stroke": REC_INK,
                                       "stroke-width": 0.8, "stroke-dasharray": "2 2"}))
    return "".join(out)


def sec_map(c: Ctx):
    sx, sy, W, H, bounds = _map_frame(c)
    x0, x1, y0, y1 = c.area
    p = [S.open_svg(W, H, "pts map", c.t("map.title"), {"style": f"max-width:{num(W)}px", "id": "svg-map"})]
    defs = [S.arrow_marker(f"ah{d['k']}", d["color"], 6) for d in c.ds]
    defs.append(S.arrow_marker("ahrec", REC_INK, 8))
    px0, px1 = sorted((sx.r0, sx.r1))
    defs.append(f'<clipPath id="mapclip"><rect x="{num(px0)}" y="{num(sy.r1)}" width="{num(px1 - px0)}" height="{num(sy.r0 - sy.r1)}"/></clipPath>')
    p.append("<defs>" + "".join(defs) + "</defs>")
    ax0, ax1 = sorted((sx(x0), sx(x1)))
    p.append(S.el("rect", {"x": ax0, "y": sy(y1), "width": ax1 - ax0, "height": sy(y0) - sy(y1), "fill": AREA_FILL,
                           "stroke": AREA_EDGE, "stroke-width": 1}))
    # 육각 칸 옅게
    if c.cov and c.cov.get("centers"):
        h = float(c.cov.get("h") or (c.sp.get("scales") or {}).get("h_xy_mm") or 30)
        orient = _orient(c)
        r = h * abs(sx.k)
        hx = "".join(f'<polygon points="{S.hex_points(sx(cx_), sy(cy_), r * 0.97, orient)}"/>' for cx_, cy_ in c.cov["centers"])
        p.append(f'<g class="hexbg" fill="none" stroke="#D9DDE2" stroke-width="0.8">{hx}</g>')
    # 축
    p.append(S.axis_x(sx, sy(bounds[2]) + 4, S.ticks(bounds[0], bounds[1], 8), c.x_label()))
    p.append(S.axis_y(sy, min(sx.r0, sx.r1) - 4, S.ticks(bounds[2], bounds[3], 4), c.y_label(), label_dx=44))
    # 화살표(데이터셋마다) → 점(데이터셋마다)
    arrows, dots = [], []
    for d in c.ds:
        la, ld = [], []
        for i, e in enumerate(c.eps):
            if c.ds_of(e) != d["k"]:
                continue
            s, g = _pt(e.get("start")), _pt(e.get("goal"))
            if s and g:
                a, b, cc, dd = S.shrink(sx(s[0]), sy(s[1]), sx(g[0]), sy(g[1]), 3.5, 5.5)
                la.append(f'<line data-i="{i}" x1="{num(a)}" y1="{num(b)}" x2="{num(cc)}" y2="{num(dd)}"/>')
            if s:
                ld.append(f'<circle data-i="{i}" cx="{num(sx(s[0]))}" cy="{num(sy(s[1]))}" r="3.3"/>')
        arrows.append(f'<g class="ds d{d["k"]} arw" stroke="{d["color"]}" stroke-width="1" stroke-opacity="0.55" '
                      f'marker-end="url(#ah{d["k"]})">{"".join(la)}</g>')
        dots.append(f'<g class="ds d{d["k"]} sdot" fill="{d["color"]}" stroke="#fff" stroke-width="0.8">{"".join(ld)}</g>')
        lg = []
        for i, e in enumerate(c.eps):
            g = _pt(e.get("goal"))
            if c.ds_of(e) == d["k"] and g:
                lg.append(f'<circle data-i="{i}" cx="{num(sx(g[0]))}" cy="{num(sy(g[1]))}" r="4.2"/>')
        dots.append(f'<g class="ds d{d["k"]} gdot" fill="#fff" fill-opacity="0.7" stroke="{d["color"]}" stroke-width="1.5">{"".join(lg)}</g>')
    p += arrows + dots
    # 시험 배치
    hold = (c.rec or {}).get("holdout") or []
    if hold:
        hp = []
        for j, hd in enumerate(hold):
            s, g = _pt(hd.get("start")), _pt(hd.get("goal"))
            tip = c.t("map.holdout_tip", id=hd.get("id") or j + 1)
            for q, role in ((s, "map.start"), (g, "map.goal")):
                if q:
                    hp.append(S.marker_shape("cross", sx(q[0]), sy(q[1]), 3.6, {"fill": "none", "stroke": "#7F7F7F", "stroke-width": 1.6},
                                             {"tip": f"{tip} · {c.t(role)}"}))
        p.append(f'<g class="hold">{"".join(hp)}</g>')
    # 추천(점선)
    for o in ((c.rec or {}).get("options") or [])[:3]:
        s, g = _pt(o.get("start")), _pt(o.get("goal"))
        if not s:
            continue
        r = rec_sentence(c, o)
        tip = r if isinstance(r, str) else f"{o.get('label')}: {r[0]}" + (f" — {' · '.join(r[1])}" if r[1] else "")
        q = [_fixture_svg(c, f, lambda x, y: (sx(x), sy(y)), sx.k) for f in o.get("fixtures") or []]
        if g:
            a, b, cc, dd = S.shrink(sx(s[0]), sy(s[1]), sx(g[0]), sy(g[1]), 6, 9)
            q.append(S.el("line", {"x1": a, "y1": b, "x2": cc, "y2": dd, "stroke": REC_INK, "stroke-width": 1.8,
                                   "stroke-dasharray": "5 3", "marker-end": "url(#ahrec)"}))
            q.append(S.el("circle", {"cx": sx(g[0]), "cy": sy(g[1]), "r": 7, "fill": "#fff", "fill-opacity": 0.6, "stroke": REC_INK,
                                     "stroke-width": 1.8, "stroke-dasharray": "3 2"}))
        q.append(S.el("circle", {"cx": sx(s[0]), "cy": sy(s[1]), "r": 5, "fill": REC_INK, "stroke": "#fff", "stroke-width": 1.5}))
        bx, by = sx(s[0]) + 12, sy(s[1]) - 13
        q.append(S.el("circle", {"cx": bx, "cy": by, "r": 9, "fill": REC_INK}))
        q.append(S.el("text", {"x": bx, "y": by + 4, "class": "rbadge", "text-anchor": "middle"}, esc(o.get("label") or "")))
        p.append(f'<g class="rec" data-rec="{esc(o.get("label") or "")}" data-tip="{esc(tip)}" clip-path="url(#mapclip)">{"".join(q)}</g>')
    p.append('<g class="sel-layer"></g><g class="hl-layer"></g></svg>')
    items = [(sw_dot("#4A4F57"), c.t("map.start")), (sw_dot("#4A4F57", True), c.t("map.goal")),
             (sw_box(AREA_FILL, AREA_EDGE), c.t("map.area"))]
    if c.cov and c.cov.get("centers"):
        items.append((sw_box("#fff", "#D9DDE2"), c.t("map.cells", h=float(c.cov.get("h") or 30))))
    if (c.rec or {}).get("options"):
        items.append((sw_line(REC_INK, "5 3"), c.t("map.rec")))
    if hold:
        items.append((f'<svg width="12" height="12">{S.marker_shape("cross", 6, 6, 4, {"fill": "none", "stroke": "#7F7F7F", "stroke-width": 1.6})}</svg>',
                      c.t("map.holdout")))
    for d in c.ds:
        items.append((sw_line(d["color"]), d["name"]))
    tools = (f'<div class="seg" role="group"><button type="button" class="btn on" data-mapmode="arrows">{esc(c.t("map.arrows"))}</button>'
             f'<button type="button" class="btn" data-mapmode="dots">{esc(c.t("map.dots"))}</button></div>'
             f'<span class="selchip" hidden><b>{esc(c.t("map.selected"))}</b> <span class="selid"></span>'
             f'<button type="button" class="btn small" id="sel-clear">{esc(c.t("map.clear"))}</button>'
             f'<button type="button" class="btn small" id="sel-back">{esc(c.t("map.back"))}</button></span>')
    body = f'<div class="plot">{"".join(p)}</div>{legend(items)}'
    mapt = {"sx": [sx.d0, sx.d1, sx.r0, sx.r1], "sy": [sy.d0, sy.d1, sy.r0, sy.r1]}
    return panel("p-map", c.t("map.title"), body, c.t("map.sub"), tools), mapt


def _orient(c: Ctx):
    o = (c.cov or {}).get("orient")
    if o in ("pointy", "flat"):
        return o
    x0, x1, y0, y1 = c.area
    return "pointy" if (x1 - x0) >= (y1 - y0) else "flat"


# ================================================================== 칸 지도
def _bin_edges(mx):
    """셈 단계 경계(5단계). 작으면 1·2·4·8·16, 크면 기하 간격."""
    if mx <= 16:
        return [1, 2, 4, 8, 16]
    e = [1]
    for k in range(1, 5):
        v = int(math.ceil(mx ** (k / 5.0)))
        e.append(max(v, e[-1] + 1))
    return e


def _bin_label(edges, j):
    lo = edges[j]
    hi = edges[j + 1] - 1 if j + 1 < len(edges) else None
    if hi is None:
        return f"{lo}+"
    return f"{lo}" if hi == lo else f"{lo}–{hi}"


def sec_cells(c: Ctx):
    cov = c.cov
    if not cov or not cov.get("centers"):
        return "", None
    C = cov["centers"]
    h = float(cov.get("h") or 30)
    orient = _orient(c)
    x0, x1, y0, y1 = c.area
    W, maxH = 510, 250
    k = min((W - 16) / (x1 - x0 + 2 * h), maxH / (y1 - y0 + 2 * h))
    pw, ph = (x1 - x0 + 2 * h) * k, (y1 - y0 + 2 * h) * k
    Wt, Ht = pw + 16, ph + 16
    sx = S.Scale(x1 + h, x0 - h, 8, 8 + pw) if c.xl else S.Scale(x0 - h, x1 + h, 8, 8 + pw)
    sy = S.Scale(y0 - h, y1 + h, 8 + ph, 8)
    r = h * k * 0.95
    by_role = {}
    mx = 1
    for role in ("start", "goal"):
        rr = cov.get(role) or {}
        cbd = rr.get("count_by_ds") or {}
        by = {}
        for name, arr in cbd.items():
            if name in c.dk:
                by[str(c.dk[name])] = [int(round(_num(v) or 0)) for v in arr]
        if not by:                                    # 데이터셋별이 없으면 합친 셈만(켜기/끄기 반영 안 됨)
            by = {"all": [int(math.ceil(_num(v) or 0)) for v in (rr.get("count") or [0] * len(C))]}
        tot = [sum(v[j] for v in by.values()) for j in range(len(C))]
        mx = max(mx, max(tot or [0]))
        by_role[role] = {"by": by, "reach": rr.get("reach")}
    edges = _bin_edges(mx)
    rec_cells = {"start": {}, "goal": {}}
    for o in ((c.rec or {}).get("options") or [])[:3]:
        for role in ("start", "goal"):
            kk = (o.get("cells") or {}).get(role)
            if isinstance(kk, int) and kk >= 0:
                rec_cells[role].setdefault(kk, []).append(str(o.get("label") or ""))
    out = []
    for role in ("start", "goal"):
        info = by_role[role]
        reach = info["reach"]
        tot = [sum(v[j] for v in info["by"].values()) for j in range(len(C))]
        filled = sum(1 for j in range(len(C)) if tot[j] > 0 and (reach is None or reach[j]))
        if reach is not None:
            nreach = sum(1 for v in reach if v)
            ttl = c.t(f"cells.{role}", reach=nreach, filled=filled, empty=nreach - filled)
        else:
            ttl = c.t(f"cells.{role}_all", n=len(C), filled=sum(1 for v in tot if v > 0))
        p = [S.open_svg(Wt, Ht, f"cellmap", ttl, {"data-role": role, "style": f"max-width:{num(Wt)}px"})]
        p.append(f'<defs>{S.hatch_pattern("hatch-" + role, "#B3B9C1", 5, 1)}</defs>')
        hx, hat, lab, badges = [], [], [], []
        for j, (cx_, cy_) in enumerate(C):
            px, py = sx(cx_), sy(cy_)
            rch = True if reach is None else bool(reach[j])
            hx.append(f'<polygon class="cell" data-c="{j}" data-reach="{1 if rch else 0}" points="{S.hex_points(px, py, r, orient)}"/>')
            if not rch:
                hat.append(f'<polygon points="{S.hex_points(px, py, r, orient)}"/>')
            lab.append(f'<text class="clab" data-c="{j}" x="{num(px)}" y="{num(py + 4)}" text-anchor="middle"></text>')
            recl = rec_cells[role].get(j)
            if recl:                                   # 추천 배치가 이 칸을 쓴다 — 검은 딱지(셈 글자는 그대로)
                t_ = "".join(recl)
                bw = 9 + 6.5 * len(t_)
                bx, by = px + r * 0.42, py - r * 0.62
                badges.append(f'<rect x="{num(bx - bw / 2)}" y="{num(by - 7.5)}" width="{num(bw)}" height="15" rx="7.5" '
                              f'fill="#1A1A1A" stroke="#fff" stroke-width="1.2"/>'
                              f'<text class="rbadge" x="{num(bx)}" y="{num(by + 3.8)}" text-anchor="middle">{esc(t_)}</text>')
        p.append(f'<g class="cells">{"".join(hx)}</g>')
        p.append(f'<g class="hatch" fill="url(#hatch-{role})" stroke="none" pointer-events="none">{"".join(hat)}</g>')
        p.append(f'<g class="clabs" pointer-events="none">{"".join(lab)}{"".join(badges)}</g></svg>')
        out.append(f'<div class="cellbox"><h3>{esc(ttl)}</h3><div class="plot">{"".join(p)}</div></div>')
    items = [(sw_box(SEQ[j]), _bin_label(edges, j)) for j in range(len(edges))]
    items = [("", c.t("cells.count") + ":")] + items
    items += [(sw_box("#fff", "#E69F00", 2.4), c.t("cells.empty")), (sw_box("#fff", "#C9CDD3", 1, pattern=True), c.t("cells.noreach"))]
    if any(rec_cells[r_] for r_ in rec_cells):
        items.append(('<span class="recbadge">A</span>', c.t("map.rec")))
    body = f'<div class="grid2 tight">{"".join(out)}</div>{legend(items)}<p class="muted small">{esc(c.t("map.left_is") if c.xl else "")}</p>'
    js = {"edges": edges, "start": by_role["start"], "goal": by_role["goal"], "n": len(C)}
    return panel("p-cells", c.t("cells.title"), body), js


# ================================================================== 지름길
def _side_screen(c: Ctx, side):
    """쪽 표를 화면 순서 [왼, 오] × [왼, 오] 로. rows/cols 라벨: hi(값 > split) · lo · left · right."""
    tb = side.get("table") or [[0, 0], [0, 0]]
    axis = side.get("axis") or "x"
    rows = side.get("rows") or ["hi", "lo"]          # 기본: DESIGN 3절 예 [[44,0],[4,52]] 과 같은 배치
    cols = side.get("cols") or ["lo", "hi"]

    def scr(lbl):
        if lbl in ("left", "right", "top", "bottom"):
            return lbl
        if axis == "x":
            hi = "left" if c.xl else "right"
            return hi if lbl == "hi" else ("right" if hi == "left" else "left")
        return "top" if lbl == "hi" else "bottom"
    order = ["left", "right"] if axis == "x" else ["top", "bottom"]
    M = [[0, 0], [0, 0]]
    for i, rl in enumerate(rows):
        for j, cl in enumerate(cols):
            M[order.index(scr(rl))][order.index(scr(cl))] = int(tb[i][j])
    return M, order


def _verdict(c: Ctx, acc, chance=0.5):
    if acc is None:
        return "info", ""
    st = "good" if acc <= c.tg["predict_good"] else "warn" if acc <= c.tg["predict_bad"] else "bad"
    return st, c.t("sc." + st, acc=pct(acc), chance=pct(chance))


def _side_from_eps(c: Ctx, eps, axis):
    """데이터셋 하나의 쪽 표(분석이 데이터셋별 표를 안 줄 때) — 기준선 = 그 데이터셋 출발 값 범위 가운데(analyze 와 같은 정의)."""
    v = [_num((e.get("start") or {}).get(axis)) for e in eps]
    g = [_num((e.get("goal") or {}).get(axis)) for e in eps]
    P = [(a, b) for a, b in zip(v, g) if a is not None and b is not None]
    if len(P) < 2:
        return None
    split = (min(a for a, _ in P) + max(a for a, _ in P)) / 2
    T = [[0, 0], [0, 0]]                                          # 행 [hi, lo] × 열 [lo, hi]
    for a, b in P:
        T[0 if a > split else 1][1 if b > split else 0] += 1
    n = len(P)
    return {"split": round(split, 1), "axis": axis, "rows": ["hi", "lo"], "cols": ["lo", "hi"], "table": T,
            "acc": round(sum(max(r) for r in T) / n, 3), "n": n}


def _side_pane(c: Ctx, side, acc, key, active, how="knn"):
    M, order = _side_screen(c, side)
    names = [c.t("pos." + o) for o in order]
    head = "".join(f"<th>{esc(c.t('sc.col', side=n))}</th>" for n in names)
    rows, lines = [], []
    for i in range(2):
        n = sum(M[i])
        tds = []
        for j in range(2):
            sh = M[i][j] / n if n else 0
            skew = n >= 5 and sh >= 0.9
            bg = f"rgba(0,114,178,{0.06 + 0.55 * sh:.2f})"
            fg = "#fff" if sh > 0.62 else "#1A1A1A"
            tds.append(f'<td class="{"skew" if skew else ""}" style="background:{bg};color:{fg}"><span class="big">{M[i][j]}</span>'
                       f'<span class="pc">{pct(sh) if n else "—"}</span>'
                       f'{("<span class=sk>▲ " + esc(c.t("sc.skew")) + "</span>") if skew else ""}</td>')
        rows.append(f"<tr><th>{esc(c.t('sc.row', side=names[i]))}<span class='muted'> ({n})</span></th>{''.join(tds)}</tr>")
        if n:
            j = 0 if M[i][0] >= M[i][1] else 1
            lines.append(c.t("sc.rowline", a=names[i], b=names[j], k=M[i][j], n=n))
    nt = sum(map(sum, M))
    colsum = [M[0][0] + M[1][0], M[0][1] + M[1][1]]
    chance = max(colsum) / nt if nt else 0.5
    st, vtxt = _verdict(c, acc, chance)
    split = _num(side.get("split"))
    cap = c.t("sc.table", axis=side.get("axis") or "x", split=f"{split:g}" if split is not None else "?")
    gauge = ""
    if acc is not None:
        cfg = {"lo": 0, "hi": 1, "target": c.tg["predict_good"], "chance": chance, "tlabel": f"≤ {pct(c.tg['predict_good'])}"}
        glab = c.t("sc.gauge", k=(c.r.get("coupling") or {}).get("predict", {}).get("k", 5)) if how == "knn" else c.t("sc.gauge_side")
        gauge = (f'<div class="gwrap"><div class="glabel">{esc(glab)}'
                 f' <b>{pct(acc)}</b></div>{_gauge_svg(c, cfg, acc, st, 420)}</div>')
    return (f'<div class="spane" data-pane="{esc(key)}"{"" if active else " hidden"}>'
            f'<div class="verdict {st}">{S.status_icon(st, 16)}<span>{esc(vtxt)}</span></div>'
            f'<table class="side"><caption>{esc(cap)}</caption><thead><tr><th></th>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'
            f'<p class="small muted">{esc(" · ".join(lines))}</p>{gauge}</div>')


def _scatter(c: Ctx, a, b, rho, rho_by, side, active, idx):
    W, H, ml, mr, mt, mb = 500, 340, 54, 14, 12, 46
    pts = []
    for i, e in enumerate(c.eps):
        va, vb = _num(_feat(e, a)), _num(_feat(e, b))
        if va is not None and vb is not None:
            pts.append((i, va, vb, c.ds_of(e)))
    if not pts:
        return ""
    xa = [q[1] for q in pts]
    yb = [q[2] for q in pts]
    pa = (max(xa) - min(xa)) * 0.07 or 10
    pb = (max(yb) - min(yb)) * 0.07 or 10
    rev = c.xl and a.endswith(".x")
    sx = S.Scale(max(xa) + pa, min(xa) - pa, ml, W - mr) if rev else S.Scale(min(xa) - pa, max(xa) + pa, ml, W - mr)
    sy = S.Scale(min(yb) - pb, max(yb) + pb, H - mb, mt)
    p = [S.open_svg(W, H, "pts scatter", f"{a} ↔ {b}", {"data-pair": str(idx), "style": "" if active else "display:none"})]
    p.append(S.axis_y(sy, ml, None, f"{i18n.feature(c.lang, b)} [mm]", grid_to=W - mr, label_dx=42))
    p.append(S.axis_x(sx, H - mb, None, f"{i18n.feature(c.lang, a)} [mm]" + ("  (+x ←)" if rev else ""), grid_to=mt))
    if side and _num(side.get("split")) is not None and a == f"start.{side.get('axis', 'x')}" and b == f"goal.{side.get('axis', 'x')}":
        s_ = float(side["split"])
        if min(sx.d0, sx.d1) < s_ < max(sx.d0, sx.d1):
            p.append(S.el("line", {"x1": sx(s_), "x2": sx(s_), "y1": mt, "y2": H - mb, "stroke": "#80868F", "stroke-dasharray": "4 3"}))
        if min(sy.d0, sy.d1) < s_ < max(sy.d0, sy.d1):
            p.append(S.el("line", {"x1": ml, "x2": W - mr, "y1": sy(s_), "y2": sy(s_), "stroke": "#80868F", "stroke-dasharray": "4 3"}))
        p.append(S.el("text", {"x": sx(s_) + 4, "y": mt + 10, "class": "tick"}, esc(f"{c.t('sc.split')} {s_:g}")))
    for d in c.ds:
        q = "".join(f'<circle data-i="{i}" cx="{num(sx(va))}" cy="{num(sy(vb))}" r="3.6"/>' for i, va, vb, dk in pts if dk == d["k"])
        p.append(f'<g class="ds d{d["k"]}" fill="{d["color"]}" fill-opacity="0.8" stroke="#fff" stroke-width="0.8">{q}</g>')
    p.append('<g class="sel-layer"></g><g class="hl-layer"></g></svg>')
    items = [(sw_dot(d["color"]), f"{d['name']}  ρ = {signed(rho_by.get(d['name']))}") for d in c.ds if d["name"] in rho_by]
    items.append(("", f"{c.t('sc.merged')}  ρ = {signed(rho)}"))
    return f'<div class="scwrap" data-pair="{idx}"{"" if active else " hidden"}>{"".join(p)}{legend(items)}</div>'


def _feat(e, name):
    cur = e
    for part in str(name).split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def sec_shortcut(c: Ctx) -> str:
    cp = c.r.get("coupling") or {}
    pairs = cp.get("pairs") or []
    side = cp.get("side") or None
    pred = cp.get("predict") or {}
    if not pairs and not side:
        return ""
    # 왼쪽: 산점(짝마다, 단추로 바꾸기)
    tabs, scs = [], []
    for k, pr in enumerate(pairs):
        lab = c.t("sc.scatter", a=i18n.feature(c.lang, pr.get("a")), b=i18n.feature(c.lang, pr.get("b")))
        tabs.append(f'<button type="button" class="btn{" on" if k == 0 else ""}" data-pairbtn="{k}">{esc(lab)}</button>')
        scs.append(_scatter(c, pr.get("a"), pr.get("b"), pr.get("rho"), pr.get("rho_by_ds") or {}, side, k == 0, k))
    left = (f'<div class="seg" role="group">{"".join(tabs)}</div>' if len(tabs) > 1 else "") + "".join(scs)
    # 오른쪽: 쪽 표 + 맞힘 계기 + 한 줄 판정(합침 / 데이터셋마다)
    right = ""
    if side:
        panes, btns = [], []
        acc0 = _num(pred.get("knn_acc"))
        if acc0 is None:
            acc0 = _num(side.get("acc"))
        how0 = "knn" if _num(pred.get("knn_acc")) is not None else "side"
        btns.append(f'<button type="button" class="btn on" data-sidebtn="all">{esc(c.t("sc.merged"))}</button>')
        panes.append(_side_pane(c, side, acc0, "all", True, how0))
        by_side = dict(side.get("by_ds") or {})
        cm_pred = {}
        for m in (c.r.get("compare") or {}).get("metrics") or []:
            if m.get("key") == "predict":
                cm_pred = m.get("values") or {}
        if not by_side and len(c.ds) > 1:
            for d in c.ds:
                E = [e for e in c.eps if c.ds_of(e) == d["k"] and "excluded" not in (e.get("flags") or [])]
                sd = _side_from_eps(c, E, side.get("axis") or "x")
                if sd:
                    by_side[d["name"]] = sd
        for name, sd in by_side.items():
            if name not in c.dk:
                continue
            how = "knn"
            acc = _num((pred.get("by_ds") or {}).get(name))
            if acc is None:
                acc = _num(cm_pred.get(name))
            if acc is None:
                acc, how = _num(sd.get("acc")), "side"
            col = c.ds[c.dk[name]]["color"]
            btns.append(f'<button type="button" class="btn" data-sidebtn="{esc(name)}"><span class="sw" style="background:{col}"></span>'
                        f'{esc(name)}</button>')
            panes.append(_side_pane(c, sd, acc, name, False, how))
        right = (f'<div class="seg" role="group">{"".join(btns)}</div>' if len(btns) > 1 else "") + "".join(panes)
    body = f'<div class="grid2 sc"><div>{left}</div><div class="sideblk">{right}</div></div>'
    return panel("p-shortcut", c.t("sc.title"), body)


# ================================================================== 옮긴 거리
def sec_transfer(c: Ctx) -> str:
    vals = {d["k"]: [] for d in c.ds}
    for e in c.eps:
        m = _num(e.get("move_mm"))
        if m is None:
            s, g = _pt(e.get("start")), _pt(e.get("goal"))
            m = math.dist(s, g) if s and g else None
        if m is not None:
            vals[c.ds_of(e)].append(m)
    allv = [v for L in vals.values() for v in L]
    if not allv:
        return ""
    near = float((c.r.get("transfer") or {}).get("near_mm") or c.sp.get("near_mm") or 100)
    W, H, ml, mr, mt, mb = 500, 300, 58, 16, 14, 46
    xmax = S.ticks(0, max(allv) * 1.04, 6)[-1]
    if xmax < max(allv):
        xmax = max(allv) * 1.05
    sx = S.Scale(0, xmax, ml, W - mr)
    sy = S.Scale(0, 1, H - mb, mt)
    p = [S.open_svg(W, H, "cdf", c.t("tr.title"), {"data-x": f"{sx.d0},{sx.d1},{sx.r0},{sx.r1}", "data-y": f"{sy.r1},{sy.r0}"})]
    p.append(S.el("rect", {"x": sx(0), "y": mt, "width": sx(near) - sx(0), "height": H - mb - mt, "fill": "#EAF1F8"}))
    p.append(S.el("text", {"x": (sx(0) + sx(near)) / 2, "y": mt + 14, "class": "tick", "text-anchor": "middle"},
                  esc(c.t("tr.near", mm=f"{near:.0f}"))))
    p.append(S.axis_y(sy, ml, [0, 0.25, 0.5, 0.75, 1.0], c.t("tr.y"), pct=True, grid_to=W - mr, label_dx=46))
    p.append(S.axis_x(sx, H - mb, None, c.t("tr.x")))
    ts = c.tg["near_share"]
    p.append(S.el("line", {"x1": sx(0), "x2": sx(near), "y1": sy(ts), "y2": sy(ts), "stroke": "#1A1A1A", "stroke-width": 1.5,
                           "stroke-dasharray": "4 3"}))
    p.append(S.marker_shape("diamond", sx(near), sy(ts), 4.5, {"fill": "#1A1A1A"}, {"tip": c.t("tr.target", share=pct(ts))}))
    p.append(S.el("text", {"x": (sx(0) + sx(near)) / 2, "y": sy(ts) - 6, "class": "tick ink", "text-anchor": "middle"},
                  esc(f"{c.t('target')} ≥ {pct(ts)}")))
    items = []
    for d in c.ds:
        v = sorted(vals[d["k"]])
        if not v:
            continue
        n = len(v)
        dd = [f"M{num(sx(0))},{num(sy(0))}"]
        for j, m in enumerate(v):
            dd.append(f"H{num(sx(m))}V{num(sy((j + 1) / n))}")
        dd.append(f"H{num(sx(xmax))}")
        p.append(f'<path class="ds d{d["k"]}" d="{"".join(dd)}" fill="none" stroke="{d["color"]}" stroke-width="2" stroke-linejoin="round"/>')
        ns = bisect_right(v, near) / n
        med = v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2
        items.append((sw_line(d["color"]), c.t("tr.legend", name=d["name"], near=pct(ns), med=f"{med:.0f}")))
    p.append(S.el("line", {"class": "xh", "x1": -10, "x2": -10, "y1": mt, "y2": H - mb, "stroke": "#4A4F57", "stroke-width": 1}))
    p.append("</svg>")
    items.append((sw_line("#1A1A1A", "4 3", 1.5), c.t("tr.target", share=pct(ts))))
    return panel("p-transfer", c.t("tr.title"), f'<div class="plot">{"".join(p)}</div>{legend(items)}', wide=False)


# ================================================================== 이산 칸
def sec_strata(c: Ctx) -> str:
    strata = c.r.get("strata") or []
    if not strata:
        return ""
    charts = []
    sub = ""
    good = c.tg["strata_dev_good"]
    worst = max((_num(s.get("max_dev")) or 0 for s in strata), default=0)
    sub = c.t("st.sub", dev=f"{worst * 100:.0f}%p", good=f"{good * 100:.0f}%p")
    for s in strata:
        name = s.get("name")
        rows = s.get("rows") or []
        vals = [r_.get("value") for r_ in rows]
        if not vals:
            continue
        # 데이터셋마다 비율(에피소드의 discrete 에서; 없으면 rows.n_by_ds)
        share = {}
        for d in c.ds:
            L = [e for e in c.eps if c.ds_of(e) == d["k"] and (e.get("discrete") or {}).get(name) is not None]
            if L:
                share[d["k"]] = [sum(1 for e in L if e["discrete"][name] == v) / len(L) for v in vals]
            elif all(isinstance(r_.get("n_by_ds"), dict) for r_ in rows):
                tot = sum(r_["n_by_ds"].get(d["name"], 0) for r_ in rows)
                if tot:
                    share[d["k"]] = [r_["n_by_ds"].get(d["name"], 0) / tot for r_ in rows]
        if not share:
            share[-1] = [_num(r_.get("share")) or 0 for r_ in rows]
        W, H, ml, mr, mt, mb = 245, 220, 40, 6, 14, 40
        top = max([0.5] + [v for L in share.values() for v in L] + [_num(r_.get("target")) or 0 for r_ in rows]) * 1.12
        sy = S.Scale(0, top, H - mb, mt)
        gw = (W - ml - mr) / len(vals)
        nb = len(share)
        bw = min(22.0, (gw - 12) / max(1, nb) - 2)
        p = [S.open_svg(W, H, "strata", str(name))]
        p.append(S.axis_y(sy, ml, S.ticks(0, top, 4), None, pct=True, grid_to=W - mr))
        p.append(S.el("line", {"x1": ml, "x2": W - mr, "y1": H - mb, "y2": H - mb, "class": "axis"}))
        for j, r_ in enumerate(rows):
            gx = ml + j * gw
            x = gx + (gw - (nb * (bw + 2) - 2)) / 2
            for kk, (dk, L) in enumerate(share.items()):
                col = c.ds[dk]["color"] if dk >= 0 else "#0072B2"
                tip = f"{c.ds[dk]['name'] if dk >= 0 else ''} · {i18n.name(c.lang, name)} {vals[j]}: {pct(L[j])}"
                p.append(S.bar_v(x + kk * (bw + 2), H - mb, bw, sy(0) - sy(L[j]), 3,
                                 {"fill": col, "class": f"ds d{dk}" if dk >= 0 else None}, {"tip": tip}))
            tv = _num(r_.get("target"))
            if tv is not None:
                p.append(S.el("line", {"x1": gx + 4, "x2": gx + gw - 4, "y1": sy(tv), "y2": sy(tv), "stroke": "#1A1A1A",
                                       "stroke-width": 1.5, "stroke-dasharray": "4 3"}))
            dev = (_num(r_.get("share")) or 0) - (tv or 0)
            if tv is not None and abs(dev) > good:
                stc = "bad" if abs(dev) > c.tg["strata_dev_bad"] else "warn"
                ytop = sy(max([L[j] for L in share.values()] + [tv])) - 8
                p.append(f'<g transform="translate({num(gx + gw / 2 - 18)},{num(ytop - 10)})">{_mini_icon(stc, dev > 0)}'
                         f'<text x="14" y="10" class="tick ink">{esc(c.t("st.more") if dev > 0 else c.t("st.less"))}</text></g>')
            p.append(S.el("text", {"x": gx + gw / 2, "y": H - mb + 15, "class": "tick", "text-anchor": "middle"}, esc(str(vals[j]))))
        p.append(S.el("text", {"x": (ml + W - mr) / 2, "y": H - 8, "class": "alabel", "text-anchor": "middle"}, esc(i18n.name(c.lang, name))))
        p.append("</svg>")
        charts.append(f'<div class="plot">{"".join(p)}</div>')
    items = [(sw_box(d["color"]), d["name"]) for d in c.ds] + [(sw_line("#1A1A1A", "4 3", 1.5), c.t("st.even"))]
    body = f'<div class="grid2 tight st">{"".join(charts)}</div>{legend(items)}'
    return panel("p-strata", c.t("st.title"), body, sub, wide=False)


def _mini_icon(st, up=True):
    """치우침 표시: ▲ 많음 / ▼ 적음, 색 = 주의·나쁨(모양과 글로도 같은 뜻)."""
    col = STATUS.get(st, "#7F7F7F")
    if up:
        return f'<path d="M6,0.5 L11.5,10.5 L0.5,10.5 Z" fill="{col}"/>'
    return f'<path d="M0.5,0.5 L11.5,0.5 L6,10.5 Z" fill="{col}"/>'


# ================================================================== 비교
def sec_compare(c: Ctx) -> str:
    cmp_ = c.r.get("compare") or {}
    mets = cmp_.get("metrics") or []
    if len(c.ds) < 2 or not mets:
        return ""
    rows = []
    keys = [m.get("key") for m in mets]
    has_pairs = any(str(k).startswith("rho:") for k in keys)
    for m in mets:
        key = str(m.get("key"))
        if (key == "rho" and has_pairs) or (key == "same_fixture_n" and "same_fixture" in keys):
            continue                                   # 같은 뜻이 이미 있음
        vals = m.get("values") or {}
        pair = m.get("pair") or ""
        if key.startswith("rho:"):
            pair, key = key[4:], "rho_pair"
        tpl = i18n.METRIC.get(c.lang, {}).get(key, key)
        lab = _fmt(tpl, pair=" ↔ ".join(i18n.feature(c.lang, s) for s in pair.split("→")) if pair else "")
        nums = [abs(_num(v)) for v in vals.values() if _num(v) is not None]
        if not nums:
            continue
        is_share = key in SHARE_KEYS
        signed_v = key == "rho_pair"
        hi = 1.0 if is_share else max(nums) or 1.0
        bars = []
        for d in c.ds:
            v = _num(vals.get(d["name"]))
            if v is None:
                continue
            w = max(0.0, min(1.0, abs(v) / hi)) * 100
            if signed_v:
                txt = signed(v)
            elif key in ("rho",):
                txt = f"{v:.2f}"
            elif is_share:
                txt = pct(v)
            else:
                txt = f"{v:.0f}" if abs(v) >= 10 or float(v).is_integer() else f"{v:.1f}"
            bars.append(f'<div class="cbar ds d{d["k"]}"><span class="bar" style="width:{w:.1f}%;background:{d["color"]}"></span>'
                        f'<span class="v">{esc(txt)}</span></div>')
        better = {"lower": "low", "higher": "high"}.get(m.get("better"), m.get("better"))
        if key == "rho_pair":
            better = "zero"                            # 부호 있는 ρ — 0 에 가까울수록 좋다
        hint = ""
        if better == "zero":
            hint = f'<span class="hint">{esc(c.t("cmp.zero"))}</span>'
        elif better in ("low", "high"):
            hint = f'<span class="hint">{"↓ " if better == "low" else "↑ "}{esc(c.t("cmp." + better))}</span>'
        rows.append(f'<div class="crow"><div class="clabel">{esc(lab)}{hint}</div><div class="cbars">{"".join(bars)}</div></div>')
    items = [(sw_box(d["color"]), d["name"]) for d in c.ds]
    return panel("p-compare", c.t("cmp.title"), f'<div class="cmp">{"".join(rows)}</div>{legend(items)}')


# ================================================================== 시간표 + 수집 기록
def sec_timeline(c: Ctx) -> str:
    order = sorted(range(len(c.eps)), key=lambda i: (str(c.eps[i].get("t") or "~"), i))
    if not order:
        return ""
    lanes = [d for d in c.ds if any(c.ds_of(c.eps[i]) == d["k"] for i in order)]
    W, ml, mr, mt, lane = 1040, 120, 12, 26, 30
    H = mt + lane * len(lanes) + 8
    n = len(order)
    sx = S.Scale(0, max(1, n - 1), ml + 8, W - mr - 8)
    ly = {d["k"]: mt + lane * j + lane / 2 for j, d in enumerate(lanes)}
    p = [S.open_svg(W, H, "pts timeline", c.t("tl.title"))]
    for j, d in enumerate(lanes):
        y = ly[d["k"]]
        p.append(S.el("line", {"x1": ml, "x2": W - mr, "y1": y, "y2": y, "stroke": "#EEF0F3", "stroke-width": 10, "class": f"ds d{d['k']}"}))
        p.append(f'<g class="ds d{d["k"]}"><circle cx="{ml - 104}" cy="{num(y)}" r="5" fill="{d["color"]}"/>'
                 f'<text x="{ml - 94}" y="{num(y + 4)}" class="tick ink">{esc(d["name"])}</text></g>')
    prev = None
    r = 3.6 if n < 400 else 2.6 if n < 2000 else 1.8
    for pos, i in enumerate(order):
        day = str(c.eps[i].get("t") or "")[:10]
        if day and day != prev:
            x = sx(pos) - (sx(1) - sx(0)) / 2 if pos else sx(pos) - 6
            p.append(S.el("line", {"x1": x, "x2": x, "y1": mt - 6, "y2": H - 4, "stroke": "#9AA0A8", "stroke-dasharray": "1 3"}))
            p.append(S.el("text", {"x": x + 3, "y": mt - 10, "class": "tick"}, esc(day[5:].replace("-", "/"))))
            prev = day
    for d in lanes:
        q = []
        for pos, i in enumerate(order):
            e = c.eps[i]
            if c.ds_of(e) != d["k"]:
                continue
            col, shape = OUTCOME.get(e.get("outcome"), OUTCOME[None])
            st = {"fill": "none", "stroke": col, "stroke-width": 1.8} if shape in ("cross", "ring") else {"fill": col}
            q.append(S.marker_shape(shape, sx(pos), ly[d["k"]], r, st, {"i": i}))
        p.append(f'<g class="ds d{d["k"]}">{"".join(q)}</g>')
    p.append('<g class="sel-layer"></g><g class="hl-layer"></g></svg>')
    present = sorted({e.get("outcome") for e in c.eps}, key=lambda o: list(OUTCOME).index(o) if o in OUTCOME else 99)
    items = [(sw_shape(OUTCOME.get(o, OUTCOME[None])[1], OUTCOME.get(o, OUTCOME[None])[0]), c.t(f"oc.{o or 'none'}")) for o in present]
    body = f'<p class="muted small">{esc(c.t("tl.sub"))}</p><div class="plot">{"".join(p)}</div>{legend(items)}'
    body += _runs(c)
    return panel("p-timeline", c.t("tl.title"), body)


RUN_ORDER = ["success", "fail", "unsure", "norec", "abort", "other"]


def run_counts(d: dict) -> dict:
    """날짜 한 줄 → {결과: 횟수}. {"outcomes": {...}} 또는 analyze/runs.py 의 평평한 {"success", "fail", "unsure", "other"}."""
    oc = d.get("outcomes") or d.get("counts")
    if not isinstance(oc, dict):
        oc = {k: v for k, v in d.items() if k not in ("day", "n", "kept", "total") and isinstance(v, (int, float))
              and not isinstance(v, bool) and not k.startswith("exec") and not k.endswith(("_s", "_median"))}
    return {str(k): int(v) for k, v in oc.items()}
SHARE_KEYS = {"rho", "rho_pair", "predict", "side_acc", "near_share", "coverage", "strata_dev", "same_fixture"}


def _runs(c: Ctx) -> str:
    runs = c.r.get("runs")
    if not runs or not runs.get("by_day"):
        return ""
    days = runs["by_day"]

    counts = run_counts
    cats = list(RUN_ORDER)
    for d in days:
        for k in counts(d):
            if k not in cats:
                cats.append(k)
    cats = [k for k in cats if any(counts(d).get(k) for d in days)]
    W, H, ml, mr, mt, mb = 500, 270, 40, 10, 24, 36
    tot = [int(d.get("n") or 0) or sum(counts(d).values()) for d in days]
    top = S.ticks(0, max(tot or [1]) * 1.15, 5)[-1]
    sy = S.Scale(0, top, H - mb, mt)
    gw = (W - ml - mr) / max(1, len(days))
    bw = min(34.0, gw * 0.6)
    p = [S.open_svg(W, H, "runsday", c.t("runs.title"))]
    p.append(S.axis_y(sy, ml, S.ticks(0, top, 5), None, grid_to=W - mr))
    p.append(S.el("line", {"x1": ml, "x2": W - mr, "y1": H - mb, "y2": H - mb, "class": "axis"}))
    for j, d in enumerate(days):
        x = ml + j * gw + (gw - bw) / 2
        y = H - mb
        cn = counts(d)
        for k in cats:
            v = cn.get(k, 0)
            if not v:
                continue
            hgt = sy(0) - sy(v)
            col = OUTCOME.get(k, ("#7F7F7F", ""))[0]
            p.append(S.el("rect", {"x": x, "y": y - hgt + 1, "width": bw, "height": max(0.5, hgt - 1.5), "fill": col},
                          None, {"tip": f"{d.get('day')} · {c.t('oc.' + k)} {v}"}))
            y -= hgt
        kept = d.get("kept")
        lab = f"{kept}/{tot[j]}" if kept is not None else f"{tot[j]}"
        p.append(S.el("text", {"x": x + bw / 2, "y": sy(tot[j]) - 5, "class": "tick ink", "text-anchor": "middle"}, esc(lab)))
        p.append(S.el("text", {"x": x + bw / 2, "y": H - mb + 15, "class": "tick", "text-anchor": "middle"},
                      esc(str(d.get("day") or "")[5:].replace("-", "/"))))
    p.append(S.el("text", {"x": ml - 6, "y": mt - 10, "class": "tick", "text-anchor": "end"}, esc(c.t("runs.y"))))
    p.append("</svg>")
    # 이유 막대(결과별로 쌓기 — by_verdict 가 있으면)
    rs = runs.get("reasons") or []
    if isinstance(rs, dict):
        rs = [{"code": k, "n": v} for k, v in rs.items()]
    rs = sorted([r_ for r_ in rs if (r_.get("n") or 0) > 0], key=lambda r_: -r_["n"])
    code_oc = {"goal_state_unknown": "unsure", "not_recorded": "norec", "aborted": "abort"}
    n_bad = sum(sum(v for k, v in counts(d).items() if k != "success") for d in days) or sum(r_["n"] for r_ in rs)
    q = ""
    if rs:
        RW, row = 500, 30
        RH = 20 + row * len(rs) + 26
        lw = 210
        mxr = max(r_["n"] for r_ in rs)
        top_r = S.ticks(0, mxr, 4)[-1]
        sxr = S.Scale(0, top_r if top_r >= mxr else mxr * 1.1, lw, RW - 30)
        q = [S.open_svg(RW, RH, "reasons", c.t("runs.reasons", n=n_bad))]
        for j, r_ in enumerate(rs):
            y = 14 + j * row
            txt = i18n.REASON.get(c.lang, {}).get(r_.get("code"), r_.get("text") or r_.get("code"))
            q.append(S.el("text", {"x": lw - 8, "y": y + 14, "class": "tick ink", "text-anchor": "end"}, esc(txt)))
            bv = r_.get("by_verdict") if isinstance(r_.get("by_verdict"), dict) else None
            if not bv:
                bv = {r_.get("outcome") or code_oc.get(r_.get("code"), "fail"): r_["n"]}
            segs = sorted(bv.items(), key=lambda kv: RUN_ORDER.index(kv[0]) if kv[0] in RUN_ORDER else 99)
            x = lw
            tipd = " · ".join(f"{c.t('oc.' + k)} {v}" for k, v in segs)
            for k, v in segs:
                w = sxr(x - lw + 0) if False else (sxr(v) - lw)
                col = OUTCOME.get(k, OUTCOME["other"])[0]
                last = (k, v) == segs[-1]
                if last:
                    q.append(S.bar_h(x, y + 3, w, 16, 3, {"fill": col}, {"tip": f"{txt}: {r_['n']} ({tipd})"}))
                else:
                    q.append(S.el("rect", {"x": x, "y": y + 3, "width": max(0.5, w - 1.5), "height": 16, "fill": col}, None,
                                  {"tip": f"{txt}: {r_['n']} ({tipd})"}))
                x += w
            q.append(S.el("text", {"x": x + 5, "y": y + 15, "class": "tick ink"}, str(r_["n"])))
        q.append(S.axis_x(sxr, 14 + row * len(rs) + 2, S.ticks(sxr.d0, sxr.d1, 4)))
        q.append("</svg>")
        q = "".join(q)
    dur = runs.get("durations") or {}
    kept = runs.get("kept")
    if isinstance(kept, dict):
        kept = kept.get("success", 0)
    if kept is None:
        kept = sum((d.get("kept") or 0) for d in days)
    med = dur.get("median_s")
    if med is None and isinstance(dur.get("all"), dict):
        med = dur["all"].get("median")
    sub = c.t("runs.sub", n=runs.get("n", sum(tot)), kept=kept, med=f"{_num(med):.1f}" if _num(med) is not None else "—")
    used = list(cats)
    for r_ in rs:
        for k in (r_.get("by_verdict") or {}):
            if k not in used:
                used.append(k)
    items = [(sw_box(OUTCOME.get(k, OUTCOME["other"])[0]), c.t("oc." + k)) for k in used]
    return (f'<div class="runs"><h3>{esc(c.t("runs.title"))}</h3><p class="muted small">{esc(sub)}</p>'
            f'<div class="grid2 tight"><div class="plot">{"".join(p)}</div>'
            f'<div class="plot"><div class="small ink rtitle">{esc(c.t("runs.reasons", n=n_bad))}</div>{q}</div></div>'
            f'{legend(items)}</div>')


# ================================================================== 에피소드 표
def sec_table(c: Ctx) -> str:
    strata_names = [s.get("name") for s in (c.r.get("strata") or []) if s.get("name")]
    has_thumb = any(_thumb(e) for e in c.eps)
    cols = ([("thumb", c.t("col.thumb"))] if has_thumb else []) + [
        ("id", c.t("col.id")), ("d", c.t("col.ds")), ("t", c.t("col.t")), ("o", c.t("col.outcome")),
        ("s", c.t("col.start")), ("g", c.t("col.goal")), ("m", c.t("col.move")), ("c", c.t("col.cells"))]
    for k, nm in enumerate(strata_names):
        cols.append((f"k{k}", i18n.name(c.lang, nm)))
    cols.append(("f", c.t("col.flags")))
    th = "".join(f'<th data-col="{esc(k)}"{" class=num" if k in ("m",) else ""}>{esc(v)}</th>' for k, v in cols)
    ds_opts = "".join(f'<option value="{d["k"]}">{esc(d["name"])}</option>' for d in c.ds)
    ocs = sorted({e.get("outcome") or "none" for e in c.eps})
    oc_opts = "".join(f'<option value="{esc(o)}">{esc(c.t("oc." + o))}</option>' for o in ocs)
    flags = sorted({f for e in c.eps for f in (e.get("flags") or [])})
    fl_opts = "".join(f'<option value="{esc(f)}">{esc(i18n.FLAG.get(c.lang, {}).get(f, f))}</option>' for f in flags)
    ctrl = (f'<div class="tctrl"><label>{esc(c.t("tbl.ds"))} <select id="f-ds"><option value="">{esc(c.t("tbl.all"))}</option>{ds_opts}</select></label>'
            f'<label>{esc(c.t("tbl.outcome"))} <select id="f-oc"><option value="">{esc(c.t("tbl.all"))}</option>{oc_opts}</select></label>'
            f'<label>{esc(c.t("tbl.flag"))} <select id="f-fl"><option value="">{esc(c.t("tbl.all"))}</option>'
            f'<option value="-">{esc(c.t("tbl.none"))}</option>{fl_opts}</select></label>'
            f'<input type="search" id="f-q" placeholder="{esc(c.t("tbl.search"))}">'
            f'<span class="muted small" id="f-count"></span><span class="muted small">· {esc(c.t("tbl.hint"))}</span></div>')
    body = (f'{ctrl}<div class="tblwrap"><table class="eps" id="eps"><thead><tr>{th}</tr></thead><tbody></tbody></table></div>')
    nu = len(c.r.get("unusable") or [])
    return panel("p-table", c.t("tbl.title"), body, c.t("tbl.unusable", n=nu) if nu else "")


def _thumb(e):
    th = e.get("thumbs") or {}
    for k in ("third", "wrist", *th.keys()):
        v = th.get(k)
        if not isinstance(v, str):
            continue
        if v.startswith("data:image/") and len(v) <= THUMB_MAX:
            return v
        if "://" not in v and not v.startswith(("/", "\\")) and v.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
            return v                                     # 같은 폴더 기준 상대 경로(외부 요청 아님)
    return None


# ================================================================== JS 로 넘길 데이터
def js_data(c: Ctx, mapt, cells) -> dict:
    strata_names = [s.get("name") for s in (c.r.get("strata") or []) if s.get("name")]
    eps = []
    budget = THUMB_TOTAL
    for i, e in enumerate(c.eps):
        s, g = _pt(e.get("start")), _pt(e.get("goal"))
        m = _num(e.get("move_mm"))
        if m is None and s and g:
            m = math.dist(s, g)
        row = {"id": e.get("id"), "d": c.ds_of(e), "t": e.get("t"), "o": e.get("outcome"),
               "s": [round(s[0], 1), round(s[1], 1)] if s else None, "g": [round(g[0], 1), round(g[1], 1)] if g else None,
               "m": round(m, 1) if m is not None else None, "cs": e.get("cell_start"), "cg": e.get("cell_goal"),
               "k": [(e.get("discrete") or {}).get(n) for n in strata_names], "f": list(e.get("flags") or [])}
        fx = []
        for f in e.get("fixtures") or []:
            fp = _pt(f)
            if fp:
                L, Wd = _fixture_size(c, f.get("name"), f.get("type"))
                fx.append([round(fp[0], 1), round(fp[1], 1), round(float(f.get("yaw") or 0), 1), float(L), float(Wd)])
        if fx:
            row["fx"] = fx
        th = _thumb(e)
        if th and len(th) <= budget:
            row["th"] = th
            budget -= len(th)
        eps.append(row)
    strs = {k: c.t(k) for k in ("tip.move", "tip.cells", "tip.t", "tip.outcome", "tbl.shown", "cells.tip", "cells.reach_yes",
                                "cells.reach_no", "episodes_unit", "col.flags", "tbl.all")}
    strs["oc"] = {o: c.t("oc." + o) for o in ("success", "fail", "unsure", "none", "norec", "abort")}
    strs["flag"] = i18n.FLAG.get(c.lang, {})
    strs["strata"] = [i18n.name(c.lang, n) for n in strata_names]
    return {"lang": c.lang, "ds": [{"n": d["name"], "c": d["color"]} for d in c.ds], "ep": eps, "str": strs, "map": mapt,
            "cells": cells, "ocol": {k or "none": v[0] for k, v in OUTCOME.items()}, "seq": SEQ}


# ================================================================== 조립
def build(result: dict, lang: str = "ko") -> str:
    c = Ctx(result, lang)
    map_html, mapt = sec_map(c)
    cells_html, cells_js = sec_cells(c)
    tr, st = sec_transfer(c), sec_strata(c)
    half = f'<div class="grid2 halfrow">{tr}{st}</div>' if (tr and st) else (tr + st)
    parts = [sec_header(c), sec_cards(c), sec_next(c), map_html, cells_html, sec_shortcut(c), half, sec_compare(c),
             sec_timeline(c), sec_table(c)]
    data = json.dumps(js_data(c, mapt, cells_js), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    ds_css = "".join(f"body.off-d{d['k']} .d{d['k']}{{display:none}}" for d in c.ds)
    title = c.sp.get("title") or c.sp.get("task") or "layoutkit"
    foot = c.t("footer", version=result.get("version") or "")
    return (f'<!doctype html><html lang="{esc(lang)}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)} — layoutkit</title>'
            f'<style>{CSS}{ds_css}</style></head><body><div class="wrap">{"".join(parts)}'
            f'<footer class="muted small">{esc(foot)}</footer></div><div id="tip" role="tooltip" hidden></div>'
            f'<script>const D={data};</script><script>{JS}</script></body></html>')


# ================================================================== CSS
CSS = r"""
:root{--ink:#1A1A1A;--ink2:#4A4F57;--muted:#80868F;--line:#E3E6EA;--bg:#F4F5F7;--panel:#fff;
--good:#009E73;--warn:#E69F00;--bad:#D55E00;--info:#0072B2;color-scheme:light}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI","Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR","Noto Sans CJK KR",sans-serif}
.wrap{max-width:1120px;margin:0 auto;padding:18px 16px 40px}
h1{font-size:22px;margin:0 0 2px;font-weight:700;letter-spacing:-.01em}
h2{font-size:16px;margin:0;font-weight:700}
h3{font-size:13.5px;margin:0 0 6px;font-weight:600;color:var(--ink2)}
.muted{color:var(--muted)} .small{font-size:12.5px} .ink{fill:var(--ink2)!important;color:var(--ink2)}
code{font:12.5px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:#EEF0F3;padding:1px 6px;border-radius:4px}
.top{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:flex-end;gap:10px 24px;margin-bottom:14px}
.meta{color:var(--muted);font-size:12.5px}
.dsrow{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.dsrow .lbl{font-size:12.5px;margin-right:2px}
.dschip{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:#fff;border-radius:999px;padding:4px 10px 4px 8px;cursor:pointer;font-size:13px;user-select:none}
.dschip input{margin:0;accent-color:#4A4F57}
.dschip:has(input:not(:checked)){opacity:.45}
.sw{display:inline-block;width:10px;height:10px;border-radius:50%;flex:none}
.btn{font:inherit;font-size:12.5px;border:1px solid #CDD2D8;background:#fff;color:var(--ink);border-radius:6px;padding:3px 10px;cursor:pointer;display:inline-flex;align-items:center;gap:6px}
.btn:hover{background:#F1F3F5} .btn.on{background:#1A1A1A;color:#fff;border-color:#1A1A1A}
.btn.small{padding:1px 8px;font-size:12px}
.seg{display:inline-flex;flex-wrap:wrap;gap:4px;margin-bottom:8px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(196px,1fr));gap:12px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:0 14px 12px;overflow:hidden;display:flex;flex-direction:column}
.card::before{content:"";display:block;height:5px;margin:0 -14px 10px;background:var(--sc)}
.card.good{--sc:var(--good)} .card.warn{--sc:var(--warn)} .card.bad{--sc:var(--bad)} .card.info{--sc:var(--info)}
.chead{display:flex;justify-content:space-between;align-items:flex-start;gap:6px}
.cname{font-size:12.5px;font-weight:600;color:var(--ink2);line-height:1.3}
.badge{display:inline-flex;align-items:center;gap:4px;font-size:12px;font-weight:700;white-space:nowrap;padding:1px 7px 1px 4px;border-radius:999px;background:#F3F4F6}
.badge.good{background:#E3F4EE}.badge.warn{background:#FCF1DC}.badge.bad{background:#FBE6DC}.badge.info{background:#E2EEF7}
.sicon{flex:none;display:block}
.val{font-size:30px;font-weight:700;line-height:1.15;margin-top:6px;letter-spacing:-.01em}
.val small{font-size:13px;font-weight:600;color:var(--ink2);margin-left:4px;letter-spacing:0}
.vsub{font-size:12px;color:var(--muted);min-height:18px}
.gauge{width:100%;height:auto;display:block;margin:4px 0 2px}
.gt{font-size:11px;fill:var(--muted)} .gtb{fill:var(--ink);font-weight:600}
.why{margin:6px 0 4px;font-size:13px;line-height:1.4}
.todo{margin:auto 0 0;font-size:12.5px;line-height:1.4;color:var(--ink2);border-top:1px dashed var(--line);padding-top:6px}
.todo b{color:var(--ink);margin-right:3px}
.next{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(0,1fr);gap:16px;background:#fff;border:1px solid var(--line);border-left:5px solid #1A1A1A;border-radius:10px;padding:14px 16px;margin-top:14px}
.next h2{margin-bottom:8px}
.recs{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.recs li{display:flex;gap:10px;align-items:flex-start}
.rlabel{flex:none;width:24px;height:24px;border-radius:50%;background:#1A1A1A;color:#fff;font-weight:700;display:grid;place-items:center;font-size:13px;margin-top:1px}
.rtxt{font-size:14px;line-height:1.45}
.rtags{display:flex;flex-wrap:wrap;gap:4px;margin-top:3px}
.tag{font-size:11.5px;background:#EEF0F3;border-radius:4px;padding:0 6px;color:var(--ink2)}
.norec{margin:4px 0;color:var(--ink2)}
.notes{border-left:1px solid var(--line);padding-left:16px}
.notes ul{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.notes li{display:flex;gap:8px;font-size:13px;line-height:1.4} .notes li .sicon{margin-top:3px}
details.panel{background:#fff;border:1px solid var(--line);border-radius:10px;margin-top:16px;min-width:0}
details.panel>summary{list-style:none;cursor:pointer;padding:12px 16px 10px;display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 12px}
details.panel>summary::-webkit-details-marker{display:none}
summary .sub{font-size:12.5px;color:var(--muted)}
.chev{margin-left:auto;width:9px;height:9px;border-right:2px solid #9AA0A8;border-bottom:2px solid #9AA0A8;transform:rotate(45deg);align-self:center}
details:not([open]) .chev{transform:rotate(-45deg)}
.tools{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:0 16px 6px}
.tools .seg{margin:0}
.selchip{display:inline-flex;gap:6px;align-items:center;font-size:12.5px;background:#FFF6E0;border:1px solid #F0D9A0;border-radius:6px;padding:2px 6px}
.selchip[hidden]{display:none}
.pbody{padding:0 16px 14px}
.plot{overflow-x:auto}
.plot svg{display:block;width:100%;height:auto;min-width:300px;margin:0 auto}
svg text{font-family:inherit}
.tick{font-size:11px;fill:var(--muted)}
.alabel{font-size:12px;fill:var(--ink2)}
.grid{stroke:#EEF0F3;stroke-width:1}
.axis{stroke:#B9BEC5;stroke-width:1}
.rbadge{font-size:11px;font-weight:700;fill:#fff}
.legend{display:flex;flex-wrap:wrap;gap:4px 16px;margin-top:8px;font-size:12.5px;color:var(--ink2)}
.legend .li{display:inline-flex;align-items:center;gap:5px}
.legend svg{flex:none}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,440px),1fr));gap:16px}
.grid2.tight{gap:12px}
.grid2.halfrow{gap:16px}
.grid2.halfrow>details.panel{margin-top:16px}
.grid2.st{grid-template-columns:repeat(auto-fit,minmax(min(100%,210px),1fr))}
.grid2.st .plot svg{min-width:200px}
.cellbox h3{font-size:13px;color:var(--ink)}
.cellmap .cell{stroke:#fff;stroke-width:1.2}
.cellmap .cell.b0{fill:#D6ECF9}.cellmap .cell.b1{fill:#A6D4F1}.cellmap .cell.b2{fill:#62B5E5}.cellmap .cell.b3{fill:#2A8CC6}.cellmap .cell.b4{fill:#0B5F98}
.cellmap .cell.e{fill:#fff;stroke:#E69F00;stroke-width:2.6}
.cellmap .cell.z{fill:#F7F8F9;stroke:#D5D9DE;stroke-width:1}
.cellmap .cell:hover{stroke:#1A1A1A;stroke-width:2}
.clab{font-size:11px;fill:#1A1A1A;font-weight:600}.clab.w{fill:#fff}
.clab.rec{font-weight:800;font-size:12.5px;fill:#1A1A1A}
.recbadge{display:inline-grid;place-items:center;width:16px;height:16px;border-radius:50%;background:#1A1A1A;color:#fff;font-size:10.5px;font-weight:700}
.sc .sideblk{min-width:0}
.verdict{display:flex;gap:8px;align-items:flex-start;font-weight:600;font-size:14.5px;line-height:1.4;padding:8px 10px;border-radius:8px;margin-bottom:10px}
.verdict.bad{background:#FBE6DC}.verdict.warn{background:#FCF1DC}.verdict.good{background:#E3F4EE}.verdict .sicon{margin-top:2px}
table.side{border-collapse:separate;border-spacing:4px;width:100%;table-layout:fixed}
table.side caption{text-align:left;font-size:12.5px;color:var(--muted);padding:0 4px 2px}
table.side th{font-size:12.5px;font-weight:600;color:var(--ink2);text-align:center;padding:2px}
table.side tbody th{text-align:right;padding-right:8px;width:30%}
table.side td{text-align:center;border-radius:8px;padding:10px 4px 8px;position:relative;height:84px}
table.side td.skew{outline:3px solid var(--bad);outline-offset:-3px}
table.side .big{display:block;font-size:30px;font-weight:700;line-height:1.1}
table.side .pc{display:block;font-size:12px;opacity:.85}
table.side .sk{position:absolute;top:4px;right:6px;font-size:10.5px;font-weight:700;background:#fff;color:var(--bad);border-radius:4px;padding:0 4px}
.gwrap{margin-top:6px}.glabel{font-size:12.5px;color:var(--ink2)} .gwrap .gauge{max-width:420px}
.cdf{cursor:crosshair}
.cmp{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:4px 28px}
.crow{display:grid;grid-template-columns:minmax(120px,42%) 1fr;gap:10px;align-items:center;padding:5px 0;border-bottom:1px solid #F0F1F3}
.clabel{font-size:13px;line-height:1.3}
.clabel .hint{display:block;font-size:11px;color:var(--muted)}
.cbars{display:grid;gap:3px}
.cbar{display:flex;align-items:center;gap:6px;font-size:12px;font-variant-numeric:tabular-nums}
.cbar .bar{display:inline-block;height:10px;border-radius:0 3px 3px 0;min-width:2px}
.runs{margin-top:14px;border-top:1px solid var(--line);padding-top:12px}
.rtitle{font-weight:600;margin:0 0 2px}
.tctrl{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;margin-bottom:8px;font-size:13px}
.tctrl select,.tctrl input{font:inherit;font-size:13px;border:1px solid #CDD2D8;border-radius:6px;padding:2px 6px;background:#fff}
.tblwrap{max-height:520px;overflow:auto;border:1px solid var(--line);border-radius:8px}
table.eps{border-collapse:collapse;width:100%;font-size:12.5px}
table.eps th{position:sticky;top:0;background:#F7F8FA;text-align:left;font-weight:600;color:var(--ink2);padding:6px 8px;border-bottom:1px solid var(--line);cursor:pointer;white-space:nowrap;user-select:none}
table.eps th.sa::after{content:" ▲";font-size:9px} table.eps th.sd::after{content:" ▼";font-size:9px}
table.eps td{padding:4px 8px;border-bottom:1px solid #F0F1F3;white-space:nowrap}
table.eps td.num,table.eps th.num{text-align:right;font-variant-numeric:tabular-nums}
table.eps tbody tr{cursor:pointer} table.eps tbody tr:hover{background:#F6F8FB}
table.eps tbody tr.sel{background:#FFF3D6}
table.eps img{height:34px;border-radius:3px;display:block}
.oc{display:inline-flex;align-items:center;gap:4px}
.fl{font-size:11px;background:#EEF0F3;border-radius:4px;padding:0 5px;margin-right:3px}
#tip{position:fixed;z-index:50;pointer-events:none;background:#1A1A1A;color:#fff;font-size:12.5px;line-height:1.45;padding:7px 10px;border-radius:7px;max-width:340px;box-shadow:0 4px 14px rgba(0,0,0,.18)}
#tip b{font-weight:700} #tip .k{color:#B9C0C8} #tip img{max-width:180px;border-radius:4px;margin-top:4px;display:block}
body.mapdots #svg-map .arw{display:none}
.rec .rfix{stroke-opacity:.32}.rec:hover .rfix,.rec.on .rfix{stroke-opacity:1;stroke-width:1.6}
.rec.on circle,.rec.on line{filter:drop-shadow(0 0 2px #fff)}
.recs li{cursor:default;border-radius:6px;padding:2px 4px;margin:-2px -4px}.recs li:hover{background:#F4F5F7}
.hlc{pointer-events:none}
footer{margin-top:22px;text-align:center}
@media (max-width:760px){.next{grid-template-columns:1fr}.notes{border-left:0;padding-left:0;border-top:1px solid var(--line);padding-top:10px}
.val{font-size:26px} h1{font-size:19px}}
@media print{body{background:#fff}.wrap{max-width:none;padding:0}.btn,.seg,.tctrl,.tools,#tip,.chev{display:none!important}
details.panel,.card,.next{break-inside:avoid;border-color:#ccc}.tblwrap{max-height:none;overflow:visible;border:0}
table.eps th{position:static}.plot{overflow:visible}.plot svg{min-width:0}}
"""

# ================================================================== JS(바닐라, 라이브러리 없음)
JS = r"""
(function(){
'use strict';
var EP=D.ep, DS=D.ds, ST=D.str, hidden={};
var tip=document.getElementById('tip');
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function fmtT(t){return t?String(t).replace('T',' ').slice(0,16):'—';}
function ocTxt(o){return ST.oc[o||'none']||o;}
function epTip(i){
  var e=EP[i]; if(!e) return '';
  var h='<b>'+esc(e.id)+'</b> <span class="k">· '+esc(DS[e.d]?DS[e.d].n:'')+'</span><br>';
  h+='<span class="k">'+esc(ST['tip.t'])+'</span> '+esc(fmtT(e.t))+'<br>';
  h+='<span class="k">'+esc(ST['tip.outcome'])+'</span> '+esc(ocTxt(e.o))+'<br>';
  if(e.m!=null) h+='<span class="k">'+esc(ST['tip.move'])+'</span> '+e.m.toFixed(0)+' mm<br>';
  if(e.cs!=null||e.cg!=null) h+='<span class="k">'+esc(ST['tip.cells'])+'</span> '+esc(e.cs)+' → '+esc(e.cg);
  for(var j=0;j<(e.k||[]).length;j++){ if(e.k[j]!=null) h+=' · '+esc(ST.strata[j])+' '+esc(e.k[j]); }
  if(e.f&&e.f.length) h+='<br><span class="k">'+esc(ST['col.flags'])+'</span> '+e.f.map(function(f){return esc(ST.flag[f]||f);}).join(', ');
  if(e.th) h+='<img src="'+esc(e.th)+'" alt="">';
  return h;
}
function showTip(html,ev){
  if(!html){hideTip();return;}
  tip.innerHTML=html; tip.hidden=false;
  var x=ev.clientX+14, y=ev.clientY+14, w=tip.offsetWidth, h=tip.offsetHeight;
  if(x+w>window.innerWidth-8) x=ev.clientX-w-14;
  if(y+h>window.innerHeight-8) y=ev.clientY-h-14;
  tip.style.left=Math.max(4,x)+'px'; tip.style.top=Math.max(4,y)+'px';
}
function hideTip(){tip.hidden=true;}

/* ---------- 강조: 같은 에피소드의 모든 표시를 맨 위 층에 복제 */
function paint(i,layer){
  document.querySelectorAll('svg .'+layer).forEach(function(g){g.innerHTML='';});
  if(i==null||i<0) return;
  document.querySelectorAll('svg [data-i="'+i+'"]').forEach(function(el){
    var svg=el.ownerSVGElement, g=svg&&svg.querySelector('.'+layer); if(!g) return;
    var cs=getComputedStyle(el), c=el.cloneNode(false);
    c.removeAttribute('data-i'); c.setAttribute('class','hlc');
    var tag=el.tagName.toLowerCase();
    if(tag==='line'){
      c.style.stroke=cs.stroke; c.style.strokeWidth=layer==='sel-layer'?'3.2':'2.6'; c.style.strokeOpacity='1';
      c.style.markerEnd=cs.markerEnd;
    }else{
      var stroked=(cs.fill==='none');
      c.style.fill=cs.fill==='none'?'none':cs.fill; c.style.fillOpacity='1';
      c.style.stroke=stroked?cs.stroke:'#1A1A1A'; c.style.strokeWidth=stroked?'3':'2';
      if(tag==='circle') c.setAttribute('r',(parseFloat(el.getAttribute('r'))+1.8).toFixed(1));
    }
    g.appendChild(c);
  });
  if(layer==='sel-layer') drawFix(i);
}
function drawFix(i){
  var e=EP[i], svg=document.getElementById('svg-map'); if(!svg||!e||!e.fx||!D.map) return;
  var g=svg.querySelector('.sel-layer'), M=D.map;
  function px(x){return M.sx[2]+(x-M.sx[0])*(M.sx[3]-M.sx[2])/(M.sx[1]-M.sx[0]);}
  function py(y){return M.sy[2]+(y-M.sy[0])*(M.sy[3]-M.sy[2])/(M.sy[1]-M.sy[0]);}
  e.fx.forEach(function(f){
    var a=f[2]*Math.PI/180, u=[Math.cos(a),Math.sin(a)], v=[-u[1],u[0]], pts=[];
    [[1,1],[1,-1],[-1,-1],[-1,1]].forEach(function(s){pts.push(px(f[0]+s[0]*f[3]/2*u[0]+s[1]*f[4]/2*v[0]).toFixed(1)+','+py(f[1]+s[0]*f[3]/2*u[1]+s[1]*f[4]/2*v[1]).toFixed(1));});
    var p=document.createElementNS('http://www.w3.org/2000/svg','polygon');
    p.setAttribute('points',pts.join(' ')); p.setAttribute('fill','none'); p.setAttribute('stroke','#1A1A1A'); p.setAttribute('stroke-width','1.2');
    p.setAttribute('stroke-dasharray','2 2'); p.setAttribute('class','hlc'); g.appendChild(p);
  });
}

/* ---------- 가장 가까운 점 찾기(작은 점도 쉽게 짚게) */
var PTS=[];
document.querySelectorAll('svg.pts').forEach(function(svg){
  var arr=[];
  svg.querySelectorAll('[data-i]').forEach(function(el){
    var tag=el.tagName.toLowerCase(); if(tag==='line') return;
    var x,y;
    if(tag==='circle'){x=+el.getAttribute('cx');y=+el.getAttribute('cy');}
    else{var b=el.getBBox();x=b.x+b.width/2;y=b.y+b.height/2;}
    var i=+el.getAttribute('data-i'); arr.push([x,y,i,EP[i]?EP[i].d:0]);
  });
  PTS.push([svg,arr]);
  var last=-1;
  svg.addEventListener('mousemove',function(ev){
    var ctm=svg.getScreenCTM(); if(!ctm) return;
    var pt=svg.createSVGPoint(); pt.x=ev.clientX; pt.y=ev.clientY; pt=pt.matrixTransform(ctm.inverse());
    var lim=12/ctm.a, best=-1, bd=lim*lim;
    for(var k=0;k<arr.length;k++){ var q=arr[k]; if(hidden[q[3]]) continue;
      var dx=q[0]-pt.x, dy=q[1]-pt.y, d=dx*dx+dy*dy; if(d<bd){bd=d;best=q[2];} }
    if(best>=0){ if(best!==last){paint(best,'hl-layer');last=best;} showTip(epTip(best),ev); svg.style.cursor='pointer'; }
    else if(!ev.target.closest('[data-tip]')){ if(last>=0){paint(-1,'hl-layer');last=-1;} hideTip(); svg.style.cursor=''; }
  });
  svg.addEventListener('mouseleave',function(){paint(-1,'hl-layer');last=-1;hideTip();});
  svg.addEventListener('click',function(){ if(last>=0) select(last,false); });
});

/* ---------- 일반 말풍선(data-tip) */
document.addEventListener('mouseover',function(ev){
  var t=ev.target.closest&&ev.target.closest('[data-tip]');
  if(t){ showTip(esc(t.getAttribute('data-tip')).replace(/\n/g,'<br>'),ev); }
});
document.addEventListener('mousemove',function(ev){
  var t=ev.target.closest&&ev.target.closest('[data-tip]');
  if(t) showTip(esc(t.getAttribute('data-tip')).replace(/\n/g,'<br>'),ev);
});
document.addEventListener('mouseout',function(ev){ var t=ev.target.closest&&ev.target.closest('[data-tip]'); if(t) hideTip(); });

/* ---------- 칸 지도: 켠 데이터셋만 세어 진하기 다시 */
function cellsPaint(){
  if(!D.cells) return;
  var E=D.cells.edges;
  ['start','goal'].forEach(function(role){
    var info=D.cells[role]; if(!info) return;
    var svg=document.querySelector('svg.cellmap[data-role="'+role+'"]'); if(!svg) return;
    var keys=Object.keys(info.by);
    svg.querySelectorAll('polygon.cell').forEach(function(p){
      var j=+p.getAttribute('data-c'), n=0, parts=[];
      keys.forEach(function(k){ var v=info.by[k][j]||0; if(k==='all'||!hidden[+k]){ n+=v; if(k!=='all'&&v) parts.push(DS[+k].n+' '+v); } });
      var reach=p.getAttribute('data-reach')==='1', cls='cell';
      if(n>0){ var b=0; for(var q=0;q<E.length;q++){ if(n>=E[q]) b=q; } cls+=' b'+b; }
      else cls+= reach?' e':' z';
      p.setAttribute('class',cls);
      var tipT=ST['cells.tip'].replace('{k}',j)+'\n'+n+' '+ST['episodes_unit']+(parts.length?' ('+parts.join(' · ')+')':'')+'\n'+(reach?ST['cells.reach_yes']:ST['cells.reach_no']);
      p.setAttribute('data-tip',tipT);
      var lab=svg.querySelector('text.clab[data-c="'+j+'"]');
      if(lab){ lab.textContent=n>0?String(n):''; lab.setAttribute('class','clab'+(n>=E[Math.min(3,E.length-1)]?' w':'')); }
    });
  });
}

/* ---------- 데이터셋 켜기/끄기 */
document.querySelectorAll('.dschip input').forEach(function(cb){
  cb.addEventListener('change',function(){
    var k=+cb.getAttribute('data-d'); hidden[k]=!cb.checked;
    document.body.classList.toggle('off-d'+k,!cb.checked);
    cellsPaint(); renderTable();
  });
});
/* ---------- 지도: 화살표/점만 */
document.querySelectorAll('[data-mapmode]').forEach(function(b){
  b.addEventListener('click',function(){
    document.querySelectorAll('[data-mapmode]').forEach(function(x){x.classList.toggle('on',x===b);});
    document.body.classList.toggle('mapdots',b.getAttribute('data-mapmode')==='dots');
  });
});
/* ---------- 지름길: 짝 바꾸기, 쪽 표 데이터셋 바꾸기 */
document.querySelectorAll('[data-pairbtn]').forEach(function(b){
  b.addEventListener('click',function(){
    var k=b.getAttribute('data-pairbtn');
    document.querySelectorAll('[data-pairbtn]').forEach(function(x){x.classList.toggle('on',x===b);});
    document.querySelectorAll('.scwrap').forEach(function(w){var on=w.getAttribute('data-pair')===k; w.hidden=!on; var s=w.querySelector('svg'); if(s) s.style.display=on?'':'none';});
  });
});
document.querySelectorAll('[data-sidebtn]').forEach(function(b){
  b.addEventListener('click',function(){
    var k=b.getAttribute('data-sidebtn');
    document.querySelectorAll('[data-sidebtn]').forEach(function(x){x.classList.toggle('on',x===b);});
    document.querySelectorAll('.spane').forEach(function(p){p.hidden=p.getAttribute('data-pane')!==k;});
  });
});
/* ---------- 누적 분포: 십자선 */
document.querySelectorAll('svg.cdf').forEach(function(svg){
  var X=svg.getAttribute('data-x').split(',').map(Number), Y=svg.getAttribute('data-y').split(',').map(Number);
  var xh=svg.querySelector('.xh');
  var by={}; EP.forEach(function(e){ if(e.m!=null){ (by[e.d]=by[e.d]||[]).push(e.m);} });
  Object.keys(by).forEach(function(k){by[k].sort(function(a,b){return a-b;});});
  svg.addEventListener('mousemove',function(ev){
    var ctm=svg.getScreenCTM(); if(!ctm) return;
    var pt=svg.createSVGPoint(); pt.x=ev.clientX; pt.y=ev.clientY; pt=pt.matrixTransform(ctm.inverse());
    if(pt.x<X[2]||pt.x>X[3]||pt.y<Y[0]||pt.y>Y[1]){ xh.setAttribute('x1',-10); xh.setAttribute('x2',-10); return; }
    var mm=X[0]+(pt.x-X[2])*(X[1]-X[0])/(X[3]-X[2]);
    xh.setAttribute('x1',pt.x); xh.setAttribute('x2',pt.x);
    var h='<b>≤ '+mm.toFixed(0)+' mm</b>';
    Object.keys(by).forEach(function(k){ if(hidden[+k]) return; var a=by[k], n=0; while(n<a.length&&a[n]<=mm) n++;
      h+='<br><span class="k">'+esc(DS[+k].n)+'</span> '+(100*n/a.length).toFixed(0)+'% ('+n+'/'+a.length+')'; });
    showTip(h,ev);
  });
  svg.addEventListener('mouseleave',function(){ xh.setAttribute('x1',-10); xh.setAttribute('x2',-10); hideTip(); });
});

/* ---------- 에피소드 표 */
var tbl=document.getElementById('eps'), sortK='t', sortD=1, SEL=-1;
var cols=tbl?Array.prototype.map.call(tbl.querySelectorAll('thead th'),function(th){return th.getAttribute('data-col');}):[];
function val(e,k){
  if(k==='id') return e.id; if(k==='d') return e.d; if(k==='t') return e.t||''; if(k==='o') return e.o||'';
  if(k==='s') return e.s?e.s[0]:-1e9; if(k==='g') return e.g?e.g[0]:-1e9; if(k==='m') return e.m==null?-1:e.m;
  if(k==='c') return e.cs==null?-1:e.cs; if(k==='f') return (e.f||[]).join(',');
  if(k&&k[0]==='k') { var v=(e.k||[])[+k.slice(1)]; return v==null?'':v; }
  return '';
}
function ocCell(o){ var c=D.ocol[o||'none']||'#999';
  var shape={success:'<circle cx="6" cy="6" r="4.5" fill="'+c+'"/>',fail:'<path d="M2,2L10,10M2,10L10,2" stroke="'+c+'" stroke-width="2"/>',
    unsure:'<path d="M6,1L11,10.5H1Z" fill="'+c+'"/>'}[o]||'<circle cx="6" cy="6" r="4" fill="none" stroke="'+c+'" stroke-width="1.6"/>';
  return '<span class="oc"><svg width="12" height="12" aria-hidden="true">'+shape+'</svg>'+esc(ocTxt(o))+'</span>'; }
function renderTable(){
  if(!tbl) return;
  var fd=document.getElementById('f-ds').value, fo=document.getElementById('f-oc').value, ff=document.getElementById('f-fl').value,
      fq=(document.getElementById('f-q').value||'').toLowerCase();
  var idx=[];
  for(var i=0;i<EP.length;i++){ var e=EP[i];
    if(hidden[e.d]) continue; if(fd!==''&&String(e.d)!==fd) continue; if(fo!==''&&(e.o||'none')!==fo) continue;
    if(ff==='-'&&e.f&&e.f.length) continue; if(ff!==''&&ff!=='-'&&(e.f||[]).indexOf(ff)<0) continue;
    if(fq&&String(e.id).toLowerCase().indexOf(fq)<0) continue; idx.push(i); }
  idx.sort(function(a,b){ var x=val(EP[a],sortK), y=val(EP[b],sortK); return (x<y?-1:x>y?1:a-b)*sortD; });
  var h=[];
  idx.forEach(function(i){ var e=EP[i], r='<tr data-r="'+i+'"'+(i===SEL?' class="sel"':'')+'>';
    cols.forEach(function(k){
      if(k==='thumb') r+='<td>'+(e.th?'<img src="'+esc(e.th)+'" alt="">':'')+'</td>';
      else if(k==='id') r+='<td>'+esc(e.id)+'</td>';
      else if(k==='d') r+='<td><span class="sw" style="background:'+DS[e.d].c+'"></span> '+esc(DS[e.d].n)+'</td>';
      else if(k==='t') r+='<td>'+esc(fmtT(e.t))+'</td>';
      else if(k==='o') r+='<td>'+ocCell(e.o)+'</td>';
      else if(k==='s') r+='<td>'+(e.s?e.s[0].toFixed(0)+', '+e.s[1].toFixed(0):'—')+'</td>';
      else if(k==='g') r+='<td>'+(e.g?e.g[0].toFixed(0)+', '+e.g[1].toFixed(0):'—')+'</td>';
      else if(k==='m') r+='<td class="num">'+(e.m==null?'—':e.m.toFixed(0))+'</td>';
      else if(k==='c') r+='<td>'+esc(e.cs==null?'—':e.cs)+' → '+esc(e.cg==null?'—':e.cg)+'</td>';
      else if(k==='f') r+='<td>'+(e.f||[]).map(function(f){return '<span class="fl">'+esc(ST.flag[f]||f)+'</span>';}).join('')+'</td>';
      else if(k&&k[0]==='k'){ var v=(e.k||[])[+k.slice(1)]; r+='<td>'+esc(v==null?'—':v)+'</td>'; }
    });
    h.push(r+'</tr>'); });
  tbl.tBodies[0].innerHTML=h.join('');
  document.getElementById('f-count').textContent=ST['tbl.shown'].replace('{n}',EP.length).replace('{m}',idx.length);
}
function select(i,scroll){
  SEL=(SEL===i)?-1:i; paint(SEL,'sel-layer');
  var chip=document.querySelector('.selchip');
  if(chip){ chip.hidden=SEL<0; var s=chip.querySelector('.selid'); if(s) s.textContent=SEL>=0?EP[SEL].id:''; }
  if(tbl) tbl.querySelectorAll('tbody tr').forEach(function(r){ r.classList.toggle('sel',+r.getAttribute('data-r')===SEL); });
  if(scroll&&SEL>=0){ var m=document.getElementById('p-map'); if(m){ m.open=true; var rc=m.getBoundingClientRect();
    if(rc.bottom<60||rc.top>window.innerHeight-60) m.scrollIntoView({behavior:'smooth',block:'start'}); } }
}
if(tbl){
  tbl.querySelectorAll('thead th').forEach(function(th){
    th.addEventListener('click',function(){ var k=th.getAttribute('data-col'); if(k==='thumb') return;
      if(sortK===k) sortD=-sortD; else {sortK=k; sortD=1;}
      tbl.querySelectorAll('thead th').forEach(function(x){x.classList.remove('sa','sd');}); th.classList.add(sortD>0?'sa':'sd');
      renderTable(); });
  });
  ['f-ds','f-oc','f-fl','f-q'].forEach(function(id){ var el=document.getElementById(id); el.addEventListener(id==='f-q'?'input':'change',renderTable); });
  tbl.tBodies[0].addEventListener('click',function(ev){ var tr=ev.target.closest('tr'); if(tr) select(+tr.getAttribute('data-r'),true); });
  tbl.tBodies[0].addEventListener('mouseover',function(ev){ var tr=ev.target.closest('tr'); if(tr) paint(+tr.getAttribute('data-r'),'hl-layer'); });
  tbl.tBodies[0].addEventListener('mouseleave',function(){ paint(-1,'hl-layer'); });
  var th0=tbl.querySelector('thead th[data-col="t"]'); if(th0) th0.classList.add('sa');
}
var bc=document.getElementById('sel-clear'); if(bc) bc.addEventListener('click',function(){ if(SEL>=0) select(SEL,false); });
var bb=document.getElementById('sel-back'); if(bb) bb.addEventListener('click',function(){ var t=document.getElementById('p-table'); if(t){t.open=true; t.scrollIntoView({behavior:'smooth',block:'start'});} });
document.querySelectorAll('.recs li[data-rec]').forEach(function(li){
  var k=li.getAttribute('data-rec'), g=document.querySelector('svg .rec[data-rec="'+k+'"]'); if(!g) return;
  li.addEventListener('mouseenter',function(){g.classList.add('on');}); li.addEventListener('mouseleave',function(){g.classList.remove('on');});
});
var bp=document.getElementById('btn-print'); if(bp) bp.addEventListener('click',function(){window.print();});
window.addEventListener('beforeprint',function(){ document.querySelectorAll('details.panel').forEach(function(d){d.open=true;}); });
cellsPaint(); renderTable();
})();
"""
