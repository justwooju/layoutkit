"""fr5rec 어댑터 — 데이터셋 폴더(ep_*/meta.json) · 받침 꼬리표 JSON · 특징 묶음(feat.json).

형식은 FR5-AutoCollect docs/DATA.md 2·3절. 읽는 순서(에피소드마다):
  1) 꼬리표 fr5rec.tag 에 red_xy·slot_xy 가 있으면(받침 과제) 그것이 start/goal — fr5auto rackrec.ep_record 와 같다.
     src·dst = [받침, 구멍] → discrete start_slot·goal_slot·start_fixture·goal_fixture·same_fixture,
     yellow_at(빨강과 같은 받침일 때) → obstacle_slot·arrangement(예: Y○○R, 구멍 0 부터), 없으면 scene 문자열의 그 받침 기호.
     racks → fixtures. yaw = params.yaw_g/yaw_i(계획 손목) → 없으면 task_yaw_deg(rackrec 과 같은 짐작).
  2) 꼬리표에 rec_theta 만 있고 pitch_mm 를 주면 구멍 자리를 계산(rackrec.hole_xy 와 같은 식).
  3) 아니면 frames[].tcp_base_mm_deg(베이스 mm, °)·grip_width(m, 0.04 = 다 엶) 궤적 → events.detect.
버린 판(_discarded/)·기록 중(ep_NNN.part/)은 읽지 않는다. 드라이런 꼬리표(dry)는 뺀다.
"""
from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path

import numpy as np

from .. import events as EV
from ..data import episode
from . import display_path, make_dataset

EP_RE = re.compile(r"^ep_\d+$")
SCENE_RE = re.compile(r"받침(\d+)\[([^\]]*)\]")


def _num(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def arrangement(kr, ky, n=4) -> str:
    """받침 위 빨강·노랑 배치 글자(구멍 0 부터) — rackrec.arrangement 그대로."""
    s = ["○"] * n
    if ky is not None and 0 <= int(ky) < n:
        s[int(ky)] = "Y"
    if kr is not None and 0 <= int(kr) < n:
        s[int(kr)] = "R"
    return "".join(s)


def scene_symbols(scene) -> dict:
    """'받침0[○○·○]  받침1[Y○○R]' → {0: '○○·○', 1: 'Y○○R'}."""
    out = {}
    for m in SCENE_RE.finditer(str(scene or "")):
        out[int(m.group(1))] = m.group(2)
    return out


def hole_xy(x, y, psi, k, pitch, n=4):
    """구멍 k 의 xy: h = p + (k − (n−1)/2)·간격·(cos ψ, sin ψ) — rackrec.hole_xy 와 같은 식."""
    s = (float(k) - (n - 1) / 2.0) * float(pitch)
    r = math.radians(float(psi))
    return [float(x) + s * math.cos(r), float(y) + s * math.sin(r)]


def _iso(t):
    if t is None:
        return None
    if isinstance(t, str):
        return t
    f = _num(t)
    return None if f is None else time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(f))


def first_image(ep_dir, meta=None):
    """첫 3인칭 사진(rackrec.first_image 와 같은 곳을 본다)."""
    if ep_dir is None:
        return None
    cam = ((((meta or {}).get("fr5rec") or {}).get("camera") or {}).get("third") or {}).get("dir")
    for nm in ([cam] if cam else []) + ["rgb", "third"]:
        for ext in (".png", ".jpg"):
            p = Path(ep_dir) / str(nm) / f"00000{ext}"
            if p.is_file():
                return p
    p = Path(ep_dir) / "third_00000.png"
    return p if p.is_file() else None


def _from_tag(meta, tag, pitch_mm=None, n_slots=4):
    """꼬리표 → (start, goal, discrete, fixtures, how) 또는 None."""
    red, slot = tag.get("red_xy"), tag.get("slot_xy")
    src, dst = tag.get("src"), tag.get("dst")
    racks = tag.get("racks") if isinstance(tag.get("racks"), list) else None
    th = tag.get("rec_theta") if isinstance(tag.get("rec_theta"), dict) else None
    how = "tag"
    if not (isinstance(red, list) and isinstance(slot, list) and len(red) >= 2 and len(slot) >= 2):
        if th is None or pitch_mm is None:
            return None
        try:                                                        # 추천 배치 θ 로 구멍 자리를 계산(실제 놓인 자리가 아니라 목표)
            R_ = th["racks"]
            a, b, kr, kg = int(th["a"]), int(th["b"]), int(th["kr"]), int(th["kg"])
            red = hole_xy(R_[a]["x"], R_[a]["y"], R_[a].get("psi", R_[a].get("yaw", 0.0)), kr, pitch_mm, n_slots)
            slot = hole_xy(R_[b]["x"], R_[b]["y"], R_[b].get("psi", R_[b].get("yaw", 0.0)), kg, pitch_mm, n_slots)
            src, dst = src or [a, kr], dst or [b, kg]
            racks = racks or [{"x": r["x"], "y": r["y"], "yaw": r.get("psi", r.get("yaw"))} for r in R_]
            if tag.get("yellow_at") is None and th.get("ky") is not None:
                tag = dict(tag, yellow_at=[a, int(th["ky"])])
            how = "rec_theta"
        except (KeyError, TypeError, ValueError, IndexError):
            return None
    params = tag.get("params") if isinstance(tag.get("params"), dict) else {}
    yaw_g = _num(params.get("yaw_g"))
    yaw_i = _num(params.get("yaw_i"))
    ty = _num((meta or {}).get("task_yaw_deg"))
    start = {"x": float(red[0]), "y": float(red[1])}
    goal = {"x": float(slot[0]), "y": float(slot[1])}
    if yaw_g is not None or ty is not None:
        start["yaw"] = yaw_g if yaw_g is not None else ty
    if yaw_i is not None or ty is not None or yaw_g is not None:
        goal["yaw"] = yaw_i if yaw_i is not None else (yaw_g if yaw_g is not None else ty)
    zg, zi = _num(params.get("zg")), _num(params.get("zi"))
    if zg is not None:
        start["z"] = zg
    if zi is not None:
        goal["z"] = zi
    disc = {}
    a = b = None
    if isinstance(src, (list, tuple)) and len(src) >= 2:
        a = int(src[0])
        disc.update(start_fixture=a, start_slot=int(src[1]))
    if isinstance(dst, (list, tuple)) and len(dst) >= 2:
        b = int(dst[0])
        disc.update(goal_fixture=b, goal_slot=int(dst[1]))
    if a is not None and b is not None:
        disc["same_fixture"] = bool(a == b)
    ya = tag.get("yellow_at")
    ky = None
    if isinstance(ya, (list, tuple)) and len(ya) >= 2 and a is not None and int(ya[0]) == a:
        ky = int(ya[1])
        disc["obstacle_slot"] = ky
    if "start_slot" in disc and ky is not None:
        disc["arrangement"] = arrangement(disc["start_slot"], ky, n_slots)
    elif a is not None:
        sym = scene_symbols(tag.get("scene")).get(a)
        if sym:
            disc["arrangement"] = sym
    fixtures = []
    for i, r in enumerate(racks or []):
        try:
            fixtures.append({"name": f"rack{i}", "x": float(r["x"]), "y": float(r["y"]), "yaw": float(r.get("yaw", r.get("psi")))})
        except (KeyError, TypeError, ValueError):
            pass
    return start, goal, disc, fixtures, how


def _from_frames(frames, ev_opt):
    """frames[] → events.detect 결과(없으면 None)."""
    xyz, yaw, g, t = [], [], [], []
    for f in frames or []:
        tc = f.get("tcp_base_mm_deg")
        gw = f.get("grip_width")
        if not (isinstance(tc, list) and len(tc) >= 3) or _num(gw) is None:
            continue
        xyz.append([float(tc[0]), float(tc[1]), float(tc[2])])
        yaw.append(float(tc[5]) if len(tc) >= 6 and _num(tc[5]) is not None else np.nan)
        g.append(float(gw))
        t.append(_num(f.get("t")))
    if len(xyz) < 2:
        return None
    tt = None if any(v is None for v in t) else np.asarray(t, float)
    o = {"units": "mm", "yaw_units": "deg", "closed_is": "low", "hz": None}
    o.update(ev_opt or {})
    Y = np.asarray(yaw, float)
    ev = EV.detect(tt, np.asarray(xyz, float), np.asarray(g, float), Y if np.isfinite(Y).any() else None, **o)
    ev["t0"] = float(tt[0]) if tt is not None else 0.0
    return ev


def episode_from_meta(meta, ep="ep", ep_dir=None, use_tags=True, pitch_mm=None, n_slots=4, thumbs=True, events=None):
    """fr5rec meta(또는 그 일부) → 에피소드 dict(자리를 못 찾으면 start/goal None — 분석에서 '못 씀')."""
    meta = meta or {}
    fr = meta.get("fr5rec") or {}
    tag = fr.get("tag") or {}
    if tag.get("dry"):
        return None
    start = goal = None
    disc, fixtures, extra = {}, [], {}
    how = None
    if use_tags and tag:
        r = _from_tag(meta, tag, pitch_mm, n_slots)
        if r is not None:
            start, goal, disc, fixtures, how = r
    frames = meta.get("frames") if isinstance(meta.get("frames"), list) else None
    if start is None and frames:
        ev = _from_frames(frames, events)
        if ev is not None:
            extra["path_mm"] = ev["path_mm"]
            if ev["ok"]:
                start, goal, how = ev["start"], ev["goal"], "events"
                extra["t_pick_s"] = ev["t_pick"] - ev["t0"]
                extra["t_place_s"] = ev["t_place"] - ev["t0"]
            extra["n_grasps"] = len(ev["segments"])
    if frames:
        extra["n_frames"] = len(frames)
    dur = _num(meta.get("duration_s"))
    if dur is None and frames and len(frames) > 1:
        t0, t1 = _num(frames[0].get("t")), _num(frames[-1].get("t"))
        dur = (t1 - t0) if (t0 is not None and t1 is not None) else None
    if dur is not None:
        extra["duration_s"] = dur
    scene = meta.get("scene")
    if isinstance(scene, dict):                                     # 세션 조건 값
        for k, v in scene.items():
            if isinstance(v, (str, int, bool)) or (isinstance(v, float) and math.isfinite(v)):
                disc.setdefault(str(k), v)
    t = fr.get("started_at") or (_iso(frames[0].get("t")) if frames else None)
    th = {}
    if thumbs:
        img = first_image(ep_dir, meta)
        if img is not None:
            th["third"] = display_path(img.resolve())
    e = episode(ep, "", start, goal, t=_iso(t), outcome=meta.get("outcome"), source="fr5rec", discrete=disc,
                fixtures=fixtures, extra=extra, thumbs=th)
    e["_how"] = how or "none"                                       # 자리 출처 — load 가 데이터셋 meta 로 옮기고 지운다
    return e


def _load_dir(p: Path, opt):
    eps = []
    for d in sorted(c for c in p.iterdir() if c.is_dir() and EP_RE.match(c.name) and (c / "meta.json").is_file()):
        try:
            m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        e = episode_from_meta(m, d.name, d, **opt)
        if e is not None:
            eps.append(e)
    return eps


def _load_tags(d, opt):
    eps = []
    for i, r in enumerate(d.get("episodes") or []):
        o = dict(opt, thumbs=False)
        e = episode_from_meta(r.get("meta") or {}, str(r.get("ep") or f"ep_{i:03d}"), None, **o)
        if e is not None:
            eps.append(e)
    return eps


def _load_feat(d):
    """특징 묶음(fr5lens·rackrec 내보낸 것: R·S·Y·src·dst·t0) → 에피소드. 받침 꼬리표에서 뽑은 숫자와 같다."""
    n = len(d["R"])
    Y = d.get("Y") or [None] * n
    src = d.get("src") or [None] * n
    dst = d.get("dst") or [None] * n
    t0 = d.get("t0") or [None] * n
    eps = []
    for i in range(n):
        st = {"x": d["R"][i][0], "y": d["R"][i][1]}
        gl = {"x": d["S"][i][0], "y": d["S"][i][1]}
        if Y[i] is not None:
            st["yaw"] = gl["yaw"] = float(Y[i])
        disc = {}
        if src[i] is not None:
            disc.update(start_fixture=int(src[i][0]), start_slot=int(src[i][1]))
        if dst[i] is not None:
            disc.update(goal_fixture=int(dst[i][0]), goal_slot=int(dst[i][1]))
        if src[i] is not None and dst[i] is not None:
            disc["same_fixture"] = bool(int(src[i][0]) == int(dst[i][0]))
        eps.append(episode(f"ep_{i:03d}", "", st, gl, t=t0[i], outcome="success", source="fr5rec", discrete=disc))
    return eps


def load(path, name=None, weight=1.0, use_tags=True, pitch_mm=None, n_slots=4, thumbs=True, events=None, **_):
    """fr5rec 폴더·꼬리표 JSON·feat.json → Dataset.
    pitch_mm: rec_theta 만 있는 꼬리표를 구멍 자리로 바꿀 때 구멍 간격. events: events.detect 옵션(dict)."""
    p = Path(path).expanduser()
    opt = {"use_tags": use_tags, "pitch_mm": pitch_mm, "n_slots": n_slots, "thumbs": thumbs, "events": events}
    meta = {"kind": "fr5rec", "path": display_path(p.resolve() if p.exists() else p)}
    if p.is_dir():
        eps = _load_dir(p, opt)
        nm = name or p.name
    else:
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, dict) and "R" in d and "S" in d:
            eps = _load_feat(d)
            meta["form"] = "feat"
        elif isinstance(d, dict) and isinstance(d.get("frames"), list):
            eps = [e for e in [episode_from_meta(d, p.parent.name or "ep_000", p.parent, **opt)] if e]
            meta["form"] = "meta"
        else:
            eps = _load_tags(d, opt)
            meta["form"] = "tags"
            if d.get("note"):
                meta["note"] = str(d["note"])
        nm = name or (Path(str(d.get("dataset"))).name if isinstance(d, dict) and d.get("dataset") else p.stem)
    how = {}
    for e in eps:
        h = e.pop("_how", "none")
        how[h] = how.get(h, 0) + 1
    meta["how"] = how                                               # 자리 출처별 에피소드 수(tag · rec_theta · events · none)
    return make_dataset(nm, eps, weight=weight, meta=meta)
