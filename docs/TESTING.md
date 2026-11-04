# 시험

시험 파일과 돌리는 법, 각 시험이 다시 확인하는 숫자를 적는다. 로봇·카메라 없이 돈다. 시험 프레임워크는 쓰지 않는다 — 파일 안의 `test_*` 함수를 차례로 부르고 `ok <이름>` 을 찍는다.

## 목차

1. [돌리는 법](#1-돌리는-법)
2. [시험 파일 한눈에](#2-시험-파일-한눈에)
3. [시험 파일](#3-시험-파일)
4. [선택 의존과 건너뛰기](#4-선택-의존과-건너뛰기)
5. [시험용 결과(fixture)](#5-시험용-결과fixture)

## 1. 돌리는 법

저장소 맨 위에서 파일 하나씩 실행한다. 시험은 임시 폴더에 쓰고 지운다(`test_report.py` 만 `fig/` 에 그림을 쓴다 — 아래).

```bash
python3 tests/test_rack_numbers.py     # 받침 예제 숫자
python3 tests/test_adapters.py         # 어댑터 · 사건 찾기
python3 tests/test_recommend.py        # 배치 추천
python3 tests/test_cli.py              # 명령 흐름
python3 tests/test_report.py           # 화면(Playwright 필요)
```

`test_recommend.py` 는 끝에 `n/6 통과` 를 찍고 실패가 있으면 종료 코드 1 이다. 나머지는 첫 실패에서 예외로 멈춘다.

## 2. 시험 파일 한눈에

시간은 2026-11-04 이 개발 환경(Python 3.13, numpy 2.5)에서 잰 값이다.

| 파일 | 함수 | 시간 | 필요한 것 | 내용 |
|---|---|---|---|---|
| `test_rack_numbers.py` | 3 | 약 3 s | numpy | 받침 v1 · v2 숫자, 합친 분석, 실행 기록 |
| `test_adapters.py` | 7 | 1 s 안 | numpy (pyarrow · FR5-AutoCollect 있으면 더) | LeRobot 열 · 사건 찾기 · fr5rec 폴더 · 표 · 실행 기록 |
| `test_recommend.py` | 6 | 약 5 s | numpy (FR5-AutoCollect 있으면 더) | 카메라 투영 · 통과 121 · 가짜 세계 · 시험 배치 · 큐 · 결과 채우기 |
| `test_cli.py` | 3 | 약 3 s | numpy | analyze 결과 키 · init-spec · watch --once · pipeline |
| `test_report.py` | 5 | 약 18 s | Playwright + Chromium (matplotlib 있으면 더) | HTML 을 열어 JS 오류 · 외부 요청 · 요소 수 · 상호작용 |

## 3. 시험 파일

### test_rack_numbers.py

`examples/rack_fr5/data/` 의 실물 데이터로 FR5-AutoCollect `rackrec`(같은 판의 `test_v1_numbers`, `docs/RECOMMENDER.md` 1절)과 같은 숫자가 나오는지 본다.

| 함수 | 확인하는 값 |
|---|---|
| `test_v1_numbers` | 꼬리표 JSON 과 특징 묶음(feat.json) 둘 다: 쪽 표 기준선 64.9 · [[44, 0], [4, 52]] · 맞힘 0.96, ρ(x) −0.81 · ρ(y) −0.43, 옮긴 거리 118 · 380 · 중앙 232 · 가까이 0, 자리 32 · 43 · 99, 집는 칸 31/16/8/45 · 놓는 칸 25/22/25/28, 칸 47 · 채움 20 · 27, 공식 칸 41 · 방향 칸 3 · 이론 123 · 무작위 663, 범위 x −111~240 · −146~260, 같은 받침 0, 채움 거리 61 · 56 mm(껍질 0.0593 m²), 배치 Y○○R 45 · R○○Y 31 · ○R○Y 16 · Y○R○ 8, 카드 coupling · near · predict 나쁨 |
| `test_v2_numbers` | ρ(x) −0.03, 가까이 0.21(4판), 자리 19 · 19 · 19, 같은 받침 8, 쪽 표 기준선 30.1 · [[4, 5], [3, 7]], 방향 칸 0(내보내기에 yaw 없음) |
| `test_combined_and_runs` | v1(무게 0.5) + v2 비교 지표가 혼자 분석한 값과 같다(ρ −0.807 · −0.034, 쪽 맞힘 0.96, 가까이 0.211, 같은 받침 8), 데이터셋 색이 Okabe–Ito 순서, 실행 기록 200회 · 성공 148 · 남김 149 · 첫 이유 fixture_moved |

### test_adapters.py

| 함수 | 확인하는 것 |
|---|---|
| `test_lerobot_columns` | `make_lerobot.py` 궤적 8판(m · rad · 그리퍼 폭, 30 fps, 잡음, 한 프레임 튐)을 열 그대로 넘겨 사건으로 찾은 자리 오차 ≤ 2 mm(이 환경 0.18 mm). 열 짐작 xyz [0, 1, 2] · grip 6 · yaw 5 |
| `test_events_inverted_noisy` | 그리퍼 값이 '닫힘 명령'(0~1, 클수록 닫힘)에 잡음·두 프레임 튐이 있어도 방향 `high` 를 짐작하고 자리 ≤ 2 mm. 그리퍼가 안 움직이면 `no_grip` |
| `test_lerobot_parquet` | pyarrow 가 있으면 parquet 폴더를 써서 `load_dataset` 자동 판별 왕복 ≤ 2 mm. 없으면 건너뛴다 |
| `test_fr5rec_events_and_tags` | 가짜 fr5rec 폴더: 꼬리표 없는 4판은 궤적 사건(≤ 2 mm, 이 환경 0.29 mm), 꼬리표 판은 꼬리표 자리·칸·배치 글자·고정물, `_discarded/` · `ep_NNN.part/` 는 안 읽음 |
| `test_fr5rec_make_human` | 환경 변수 `FR5AUTO_DIR` 가 있으면 FR5-AutoCollect `tests/make_human.py`(사람 시연 흉내, 3 Hz) 데이터에서 집은 자리 ≤ 2 mm · yaw 1° 안 · 썸네일. 없으면 건너뛴다 |
| `test_table_adapter` | CSV 열 대응(map) · 결과 글 바꾸기 · 남은 열의 discrete/extra, JSONL 이름 짐작, v2 내보내기 전용 대응, 흔한 이름 짐작, 맞는 열이 없을 때 오류 글 |
| `test_runs_adapter` | 예제 CSV 200회 판별·읽기, `runs.jsonl` 은 `kind: run` 줄만, 이유 code |

### test_recommend.py

| 함수 | 확인하는 것 |
|---|---|
| `test_camera_matches_fr5auto` | 실물 3인칭 보정에서 fr5auto `camera.project_world` 기준 점 6개와 투영 차이 < 0.01 px(`dist_flip` 참 · 거짓). FR5-AutoCollect 가 있으면 무작위 500점도 |
| `test_rack_reach_121` | 받침 spec 후보 16384개(시드 20261102) 중 통과 121, 놓을 수 있는 (자리, 방향) 칸 60 · 41. FR5-AutoCollect 가 있으면 `rackrec.sample` 과 후보 좌표·줄 방향이 같고 통과 집합이 같다 |
| `test_fake_world_fills_faster` | 가짜 세계(받침 둘, 손목 창, reach · gap 검사)에서 사람이 추천 자리에 ±10 mm · ±5° 로 놓는다고 치고 40판: 추천이 무작위보다 칸을 많이 채우고, 채운 칸이 집는·놓는 쪽 모두 판 수의 0.75 배 이상(이 환경 추천 39 · 40, 무작위 30 · 33) |
| `test_avoids_holdout` | 시험 배치 6개(T01~T06)가 큐에 한 번 정해지고, 선택지가 모두 시험 배치에서 0.5 h 밖 |
| `test_queue_deleted_returns` | 저장 → 판 지움 → 같은 목표가 다음 추천의 A(`retry_deleted`, 새 계산은 A2) → 다시 모으면 끝. `rec_id` 없이 놓인 자리로 목표 맞추기 |
| `test_fills_result` | `result` 를 주면 `result["recommend"]`, `coverage.*.reach`(자리 칸 길이), `reach_start`, `n_min` 이 채워진다 |

FR5-AutoCollect 비교는 환경 변수 `FR5AUTO_DIR`, 없으면 이 저장소 옆 폴더 `../FR5-AutoCollect` 를 찾는다. 이 환경에서는 옆 폴더가 있어 비교까지 통과했다.

### test_cli.py

`python -m layoutkit` 을 하위 프로세스로 돌린다.

| 함수 | 확인하는 것 |
|---|---|
| `test_analyze_json_keys` | `analyze --json` 결과에 ARCHITECTURE 3절 키가 다 있다, 데이터셋 순서·무게, 칸 47, 상태 값, 결과 파일에 `/home/` 이 없다 |
| `test_init_spec_and_watch_once` | `init-spec` 이 영역·strata 를 짐작하고, 그 spec 으로 `watch --once` 가 한 번 만들고 알림 파일(`builds` 1 · `stopped` once · `n_used` 19)을 쓴다 |
| `test_pipeline_config` | 설정 파일로 result.json · episodes.csv(119줄) · cards.csv |

### test_report.py

`tests/fixtures/result_rack.json`(5절)과 실제 분석 결과로 HTML 을 만들고 Playwright(Chromium)로 연다.

| 함수 | 확인하는 것 |
|---|---|
| `test_dashboard_ko_en` | ko · en 모두 JS 오류 0 · 외부 요청 0 · 카드 5 · 칸 지도 2 · 산점 2 · 쪽 표 3 · 추천 3 · 표 줄 수 = 에피소드 수 · 가로 넘침 없음. ko 에서 데이터셋 끄기(표·지도) · 줄 누르기(선택 표시) · 점 말풍선 · 거르기 · 점만 보기 |
| `test_no_recommend_narrow` | 추천 없음 → 안내 글, 390 px 폭에서 가로 넘침 없음 |
| `test_big_file_size` | 에피소드 3000개 결과의 HTML 이 4 MB 아래, JS 오류 0 |
| `test_real_analyze` | 받침 예제 실제 analyze + recommend 결과로 오류 없이 서고, 이유 코드마다 사전 글이 있다 |
| `test_export_png` | matplotlib 이 있으면 PNG 6장(map · cells · shortcut · transfer · strata · runs) |

`test_dashboard_ko_en` 은 전체 페이지를 `fig/dashboard_ko.png` · `fig/dashboard_en.png` 에 덮어쓴다(폭 1280, deviceScaleFactor 1). 그림을 바꾸고 싶지 않으면 저장소 복사본에서 돌린다.

## 4. 선택 의존과 건너뛰기

| 없을 때 | 결과 |
|---|---|
| pyarrow | `test_lerobot_parquet` 건너뜀(열 시험으로 대신). 이 환경에는 없어 parquet 파일 읽기는 시험하지 못했다 |
| FR5-AutoCollect(`FR5AUTO_DIR` 또는 옆 폴더) | fr5auto 와의 무작위 점·후보·통과 집합 비교, `make_human` 시험 건너뜀. 적어 둔 기준 값 비교와 통과 수 121 은 그대로 확인한다 |
| matplotlib | `test_export_png` 건너뜀 |
| Playwright · Chromium | `test_report.py` 가 돌지 않는다(건너뛰지 않고 오류) |

## 5. 시험용 결과(fixture)

`tests/fixtures/result_rack.json` 은 화면 개발·시험용 결과다. `tests/fixtures/make_fixture.py` 가 받침 예제(v1 꼬리표 100판 + v2 19판 + 실행 기록)에서 표준 라이브러리만으로 만든다. v1 숫자(쪽 표 44/44 · 52/56, ρ −0.81, 자리 32/43/99, 칸 20/27)는 맞춰 넣지만, 추천·놓을 수 있는 칸 같은 값은 그럴듯하게 만든 것이라 실제 `analyze`·`recommend` 결과와 다르다.

```bash
python3 tests/fixtures/make_fixture.py     # → tests/fixtures/result_rack.json (없으면 test_report.py 가 먼저 만든다)
```
