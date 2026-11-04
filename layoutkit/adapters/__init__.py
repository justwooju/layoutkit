"""데이터 → Dataset. 형식 자동 판별: load_dataset(path, kind="auto", name=None, weight=1.0, **opt).

kind:
  fr5rec        fr5rec 데이터셋 폴더(ep_*/meta.json) · 받침 꼬리표 JSON({"episodes": [{"ep", "meta"}]}) · 특징 묶음(feat.json: R·S·Y·src·dst)
  lerobot       LeRobot v2.x 폴더(meta/info.json) — pyarrow 필요
  table         CSV · JSON · JSONL 표(에피소드 한 줄) — 열 대응은 map={"start.x": "red_x", ...}
  fr5auto_runs  fr5auto 실행 기록(work/runs.jsonl · data/real/runs_*.csv) → Runs(실행 기록 목록, Dataset 아님)
"""
from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path

from ..data import Dataset

KINDS = ("fr5rec", "lerobot", "table", "fr5auto_runs")


class Runs(list):
    """수집 실행 기록(한 줄 = 실행 한 번 dict). analyze(..., runs=) 가 받는다."""

    def __init__(self, rows=(), name="runs", path=None):
        super().__init__(rows)
        self.name = str(name)
        self.path = path


HOME_RE = re.compile(r"^(/home/[^/]+|/Users/[^/]+|[A-Za-z]:\\Users\\[^\\]+)(?=$|[/\\])")


def display_path(p) -> str:
    """화면·결과에 쓰는 경로 — 지금 폴더 아래면 상대 경로, 집 폴더(/home/<계정> 등)는 ~ 로 가린다(공개 저장소·공유 화면에
    계정 이름이 안 나오게). 읽을 때는 Path(...).expanduser() 로 되돌린다."""
    s = str(p)
    try:
        rel = os.path.relpath(s, os.getcwd())
        if not rel.startswith(".."):
            return rel
    except ValueError:
        pass
    home = os.path.expanduser("~")
    if home and home != "/" and (s == home or s.startswith(home + os.sep)):
        return "~" + s[len(home):]
    return HOME_RE.sub("~", s)


def _peek_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def detect_kind(path) -> str:
    """경로 → kind(못 알면 ValueError)."""
    p = Path(path).expanduser()
    if p.is_dir():
        if (p / "meta" / "info.json").is_file():
            return "lerobot"
        if any(c.is_dir() and c.name.startswith("ep_") and (c / "meta.json").is_file() for c in p.iterdir()):
            return "fr5rec"
        if (p / "runs.jsonl").is_file() or (p / "work" / "runs.jsonl").is_file() or list(p.glob("runs_*.csv")):
            return "fr5auto_runs"
        raise ValueError(f"{display_path(p)}: 형식을 모르는 폴더(ep_*/meta.json 도 meta/info.json 도 없다)")
    if not p.is_file():
        raise FileNotFoundError(f"{display_path(p)}: 없다")
    suf = p.suffix.lower()
    if suf == ".json":
        d = _peek_json(p)
        if isinstance(d, dict):
            eps = d.get("episodes")
            if isinstance(eps, list) and eps and isinstance(eps[0], dict) and isinstance(eps[0].get("meta"), dict):
                return "fr5rec"
            if "R" in d and "S" in d:
                return "fr5rec"
            if isinstance(d.get("frames"), list):                     # meta.json 하나
                return "fr5rec"
        return "table"
    if suf == ".jsonl":
        try:
            with p.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        r = json.loads(line)
                        if isinstance(r, dict) and r.get("kind") in ("run", "plan", "reset"):
                            return "fr5auto_runs"
                        break
        except (OSError, ValueError):
            pass
        return "table"
    if suf in (".csv", ".tsv"):
        try:
            with p.open(encoding="utf-8", newline="") as f:
                head = next(csv.reader(f), [])
        except OSError:
            head = []
        h = {c.strip() for c in head}
        if {"time", "verdict"} <= h and ({"exec_s", "decided_by"} & h):
            return "fr5auto_runs"
        return "table"
    if suf == ".parquet":
        raise ValueError(f"{display_path(p)}: parquet 파일 하나는 읽지 않는다 — LeRobot 폴더(meta/info.json 이 있는 곳)를 준다")
    raise ValueError(f"{display_path(p)}: 모르는 확장자 {suf}")


def load_dataset(path, kind="auto", name=None, weight=1.0, **opt):
    """경로 → Dataset(실행 기록이면 Runs). opt 는 어댑터마다(각 모듈 load 의 인자)."""
    k = detect_kind(path) if kind in (None, "auto") else kind
    if k not in KINDS:
        raise ValueError(f"kind 는 {', '.join(KINDS)} 중 하나: {k}")
    if k == "fr5rec":
        from . import fr5rec as M
    elif k == "lerobot":
        from . import lerobot as M
    elif k == "table":
        from . import table as M
    else:
        from . import fr5auto_runs as R
        return R.load(path, name=name, **opt)
    return M.load(path, name=name, weight=weight, **opt)


def load_runs(path, name=None, **opt) -> Runs:
    from . import fr5auto_runs as R
    return R.load(path, name=name, **opt)


def parse_arg(s: str):
    """명령 인자 '이름=경로' 또는 '경로' → (이름 | None, 경로). '=' 앞에 경로 구분자가 있으면 경로로 본다."""
    s = str(s)
    if "=" in s:
        a, b = s.split("=", 1)
        if a and "/" not in a and os.sep not in a and not Path(s).exists():
            return a, b
    return None, s


def make_dataset(name, episodes, weight=1.0, meta=None) -> Dataset:
    """어댑터 공통: 에피소드 id 를 '데이터셋/에피소드' 로 맞추고 Dataset 을 만든다."""
    eps = []
    for e in episodes:
        e = dict(e)
        local = str(e.get("id") or "").split("/")[-1] or f"ep_{len(eps):03d}"
        e["id"] = f"{name}/{local}"
        eps.append(e)
    return Dataset(name, eps, weight=weight, meta=meta)
