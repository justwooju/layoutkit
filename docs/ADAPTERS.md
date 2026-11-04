# 어댑터 — 데이터 읽기

데이터 형식마다 에피소드(집은 자리 · 놓은 자리 · 이산 값 · 결과)를 꺼내 같은 모양(`layoutkit/data.py`)으로 바꾼다. 분석·추천·화면은 이 모양만 읽는다.
궤적만 있는 형식(LeRobot, 꼬리표 없는 fr5rec)은 그리퍼 닫힘·열림 사건으로 자리를 찾는다(7절).

## 목차

1. [형식 자동 판별](#1-형식-자동-판별)
2. [공통](#2-공통)
3. [fr5rec](#3-fr5rec)
4. [LeRobot v2.x](#4-lerobot-v2x)
5. [CSV · JSON 표](#5-csv--json-표)
6. [fr5auto 실행 기록](#6-fr5auto-실행-기록)
7. [궤적 → 사건](#7-궤적--사건)
8. [한계](#8-한계)

## 1. 형식 자동 판별

`load_dataset(path, kind="auto")` 가 경로를 보고 정한다(`adapters.detect_kind`).

| 경로 | 판별 | kind |
|---|---|---|
| 폴더에 `meta/info.json` | LeRobot | `lerobot` |
| 폴더에 `ep_*/meta.json` | fr5rec 데이터셋 | `fr5rec` |
| 폴더에 `runs.jsonl` · `work/runs.jsonl` · `runs_*.csv` | 실행 기록 | `fr5auto_runs` |
| `.json` 이고 `{"episodes": [{"ep", "meta": {...}}]}` | 받침 꼬리표 묶음 | `fr5rec` |
| `.json` 이고 `R`·`S` 키 | 특징 묶음(feat.json) | `fr5rec` |
| `.json` 이고 `frames` 목록 | fr5rec meta.json 하나 | `fr5rec` |
| 그 밖의 `.json` | 표 | `table` |
| `.jsonl` 첫 줄 `kind` 가 run · plan · reset | 실행 기록 | `fr5auto_runs` |
| 그 밖의 `.jsonl` | 표 | `table` |
| `.csv` · `.tsv` 머리에 `time`·`verdict` 와 `exec_s` 또는 `decided_by` | 실행 기록 | `fr5auto_runs` |
| 그 밖의 `.csv` · `.tsv` | 표 | `table` |
| `.parquet` 하나 | 오류 — LeRobot 폴더를 준다 | |

명령에서는 `--kind` 로 정할 수 있다(모든 DATA 에 같이 적용된다).

## 2. 공통

```python
import layoutkit as lk
ds = lk.load_dataset("examples/rack_fr5/data/v1_tags.json", name="fr5_v1", weight=0.5)
ds.summary()        # {"name", "n", "n_usable", "n_success", "weight", "meta"}
ds.meta["how"]      # 자리 출처별 판 수(fr5rec): {"tag": 100}
```

- 명령의 DATA 는 `이름=경로` 로 이름을 붙인다. 이름이 없으면 폴더·파일 이름(또는 파일 안 `dataset` 값)이다. 데이터셋 이름이 겹치면 오류다.
- 에피소드 id 는 `데이터셋/에피소드` 로 맞춘다.
- 무게: `--weight 이름=W` 또는 `weight=`. 판 무게 = 데이터셋 무게 × 에피소드 무게.
- 어댑터 옵션: 명령 `--opt 키=값`(값이 JSON 이면 JSON 으로 읽는다. 예 `--opt xyz=[0,1,2]`, `--opt events={"which":"first"}`), 파이썬은 `load_dataset(..., 키=값)`. 모르는 옵션은 무시한다.
- 표 열 대응: 명령 `--map start.x=red_x`(여러 번), 파이썬 `map={...}`.
- 경로는 결과에 상대 경로나 `~/…` 로 남는다(집 폴더 계정 이름을 가린다).

에피소드 모양:

```json
{"id": "fr5_v1/ep_007", "dataset": "fr5_v1", "t": "2026-11-01T18:29:08", "outcome": "success", "weight": 0.5, "source": "fr5rec",
 "start": {"x": 240.3, "y": 579.8, "yaw": 77.2, "z": 131.4},
 "goal": {"x": -29.3, "y": 573.7, "yaw": 77.2},
 "discrete": {"start_slot": 3, "goal_slot": 0, "arrangement": "Y○○R", "same_fixture": false},
 "fixtures": [{"name": "rack0", "x": 120.0, "y": 560.0, "yaw": 47.0}],
 "extra": {"duration_s": 23.1, "path_mm": 812.0, "n_frames": 231},
 "thumbs": {"third": "상대 경로 또는 data URI"},
 "flags": []}
```

`start`·`goal` 의 x·y 는 mm 이고 둘 다 있어야 분석에 쓴다. `yaw`(°)·`z` 는 없어도 된다. `extra` 에는 숫자만 남는다.

## 3. fr5rec

FAIRINO FR5 기록 서버 `fr5rec` 의 데이터셋 폴더와, 그 꼬리표를 모은 JSON 을 읽는다(`adapters/fr5rec.py`). 폴더 구조와 꼬리표 키는 FR5-AutoCollect `docs/DATA.md` 와 같다.

```
~/fr5cap/datasets/<데이터셋>/
  ep_000/meta.json      ← 읽는다
  ep_000/rgb/00000.png  ← 썸네일(첫 3인칭 사진)
  ep_005.part/          ← 기록 중 — 읽지 않는다
  _discarded/...        ← 버린 판 — 읽지 않는다
```

읽는 형태:

| 형태 | 모양 |
|---|---|
| 폴더 | `ep_<숫자>/meta.json` 마다 한 판 |
| 꼬리표 묶음 JSON | `{"dataset": 경로, "note": 글, "episodes": [{"ep": "ep_000", "meta": {...}}]}` (받침 v1 예제) |
| 특징 묶음 JSON | `{"R": [[x, y]...], "S": [[x, y]...], "Y": [...], "src": [[받침, 칸]...], "dst": [...], "t0": [...]}` (fr5lens·rackrec 내보내기) |
| meta.json 하나 | `frames` 가 있는 meta |

판마다 자리를 찾는 순서:

1. 꼬리표 `fr5rec.tag` 에 `red_xy`·`slot_xy` 가 있으면 그것이 start · goal 이다(fr5auto `rackrec.ep_record` 와 같다).
   - `src`·`dst` = [받침, 칸] → `discrete` 의 `start_fixture`·`start_slot`·`goal_fixture`·`goal_slot`·`same_fixture`.
   - `yellow_at` 이 빨강과 같은 받침이면 `obstacle_slot` 과 `arrangement`(예 `Y○○R`, 칸 0 부터). 없으면 `tag.scene` 문자열(`받침1[Y○○R]`)에서 그 받침 기호.
   - `racks` → `fixtures`(rack0, rack1, …).
   - yaw: `params.yaw_g`·`yaw_i`(계획한 잡기·꽂기 손목 각), 없으면 meta `task_yaw_deg`. z: `params.zg`·`zi`.
2. 꼬리표에 추천 배치 `rec_theta` 만 있고 옵션 `pitch_mm` 을 주면 칸 자리를 계산한다(h = p + (k − (n−1)/2)·간격·(cos ψ, sin ψ)). 실제 놓인 자리가 아니라 목표 자리다.
3. 아니면 `frames[]` 궤적(`t`, `tcp_base_mm_deg` = [x, y, z (mm), rx, ry, rz (°)], `grip_width` (m, 0.04 = 다 엶))에서 사건을 찾는다(7절, 닫힘 = 폭이 작은 쪽).

그 밖에 읽는 것: `outcome`, `duration_s`(없으면 프레임 시각 차), meta `scene` 묶음(세션 조건 값 → `discrete`), 시각(`fr5rec.started_at`, 없으면 첫 프레임 시각), 첫 3인칭 사진(`<카메라 dir | rgb | third>/00000.png|jpg` 또는 `third_00000.png`).
꼬리표에 `dry: true`(드라이런)인 판은 뺀다. 데이터셋 `meta.how` 에 자리 출처별 판 수(`tag` · `rec_theta` · `events` · `none`)가 남는다.

| 옵션 | 기본 | 뜻 |
|---|---|---|
| `use_tags` | `true` | 거짓이면 꼬리표를 무시하고 궤적 사건만 |
| `pitch_mm` | `null` | `rec_theta` 를 칸 자리로 바꿀 때 칸 간격 |
| `n_slots` | `4` | 받침 칸 수(배치 글자·칸 자리) |
| `thumbs` | `true` | 첫 사진 경로를 썸네일로 |
| `events` | `null` | 사건 찾기 옵션 묶음(7절), 예 `{"which": "first"}` |

## 4. LeRobot v2.x

`meta/info.json` · `meta/episodes.jsonl` · `data/chunk-*/episode_*.parquet` 폴더를 읽는다(`adapters/lerobot.py`). parquet 을 읽으려면 pyarrow 가 필요하다(`pip install pyarrow` 또는 `pip install ".[parquet]"`).

- 에피소드 목록은 `meta/episodes.jsonl`, 없으면 `info.total_episodes`. `tasks` 첫 값은 `discrete.task` 로 남는다.
- 파일 자리는 `info.data_path` 틀(`chunks_size` 로 묶음 번호)로 찾고, 없으면 `data/**/episode_<번호>.parquet` 를 찾는다. 에피소드 파일이 없으면(한 파일에 여러 에피소드) `data/` 아래 parquet 을 다 읽어 `episode_index` 로 나눈다.
- 시각: `timestamp` 열, 없으면 `frame_index / fps`, 없으면 순서 / fps(`info.fps`, 없으면 10).
- 결과(`outcome`)는 없다(분석에서 '결과 없음'으로 쓴다).

열 고르기(옵션이 없으면 짐작한다):

| 옵션 | 짐작 | 뜻 |
|---|---|---|
| `state` | `observation.state`, 없으면 이름에 state 가 든 첫 1차원 열(길이 ≥ 3) | 상태 벡터 열 |
| `eef` | 열 이름이 `eef_pos` · `ee.position` · `tcp_xyz` · `end_effector_pos` 꼴 | EEF 위치가 따로 든 열 — 주면 xyz 를 이 열에서 |
| `xyz` | `features[state].names` 에서 `x`·`y`·`z`(또는 `ee_x`·`tcp.x` 꼴, rot·quat·vel·action·force·torque 는 피함), 못 찾으면 `[0, 1, 2]` | 위치 칸 번호 3개 |
| `grip` | names 에 grip · finger · claw · jaw 가 든 칸 → 따로 된 gripper 열 → 상태 마지막 칸 | 그리퍼 칸 번호 또는 열 이름 |
| `yaw` | names 에 yaw 또는 `rz` | yaw 칸 번호(없으면 안 씀) |
| `episodes` | 전부 | 읽을 에피소드 번호 목록 |
| `units` · `yaw_units` | `auto` · `auto` | 7절 |
| `closed_is` · `threshold` · `grip_range` · `min_closed_s` · `min_open_s` · `min_frames` · `hyst` · `sep_ratio` · `settle_s` · `still_mm_s` · `which` | 7절 기본 | 사건 찾기 옵션 |

상태가 관절각뿐이고(names 에 joint · shoulder · elbow · wrist_flex/roll/pitch · pan · lift · q<숫자> 가 둘 이상) 위치 칸을 못 찾으면 짐작하지 않고 오류로 알린다. 이때는 `eef` 나 `xyz` 를 준다. layoutkit 은 순기구학을 하지 않는다.
짐작한 것은 데이터셋 `meta.guessed`(예 `xyz=[0,1,2]`, `grip=last`), 쓴 열은 `meta.columns`, 사건 깃발 수는 `meta.event_flags` 에 남는다.

```bash
layoutkit analyze ~/lerobot/my_task --opt eef=observation.eef_pos --opt grip=6 --opt units=m
```

예제 [examples/lerobot_demo/make_lerobot.py](../examples/lerobot_demo/make_lerobot.py) 는 알고 있는 집는·놓는 자리로 작은 LeRobot v2.1 폴더(상태 = x, y, z [m], roll, pitch, yaw [rad], gripper [폭 m], 30 fps)와 참값 `truth.json` 을 만든다(pyarrow 필요).

## 5. CSV · JSON 표

한 줄 = 에피소드 하나인 표를 읽는다(`adapters/table.py`). CSV · TSV · JSONL · JSON(`[행, ...]` 또는 `{"episodes" | "rows" | "data": [행, ...], "dataset": 이름, "note": 글}`).

layoutkit 에피소드 모양 그대로(`start`·`goal` 이 `{"x", "y", ...}` 묶음)인 JSON 은 열 대응 없이 받는다. 캡스톤 예제의 `make_synth.py` 출력이 이 모양이다.

열 대응 `map` 키(값 = 열 이름):

| 키 | 뜻 |
|---|---|
| `id` · `t` · `outcome` · `weight` | |
| `start.x` · `start.y` · `start.yaw` · `start.z` | 집은 자리 |
| `goal.x` · `goal.y` · `goal.yaw` · `goal.z` | 놓은 자리 |
| `start` · `goal` | `[x, y(, yaw)]` 목록 또는 `{"x", "y"}` 가 든 한 열(예 `red_xy`) |
| `discrete.<이름>` · `extra.<이름>` · `thumbs.<이름>` | |

`map` 에 없는 것은 흔한 이름으로 짐작한다(대소문자 무시, 표의 첫 맞는 열).

| 키 | 짐작하는 열 이름 |
|---|---|
| id | id · ep · episode · episode_id · episode_index · name |
| t | t · time · timestamp · started_at · datetime · date |
| outcome | outcome · result · verdict · success |
| start (목록 열) | start_xy · pick_xy · start · pick · src_xy · from_xy · red_xy · object_xy |
| goal (목록 열) | goal_xy · place_xy · goal · place · dst_xy · to_xy · target_xy · ring_xy · slot_xy |
| start.x / start.y | start_x · pick_x · src_x · from_x · x0 · red_x · object_x (y 도 같은 꼴) |
| goal.x / goal.y | goal_x · place_x · dst_x · to_x · x1 · target_x · ring_x · slot_x (y 도 같은 꼴) |
| start.yaw · goal.yaw | start_yaw · pick_yaw · yaw0 / goal_yaw · place_yaw · yaw1 |

- 대응 안 된 열: 글자·참거짓은 값 종류가 12개 이하일 때 `discrete`(넘으면 버린다), 정수는 값 종류 12개 이하면 `discrete` 아니면 `extra`, 실수는 `extra`.
- `outcome` 값: true · 1 · ok · pass · yes · success → success, false · 0 · no · fail · failure → fail, unsure · unknown · ? → unsure.
- `red_xy`·`ring_xy` 열이 함께 있고 `map` 을 안 주면 fr5auto `rack cover` 내보내기(`v2_layouts_*.json`)로 보고 정해진 대응을 쓴다(`red_slot` → start_slot, `ring_slot` → goal_slot, `same_rack` → same_fixture, `arrangement`).
- 집은·놓은 자리 열을 못 찾으면 열 목록과 함께 "map 으로 알려 준다" 오류를 낸다.

| 옵션 | 기본 | 뜻 |
|---|---|---|
| `map` | `null` | 열 대응 |
| `scale` | `1.0` | 좌표(x, y, z)에 곱할 값. m 표면 1000 |
| `sep` | `,`(`.tsv` 는 탭) | CSV 구분자 |

```bash
layoutkit analyze runs.csv --map start.x=obj_x --map start.y=obj_y --map goal.x=bin_x --map goal.y=bin_y --opt scale=1000
```

## 6. fr5auto 실행 기록

수집기 fr5auto 의 실행 기록을 읽어 `Runs`(실행 한 번 = 한 줄)를 만든다(`adapters/fr5auto_runs.py`). 데이터셋이 아니라 `analyze(..., runs=)` 에 들어간다. 명령에서는 `--runs` 로 주거나 DATA 에 섞어 주면 실행 기록으로 쓴다.

| 파일 | 읽는 것 |
|---|---|
| `runs.jsonl` | `kind == "run"` 줄만(plan · reset 은 녹화가 아니다). `t`, `verdict`, `kept`, `decided_by`, `record`, `T`(실행 시간), `verdict_why`(목록) 또는 `why`, `hover`·`evidence.hover`(`off_mm`, `shift`, `too_big`), `servo`(`n_meas`, `n_fix`, `n_clamp`, `shift_mm`, `phi_deg`), `episode` |
| `runs_*.csv` | 열 time, verdict, kept, decided_by, record, exec_s, hover_off_mm, hover_shifted, hover_too_big, servo_meas, servo_fixes, servo_hit_limit, servo_shift_mm, servo_wrist_deg, reason |
| 폴더 | 그 안의 `runs.jsonl` · `work/runs.jsonl` · `runs_*.csv` · `data/real/runs_*.csv` 전부 |

시각이 유닉스 초면 로컬 시각 ISO 로 바꾼다. 이유 글은 ` | ` 로 나눠 `reasons` 에 둔다. 줄은 시각 순으로 정렬한다. 요약은 [ANALYSIS.md 9절](ANALYSIS.md#9-실행-기록).

## 7. 궤적 → 사건

`layoutkit.events.detect(t, xyz, grip, yaw=None, **opt)` 가 궤적 하나에서 집은 자리 · 놓은 자리를 찾는다. 그리퍼가 닫힌 구간의 시작 = 집음, 다시 열린 순간 = 놓음이다.

1. 위치 단위: `units` 가 `auto` 면 절댓값 최대가 5 아래일 때 m 로 보고 mm 로 바꾼다. yaw 는 `yaw_units` 가 `auto` 면 절댓값 최대가 π(+0.05) 이하일 때 rad 로 본다.
2. 문턱: `threshold` → `grip_range` 가운데 → 자동(그리퍼 값을 1차원 2-평균으로 두 무리로 나눈 두 가운데의 중간). 두 무리 사이가 무리 안 표준편차의 `sep_ratio` 배보다 작으면 그리퍼가 안 움직였다고 본다(`no_grip`).
3. 닫힘 방향: `closed_is` 가 `low`(폭: 작을수록 닫힘) · `high`(닫힘 명령: 클수록 닫힘) · `auto`(에피소드 첫 10 % 는 열려 있다고 보고 그 반대).
4. 잡음: 문턱 둘레 히스테리시스(두 무리 사이 × `hyst`). 그다음 `min_closed_s` 또는 `min_frames` 보다 짧은 닫힘은 지우고, 닫힘 사이의 짧은 열림(`min_open_s`)은 메운다(처음·끝의 열림은 메우지 않는다).
5. 구간 고르기: 닫힌 구간이 여럿이면(다시 잡기) `which` 로 고른다. `longest`(기본, 가장 긴 구간 = 옮긴 구간) · `first` · `last` · `span`(첫 구간의 집음 + 마지막 구간의 놓음).
6. 자리: 집은 자리 = 닫힌 첫 프레임 앞 `settle_s`/2 ~ 뒤 `settle_s` 창에서 팔이 거의 멈춘(xy 속력 ≤ `still_mm_s`) 프레임들의 EEF 중앙값. 놓은 자리 = 열린 첫 프레임 앞 `settle_s` ~ 뒤 `settle_s`/2 창에서 같은 방식. 멈춘 프레임이 없으면 창에서 가장 느린 프레임. yaw 는 원형 중앙값.

| 옵션 | 기본 | |
|---|---|---|
| `threshold` | `null` | 그리퍼 문턱(값 단위) |
| `grip_range` | `null` | `(lo, hi)` 값 범위를 알면 |
| `closed_is` | `"auto"` | `low` · `high` · `auto` (fr5rec 은 `low`) |
| `units` | `"auto"` | `mm` · `m` · `auto` |
| `yaw_units` | `"deg"` | `deg` · `rad` · `auto` (LeRobot 은 `auto`) |
| `hz` | `null` | 시각이 없을 때 프레임 주기(없으면 10) |
| `min_closed_s` · `min_open_s` | `0.3` · `0.3` | 깜빡임 길이 |
| `min_frames` | `2` | 이보다 짧은 구간은 깜빡임 |
| `hyst` | `0.1` | 히스테리시스 반폭 비율 |
| `sep_ratio` | `5.0` | '안 움직임' 판정 |
| `settle_s` | `0.6` | 자리를 재는 창 길이 |
| `still_mm_s` | `15.0` | 멈춤 속력 |
| `which` | `"longest"` | 구간 고르기 |

깃발(`flags`): `no_grip`(그리퍼가 안 움직임 — 자리 없음) · `held_at_start`(처음부터 닫힘) · `no_release`(끝까지 안 열림 — 마지막 프레임을 놓은 때로) · `regrasp`(닫힌 구간 여럿) · `too_short`.
돌려주는 값에는 `t_pick`·`t_place`·`segments`·쓴 문턱·방향·단위·`duration_s`·`path_mm` 도 있다. 어댑터는 이 중 시간·경로 길이·잡은 횟수를 `extra` 에 남긴다.

시험: 가짜 LeRobot 궤적(30 fps, 위치 잡음 0.3 mm, 그리퍼 잡음 0.5 mm, 한 프레임 튐)에서 자리 오차 최대 0.18 mm, 가짜 fr5rec 궤적(10 Hz)에서 0.29 mm, '닫힘 명령'(0~1, 클수록 닫힘) 값과 두 프레임 튐에서도 방향을 스스로 짐작했다([TESTING.md](TESTING.md#3-시험-파일)).

## 8. 한계

- 에피소드 하나에서 집기 · 놓기를 한 번만 찾는다. 여러 물체를 차례로 옮기는 긴 에피소드는 `which` 로 고른 한 구간만 남는다. 나눠서 넣어야 한다.
- 자리는 그리퍼를 닫고 열 때의 EEF 위치다. 물체 자리가 아니라 손 자리이고, 놓을 때 물체를 떨어뜨리면 놓은 자리가 실제 물체 자리와 다르다.
- 이 개발 환경에는 pyarrow 가 없어 LeRobot parquet 파일을 실제로 읽는 경로는 시험하지 못했다. 같은 열을 메모리에서 넘기는 시험(`episode_from_columns`)과 가짜 데이터로만 확인했다. 한 파일에 여러 에피소드가 든 꼴(v3 모양)도 시험하지 않았다.
- LeRobot 상태가 관절각뿐이면 읽지 못한다(순기구학 없음).
- 위치 단위 자동 짐작은 작업 공간이 5 m 를 넘지 않는다고 본다. mm 기록인데 값이 모두 5 아래면 m 로 잘못 본다. 그때는 `units` 를 준다.
- fr5rec 꼬리표의 `rec_theta` 로 계산한 자리는 추천 목표 자리다(실제 놓인 자리가 아니다).
