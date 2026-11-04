# 명령과 자동화

명령줄 도구 전부와, 폴더를 지켜보다 새 에피소드가 생기면 화면을 다시 만드는 `watch`, 설정 파일 하나로 여러 데이터셋을 돌리는 `pipeline` 을 적는다.
설치하면 `layoutkit` 명령이 생기고, 설치 없이 저장소에서는 `python3 -m layoutkit` 으로 같다.

## 목차

1. [명령 한눈에](#1-명령-한눈에)
2. [DATA 와 공통 옵션](#2-data-와-공통-옵션)
3. [analyze · recommend · compare](#3-analyze--recommend--compare)
4. [watch](#4-watch)
5. [report · init-spec · demo](#5-report--init-spec--demo)
6. [pipeline](#6-pipeline)
7. [파이썬에서](#7-파이썬에서)
8. [출력과 종료 코드](#8-출력과-종료-코드)

## 1. 명령 한눈에

| 명령 | 하는 일 |
|---|---|
| `analyze DATA...` | 분석 → JSON · HTML · PNG |
| `recommend DATA... --spec S` | 분석 + 다음 배치 추천 |
| `compare A B ...` | 분석 + 데이터셋 나란히(둘 이상) |
| `watch DATA... --spec S` | 폴더 감시 → 바뀌면 다시 만들기 |
| `report result.json --out H` | 저장한 결과로 화면만 |
| `init-spec DATA... --out S` | 데이터로 spec 짐작 |
| `demo` | 받침 예제로 화면 만들기 |
| `pipeline config.json` | 설정 파일 하나로 분석·비교·추천·내보내기 |

`layoutkit --version` 은 버전을 찍는다.

## 2. DATA 와 공통 옵션

DATA 는 폴더(fr5rec · LeRobot 자동 판별) · `.csv` · `.tsv` · `.json` · `.jsonl` 이다. `이름=경로` 로 이름을 붙인다(`=` 앞에 경로 구분자가 있거나 그 문자열이 실제 경로면 경로로 본다).
실행 기록(`runs_*.csv` · `runs.jsonl`)을 DATA 에 섞어 주면 실행 기록으로 쓴다. 형식은 [ADAPTERS.md](ADAPTERS.md).

`analyze` · `recommend` · `compare` · `watch` 가 같이 받는 옵션:

| 옵션 | 뜻 |
|---|---|
| `--spec SPEC` | 과제 선언 JSON · YAML(`recommend` · `watch` 는 필수) |
| `--weight NAME=W` | 데이터셋 무게(여러 번) |
| `--runs RUNS` | 수집 실행 기록(여러 번) |
| `--kind KIND` | 형식 고정: `auto`(기본) · `fr5rec` · `lerobot` · `table` · `fr5auto_runs` |
| `--map KEY=COL` | 표 열 대응(여러 번), 예 `start.x=red_x` |
| `--opt KEY=VAL` | 어댑터 옵션(여러 번). 값이 JSON 이면 JSON 으로 읽는다. 예 `grip=6`, `units="m"`, `xyz=[0,1,2]` |
| `--all-outcomes` | 실패·불확실 판도 분석에 넣는다(기본: success · 결과 없음만) |
| `--json JSON` | 결과 JSON 저장 |
| `--lang {ko,en}` | 화면 말 |

`--kind` · `--map` · `--opt` 는 모든 DATA 에 같이 적용된다. 데이터셋마다 다르게 주려면 `pipeline` 설정을 쓴다.

## 3. analyze · recommend · compare

```bash
layoutkit analyze   fr5_v1=v1.json fr5_v2=v2.json --weight fr5_v1=0.5 --spec spec.json --out report.html --json result.json
layoutkit recommend fr5_v1=v1.json fr5_v2=v2.json --weight fr5_v1=0.5 --spec spec.json --n 3 --seed 1 --out report.html
layoutkit compare   v1.json v2.json --spec spec.json --out compare.html
```

| 옵션 | analyze | recommend | compare | 뜻 |
|---|---|---|---|---|
| `--out OUT` | ○ | ○ | ○ | 화면 HTML |
| `--png PNG` | ○ | ○ | ○ | 그림 폴더(matplotlib) |
| `--n N` | | ○ (3) | | 선택지 수 |
| `--seed SEED` | | ○ | | 추천 시드(없으면 spec `recommend.seed`, 그것도 없으면 매번 다름) |

`compare` 는 데이터셋이 둘 이상이어야 하고, 요약 뒤에 비교 지표를 한 줄씩 더 찍는다. 화면은 `analyze` 와 같다(비교 패널은 데이터셋이 둘 이상이면 언제나 나온다).

명령은 끝에 요약을 표준 출력으로 찍는다(진행 글은 표준 오류).

```
layoutkit 0.1.0 · 2026-11-04T16:42:07
  데이터셋 fr5_v1: 100판(쓸 수 있음 100, 씀 100) · 무게 0.5
  데이터셋 fr5_v2: 19판(쓸 수 있음 19, 씀 19) · 무게 1
  [ bad] coupling    0.604 ≤ 0.3    coupling_high
  [ bad] predict     0.908 ≤ 0.65   predict_high
  [ bad] near        0.058 ≥ 0.25   near_low
  [warn] coverage    0.571 ≥ 0.8    coverage_low
  [warn] strata      0.149 ≤ 0.1    strata_skew
  [info] dups        0.008          dups_info
  [info] n_min          18          n_min_info
  쪽 표(기준 x 31.2, 행 출발 ['left', 'right'], 열 목표 ['right', 'left']): [[49, 7], [4, 59]] · 맞힘 0.908
  추천 A: 집기 (250, 604) → 놓기 (185, 567) · empty_start_cell, new_yaw, lowers_coupling, adds_near, balances_strata, far_from_data
  ...
```

## 4. watch

수집하는 동안 데이터 폴더를 지켜보다가 바뀌면 분석(·추천)·화면을 다시 만든다. 브라우저에서 화면을 다시 읽으면 새 판이 반영돼 있다.

```bash
layoutkit watch ~/fr5cap/datasets/fr5_v2 --spec spec.json --out report.html --recommend --every 5
```

| 옵션 | 기본 | 뜻 |
|---|---|---|
| `--out OUT` · `--json JSON` | | 둘 중 하나는 있어야 한다 |
| `--every EVERY` | `5.0` | 확인 주기(s) |
| `--settle SETTLE` | `1` | 바뀐 지문이 다음 확인에서도 이만큼 연속 같아야 다시 만든다(쓰는 중인 파일을 반쯤 읽지 않게) |
| `--recommend` | 끔 | 추천도 같이 |
| `--n N` · `--seed SEED` | `3` · 없음 | 추천 선택지 수·시드 |
| `--once` | | 한 번 만들고 끝 |
| `--max-builds N` | | 이만큼 만들면 끝 |
| `--max-checks N` | | 이만큼 확인하면 끝 |
| `--until-n N` | | 쓴 에피소드가 이만큼이면 끝 |
| `--stop-file F` | | 이 파일이 생기면 끝 |
| `--notify F` | 출력 이름`.watch.json` | 알림 파일 |

공통 옵션(2절)도 받는다.

지문: 형식마다 필요한 파일만 이름 · 크기 · 수정 시각으로 본다(사진 수만 장을 매번 훑지 않게).

| DATA | 보는 파일 |
|---|---|
| fr5rec 폴더 | `ep_*/meta.json`(기록 중 `ep_NNN.part/` 는 뺀다) |
| LeRobot 폴더 | `meta/*.json(l)` · `data/**/*.parquet` |
| 파일 | 그 파일 |
| 그 밖의 폴더 | 2단계 깊이까지의 `.json` · `.jsonl` · `.csv` · `.parquet`(`_discarded*` · `*.part` 폴더, `.tmp` 파일은 뺀다) |

처음 한 번은 바로 만든다. 그 뒤로는 지문이 바뀌고 `settle` 번 연속 같을 때 다시 만든다. 만드는 중 오류(쓰는 중인 파일 등)는 알림 파일 `error` 에 남기고 다음 확인에서 다시 한다(`--once` 면 끝).

알림 파일은 만들 때마다 갱신된다. 수집 프로그램이 읽어 쓸 수 있다. 받침 예제 v1 + v2 를 `--json … --once` 로 돌린 것:

```json
{"t": "2026-11-04T17:01:40", "builds": 1, "checks": 1, "fingerprint": "59cb94ca…", "n_used": 119,
 "cards": [["coupling", "bad", 0.604], ["predict", "bad", 0.908], ["near", "bad", 0.058], ["coverage", "warn", 0.553],
           ["strata", "warn", 0.149], ["dups", "info", 0.008], ["n_min", "info", 21.0]],
 "error": null, "stopped": "once"}
```

`--recommend` 없이 돌린 것이라 칸 채움·n_min 은 놓을 수 있는 칸을 모르는 채(전체 47칸 기준) 센 값이다.

## 5. report · init-spec · demo

```bash
layoutkit report result.json --out report_en.html --lang en
layoutkit init-spec examples/rack_fr5/data/v2_layouts_20261103.json --out spec_guess.json
layoutkit demo --out demo
```

| 명령 | 옵션 | 기본 | 뜻 |
|---|---|---|---|
| `report` | `result`(위치) · `--out`(필수) · `--lang` | spec 의 lang | 저장한 결과로 화면만 |
| `init-spec` | `data`(위치, 여럿) · `--out`(필수) · `--kind` · `--map` · `--opt` | | 데이터로 spec 짐작([SPEC.md 10절](SPEC.md#10-init-spec-짐작)) |
| `demo` | `--out` | `demo` | 출력 폴더 |
| | `--examples` | 저장소의 `examples/` | 예제 폴더 |
| | `--seed` | `1` | 추천 시드 |
| | `--lang` | | 화면 말 |
| | `--no-recommend` | | 추천 없이 |

`demo` 는 `examples/rack_fr5` 의 v1 꼬리표(이름 fr5_v1, 무게 0.5) · v2 배치(fr5_v2) · 실행 기록 · spec 으로 `report.html` · `result.json` · `episodes.csv` 를 만든다. 이 환경에서 약 3 s 걸렸다.
예제 폴더는 패키지 파일 위치 기준(`layoutkit/` 옆 `examples/`)으로 찾는다. 저장소에서 돌리거나 `pip install -e .` 로 설치했으면 그대로 되고, `pip install .` 로 복사 설치했으면 `--examples 저장소/examples` 를 준다.

## 6. pipeline

설정 파일 하나로 여러 데이터셋을 데이터셋마다 다른 옵션으로 읽고, 분석·추천·내보내기를 한 번에 한다. JSON 이고, PyYAML 이 있으면 YAML 도 된다. 상대 경로는 설정 파일이 있는 폴더 기준이다.

```json
{
  "spec": "examples/rack_fr5/spec.json",
  "datasets": [
    {"name": "fr5_v1", "path": "examples/rack_fr5/data/v1_tags.json", "weight": 0.5},
    {"name": "fr5_v2", "path": "examples/rack_fr5/data/v2_layouts_20261103.json", "kind": "table",
     "opt": {"map": {"start": "red_xy", "goal": "ring_xy"}}}
  ],
  "runs": ["examples/rack_fr5/data/runs_20261031_20261104.csv"],
  "recommend": {"n": 3, "seed": 1},
  "outcomes": ["success", null],
  "out": {"dir": "out", "json": "result.json", "html": "report.html", "csv": "episodes.csv",
          "cards_csv": "cards.csv", "png": "fig", "lang": "ko"}
}
```

| 키 | 뜻 |
|---|---|
| `spec` | spec 경로(또는 spec 묶음 그대로) |
| `datasets` | `"이름=경로"` 글이나 `{"name", "path", "weight", "kind", "opt"}` 목록 |
| `runs` | 실행 기록 경로 목록 |
| `recommend` | 없거나 `false` 면 추천 안 함. `true` 또는 `{"n", "seed"}` |
| `outcomes` | 분석에 쓸 결과(기본 `["success", null]`) |
| `out.dir` | 출력 폴더(기본 설정 파일 폴더) |
| `out.json` · `out.html` · `out.png` | 결과 JSON · 화면 · 그림 폴더(`out.dir` 기준) |
| `out.csv` | 에피소드 표 CSV(한 줄 = 에피소드: id, dataset, t, outcome, weight, start_x/y/yaw, goal_x/y/yaw, move_mm, cell_start, cell_goal, flags, `d.<이산 키>`) |
| `out.cards_csv` | 카드 표 CSV(id, status, value, unit, target, code, args) |
| `out.lang` | 화면 말 |

```bash
layoutkit pipeline config.json
```

## 7. 파이썬에서

```python
import layoutkit as lk

v1 = lk.load_dataset("examples/rack_fr5/data/v1_tags.json", name="fr5_v1", weight=0.5)
v2 = lk.load_dataset("examples/rack_fr5/data/v2_layouts_20261103.json", name="fr5_v2")
runs = lk.load_runs("examples/rack_fr5/data/runs_20261031_20261104.csv")

res = lk.analyze([v1, v2], "examples/rack_fr5/spec.json", runs=runs)
lk.recommend([v1, v2], "examples/rack_fr5/spec.json", result=res, n=3, seed=1)   # res["recommend"] 와 reach·카드가 채워진다
lk.render(res, "report.html")
lk.export_png(res, "fig_out")                                                    # matplotlib 이 없으면 []
```

한 번에 돌리는 함수(명령들이 쓰는 것):

```python
from layoutkit.automate import build, watch, run_config, export_episodes_csv, export_cards_csv

res = build(["fr5_v1=v1.json", "fr5_v2=v2.json"], "spec.json", weights={"fr5_v1": 0.5}, recommend=True, n=3, seed=1,
            out_html="report.html", out_json="result.json")
```

`watch(paths, build_fn, every=5.0, settle=1, once=False, max_builds=None, max_checks=None, until_n=None, stop_file=None, notify=None)` 는 `build_fn()` 이 돌려준 결과로 알림 상태를 만든다.

## 8. 출력과 종료 코드

| 종료 코드 | 때 |
|---|---|
| 0 | 끝남 |
| 2 | 다루는 오류(`ImportError` · `ValueError` · `FileNotFoundError` · `RuntimeError` · `KeyError`) — 표준 오류에 `오류: …` 한 줄. `demo` 가 화면 모듈이 없어 HTML 을 못 만든 경우도 2 |
| 1 | `watch` 의 마지막 만들기가 오류로 끝남 |

자주 보는 오류 글:

- `예제 폴더(examples/rack_fr5)를 못 찾았다` — `demo` 에 `--examples` 를 준다.
- `…: 집은 자리·놓은 자리 열을 못 찾았다 — map 으로 알려 준다` — `--map start.x=열 …`.
- `상태 열 … 이 관절각으로 보인다` — LeRobot 에 `--opt eef=열` 또는 `--opt xyz=[…]`.
- `LeRobot parquet 을 읽으려면 pyarrow 가 필요하다` — `pip install pyarrow`.
- `데이터셋 이름이 겹친다` — `이름=경로` 로 나눈다.
