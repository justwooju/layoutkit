"""폴더 감시 — 데이터 폴더의 지문(파일 이름·크기·수정 시각)이 바뀌면 분석·(추천)·화면을 다시 만든다.

지문은 형식마다 필요한 파일만 본다(사진 수만 장을 매번 훑지 않게):
  fr5rec   ep_*/meta.json(버린 판 _discarded/·기록 중 ep_NNN.part/ 는 빼고)
  lerobot  meta/*.json(l) · data/**/*.parquet
  파일     그 파일 하나 · 그 밖의 폴더는 2단계 깊이까지의 .json·.jsonl·.csv·.parquet
바뀐 지문은 다음 확인에서도 같을 때(settle 번 연속) 다시 만든다 — 쓰는 중인 파일을 반쯤 읽지 않게. 첫 번은 바로 만든다.
끝: --once(한 번) · max_builds · max_checks · until_n(쓴 에피소드 수가 이만큼 되면) · stop_file(이 파일이 생기면).
알림 파일(notify): 만들 때마다 {"t", "builds", "fingerprint", "n_used", "cards": [[id, status, value]], "error"} 를 쓴다.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from ..adapters import parse_arg

SUFFIX = (".json", ".jsonl", ".csv", ".parquet")


def _stat(p: Path, root: Path):
    try:
        st = p.stat()
        return (str(p.relative_to(root)) if p != root else p.name, st.st_size, st.st_mtime_ns)
    except OSError:
        return None


def fingerprint_one(path) -> list:
    p = Path(path).expanduser()
    if p.is_file():
        s = _stat(p, p)
        return [s] if s else []
    if not p.is_dir():
        return [("missing", str(p))]
    out = []
    eps = [c for c in p.iterdir() if c.is_dir() and c.name.startswith("ep_") and not c.name.endswith(".part")]
    if eps:
        for c in eps:
            s = _stat(c / "meta.json", p)
            if s:
                out.append(s)
        return sorted(out)
    if (p / "meta" / "info.json").is_file():
        for q in list((p / "meta").glob("*.json*")) + list(p.glob("data/**/*.parquet")):
            s = _stat(q, p)
            if s:
                out.append(s)
        return sorted(out)
    for dirpath, dirnames, filenames in os.walk(p):
        depth = Path(dirpath).relative_to(p).parts
        dirnames[:] = [d for d in dirnames if not d.startswith("_discarded") and not d.endswith(".part") and len(depth) < 2]
        for fn in filenames:
            if fn.endswith(SUFFIX) and not fn.endswith(".tmp"):
                s = _stat(Path(dirpath) / fn, p)
                if s:
                    out.append(s)
    return sorted(out)


def fingerprint(paths) -> str:
    h = hashlib.sha1()
    for x in paths:
        _, p = parse_arg(str(x))
        h.update(json.dumps([str(p), fingerprint_one(p)], ensure_ascii=False).encode())
    return h.hexdigest()


def _notify(path, state):
    if not path:
        return
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)
    except OSError:
        pass


def watch(paths, build_fn, every=5.0, settle=1, once=False, max_builds=None, max_checks=None, until_n=None, stop_file=None,
          notify=None, say=print, sleep=time.sleep) -> dict:
    """paths 를 감시하며 바뀌면 build_fn() 을 부른다(build_fn 은 result 를 돌려준다). 반환 마지막 상태."""
    state = {"t": None, "builds": 0, "checks": 0, "fingerprint": None, "n_used": None, "cards": [], "error": None, "stopped": None}
    built, pending, same = None, None, 0
    while True:
        fp = fingerprint(paths)
        state["checks"] += 1
        if fp != built:
            if built is None or fp == pending:
                same += 1
            else:
                pending, same = fp, 0
            if built is None or same >= settle or once:
                try:
                    res = build_fn()
                    built, pending, same = fp, None, 0
                    state.update(t=time.strftime("%Y-%m-%dT%H:%M:%S"), fingerprint=fp, error=None,
                                 n_used=sum(d.get("n_used", 0) for d in res.get("datasets") or []),
                                 cards=[[c["id"], c["status"], c["value"]] for c in res.get("cards") or []])
                    state["builds"] += 1
                    say(f"[{state['t']}] 다시 만듦 #{state['builds']} — 쓴 에피소드 {state['n_used']}")
                except Exception as e:                               # 쓰는 중인 파일 등 — 다음 확인에서 다시
                    state["error"] = f"{type(e).__name__}: {e}"
                    say(f"[{time.strftime('%H:%M:%S')}] 못 만듦: {state['error']}")
                    if once:
                        state["stopped"] = "once"
                        _notify(notify, state)
                        return state
                _notify(notify, state)
        stop = None
        if once:
            stop = "once"
        elif max_builds is not None and state["builds"] >= int(max_builds):
            stop = "max_builds"
        elif max_checks is not None and state["checks"] >= int(max_checks):
            stop = "max_checks"
        elif until_n is not None and (state["n_used"] or 0) >= int(until_n):
            stop = "until_n"
        elif stop_file and Path(stop_file).expanduser().exists():
            stop = "stop_file"
        if stop:
            state["stopped"] = stop
            _notify(notify, state)
            say(f"감시 끝: {stop}")
            return state
        sleep(float(every))
