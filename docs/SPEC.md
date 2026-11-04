# spec — 과제 선언

분석 눈금·목표 영역·이산 칸·지름길 짝·문턱과, 추천이 고르는 배치 모양·검사·카메라를 파일 하나(JSON 또는 YAML)에 적는다.
분석만 할 때는 spec 이 없어도 된다(데이터 범위로 영역을 짐작한다). 추천은 배치 모양·검사를 spec 에서 읽으므로 `recommend` 명령은 `--spec` 이 필수다.

## 목차

1. [읽기와 기본값](#1-읽기와-기본값)
2. [분석 키](#2-분석-키)
3. [추천 공통 키](#3-추천-공통-키)
4. [layout — 추천이 고르는 배치](#4-layout--추천이-고르는-배치)
5. [constraints — 놓을 수 있는 배치 검사](#5-constraints--놓을-수-있는-배치-검사)
6. [cameras](#6-cameras)
7. [예: 받침 과제](#7-예-받침-과제)
8. [예: 캡스톤 색 분류](#8-예-캡스톤-색-분류)
9. [예: points 최소](#9-예-points-최소)
10. [init-spec 짐작](#10-init-spec-짐작)

## 1. 읽기와 기본값

`layoutkit.spec.load(path_or_dict)` 가 읽는다. 사용자가 준 값을 `spec.DEFAULTS` 위에 덮는다. 묶음(dict)은 안쪽 키만 덮고, 목록은 통째로 바꾼다.
확장자가 `.yaml`·`.yml` 이면 PyYAML 로 읽는다(없으면 오류로 알린다). 읽은 파일 경로는 `_source` 에 남는다(훅 모듈을 spec 옆 폴더에서 찾을 때 쓴다).

가장 작은 spec 은 영역 하나다.

```json
{"task": "pick_place", "area": {"x": [-200, 270], "y": [450, 650]}}
```

읽을 때 `spec.check()` 가 모양을 본다. 틀리면 `ValueError` 로 무엇이 틀렸는지 알린다.

| 검사 | 조건 |
|---|---|
| area | `x`·`y` 가 `[작은 값, 큰 값]` |
| scales.h_xy_mm | 0 보다 크다 |
| strata | 항목마다 `name`·`values` 가 있다. `shares` 를 주면 `values` 와 길이가 같고 합이 1 |
| pairs | 항목마다 `[출발 특징, 목표 특징]` 두 개 |
| lang | `ko` 또는 `en` |

좌표는 mm 다. 같은 데이터셋 안에서 같은 기준(보통 로봇 베이스)이어야 한다. 화면에서 어느 쪽이 왼쪽인지는 `frame` 에 적는다.

## 2. 분석 키

| 키 | 기본 | 뜻 |
|---|---|---|
| `task` | `"pick_place"` | 과제 이름. `title` 이 없으면 화면 제목 |
| `title` | `null` | 화면 제목 |
| `units` | `"mm"` | 기록용. 지금 코드는 이 값으로 단위를 바꾸지 않는다. 좌표는 mm 로 넣는다(어댑터의 `units`·`scale` 옵션으로 바꾼다) |
| `frame.x_label` · `frame.y_label` | `null` · `null` | 지도 축 이름. 비우면 화면 사전의 `x [mm]`·`y [mm]`. 화면 말(`lang`)이 spec 의 `lang` 과 같을 때만 쓰고, 다르면 사전의 기본 이름을 쓴다 |
| `frame.x_left_positive` | `false` | `true` 면 지도에서 +x 를 왼쪽에 그린다(로봇 뒤에서 앞을 본 모습). 쪽 표의 '왼쪽'도 이 방향을 따른다 |
| `frame.note` | `""` | 메모 |
| `area` | `null` | 집는·놓는 자리의 목표 영역 `{"x": [lo, hi], "y": [lo, hi]}`. 없으면 데이터 범위 + 30 mm(결과 `notes` 에 `area_from_data`) |
| `scales.h_xy_mm` | `30.0` | 육각 칸 반지름 = 거리 눈금(mm) |
| `scales.h_yaw_deg` | `20.0` | 방향 칸 반폭(°). 방향 칸 폭은 2·h_yaw |
| `scales.use_yaw` | `true` | 데이터에 yaw 가 있으면 칸에 방향도 넣는다 |
| `scales.yaw_period_deg` | (360) | 분석의 방향 칸 주기. DEFAULTS 에는 없고 코드 기본이 360 이다. 평행 그리퍼처럼 180° 대칭이면 180 |
| `near_mm` | `100.0` | 이 거리 이하로 옮기면 '가까이' |
| `targets.rho_max` · `rho_bad` | `0.3` · `0.5` | \|ρ\| 문턱(좋음 · 주의) |
| `targets.near_share` · `near_warn` | `0.25` · `0.10` | 가까이 비율 문턱 |
| `targets.predict_good` · `predict_bad` | `0.65` · `0.80` | 출발만으로 목표 쪽 맞힘 문턱 |
| `targets.coverage_good` · `coverage_warn` | `0.80` · `0.50` | 칸 채움 문턱 |
| `targets.strata_dev_good` · `strata_dev_bad` | `0.10` · `0.25` | 이산 칸 비율 치우침 문턱 |
| `targets.dup_mm` | `12.0` | 이 거리 안이면 같은 자리(서로 다른 자리 묶음·같은 자리 짝) |
| `strata` | `[]` | 고르게 채울 이산 칸 `[{"name", "values", "shares"}]`. `shares` 가 없으면 고르게 |
| `pairs` | `[["start.x","goal.x"], ["start.y","goal.y"]]` | 지름길 상관을 볼 (출발, 목표) 특징 짝 |
| `side_split` | (`"range_mid"`) | 쪽 표 기준선. 숫자면 그 값, `"area_mid"` 면 목표 영역 가운데, 기본은 출발 값 범위 가운데 |
| `lang` | `"ko"` | 화면 말 `ko` · `en` |
| `dataset_colors` | `{}` | `{데이터셋 이름: "#RRGGBB"}`. 없으면 Okabe–Ito 순서 |

특징 이름은 에피소드 dict 의 점 경로다. `start.x` · `goal.yaw` · `discrete.goal_slot` · `extra.duration_s` 처럼 쓴다.
`strata[].name` 은 먼저 `discrete.<name>` 을 찾고, 없으면 같은 이름의 점 경로로 본다.

```json
"strata": [
  {"name": "color", "values": ["red", "green", "black"], "shares": [0.375, 0.375, 0.25]},
  {"name": "start_slot", "values": [0, 1, 2, 3]}
]
```

쪽 표의 축은 `pairs` 중 처음 나오는 같은 축 짝(`start.x`·`goal.x` 또는 `start.y`·`goal.y`)이다. 없으면 x 다.

## 3. 추천 공통 키

| 키 | 기본 | 뜻 |
|---|---|---|
| `holdout` | `0` | 시험 전용으로 떼어 둘 배치 수(k-center). 0 이면 안 뗀다 |
| `recommend.n_cand` | `4096` | 한 번에 뽑는 후보 수 |
| `recommend.top_k` | `30` | softmax 로 고를 상위 후보 수 |
| `recommend.temp` | `0.15` | softmax 온도. 0 이면 점수 1등 |
| `recommend.seed` | `null` | 시드. `--seed` 가 먼저다. 둘 다 없으면 매번 다르다 |
| `recommend.weights.alpha` | `0.5` | 옮김 방향 σ²_r 무게 |
| `recommend.weights.beta` | `0.3` | 이산 칸 항 무게 |
| `recommend.weights.eta` | `1.0` | 상관 항 무게 |
| `recommend.weights.gamma` | `0.15` | 수고 항 무게 |
| `recommend.weights.bad_view` | (0.8) | 인식 실패 자리 벌점 무게(코드 기본) |
| `recommend.lambda` | (0.05) | 가우스 과정 잡음 λ(판 무게로 나눈다) |
| `recommend.rho_v2_n` | (10) | 새 데이터셋 판이 이 수 이상이면 상관 항이 '새 데이터셋만'의 상관도 본다 |
| `recommend.n_plan` | (20) | final 훅(비싼 검사)을 부를 수 있는 횟수 |
| `recommend.n_reach` | (4 × n_cand) | 놓을 수 있는 칸을 셀 때 뽑는 후보 수(고정 시드 20261102) |
| `recommend.auto_strata` | (`true`) | 이산 칸 묶음에 '가까이'(목표 near_share)와 '장애물 이웃'(50/50)을 자동으로 더한다 |
| `recommend.rho_pairs` | (`pairs` 첫 짝) | 상관 항이 줄일 짝. 예 `[["start.x", "goal.x"]]` |
| `recommend.target_dataset` | (마지막 데이터셋) | '지금 모으는 묶음'. 데이터셋이 하나면 합친 상관만 본다 |

괄호 안 기본은 `spec.DEFAULTS` 에 없고 코드가 쓰는 값이다. 각 항의 식은 [RECOMMEND.md 4절](RECOMMEND.md#4-점수)에 있다.

## 4. layout — 추천이 고르는 배치

`layout` 이 없으면 `{"kind": "points"}` 로 본다. `area` 가 없으면 추천도 데이터 범위 + 30 mm 를 영역으로 쓴다.

### 4.1 points

집는 자리·놓는 자리를 영역 안에서 직접 고른다.

| 키 | 기본 | 뜻 |
|---|---|---|
| `kind` | `"points"` | |
| `min_move_mm` | `0` | 집는 → 놓는 거리 하한. 0 보다 크면 자동 검사 `min_move` 가 붙는다 |
| `start_area` · `goal_area` | `null` | 집는·놓는 자리를 뽑는 영역(`{"x", "y"}`). 없으면 `area` |
| `start_yaw` · `goal_yaw` | `null` | `[lo, hi]` 를 주면 그 범위에서 yaw 도 뽑고 거리·칸에 넣는다. 없으면 방향을 안 본다 |
| `yaw_period_deg` | `360` | 방향 주기 |
| `start_z_mm` · `goal_z_mm` | `0` | 화면 검사(`in_view`)·정책 입력 칸에 쓰는 높이 |
| `yaw_window` | `null` | 방향 창(4.3) |
| `discrete` | `[]` | 추천이 함께 고르는 이산 변수 `[{"name", "values"}]` — 고르게 뽑는다 |

### 4.2 fixtures

받침 같은 고정물을 놓고 물건을 고정물의 칸(slot)에 둔다. 배치 하나 = (start 고정물 a 의 칸 ks, goal 고정물 b 의 칸 kg) + 고정물마다 (x, y, yaw) 다.

`layout.fixtures[]` — 고정물 형식마다 하나.

| 키 | 기본 | 뜻 |
|---|---|---|
| `name` | `fixture{i}` | 형식 이름. 인스턴스 이름은 `이름 + 번호`(예 `rack0`, `rack1`, `bin0`) |
| `count` | `1` | 인스턴스 수 |
| `size_mm` | `[100, 40]` | 윗판 길이 L · 폭 W(위에서 본 사각형) |
| `height_mm` | `0` | 높이(탁자 ~ 윗판). 가림 검사의 상자 높이 |
| `z_top_mm` | `table_z_mm + height_mm` | 윗판 높이(베이스 z) |
| `slots` · `pitch_mm` | `1` · `0` | 칸 수와 간격. 칸 i 가운데 = (i − (n−1)/2)·간격 |
| `slot_axis` | `"length"` | 칸 줄 방향. `"length"` 가 아니면 폭 방향으로 본다 |
| `slots_xy` | — | 칸 자리를 고정물 프레임 `[[u, v], ...]` 로 직접(주면 `slots`·`pitch_mm` 대신) |
| `hole_r_mm` | `0` | 구멍 반지름(표시물 띠 자리·에피소드 방향 찾기) |
| `yaw_range` | `null` | `[lo, hi]` 를 주면 그 안에서 줄 방향을 고르게 뽑는다 |
| `yaw_period_deg` | `180` | 줄 방향 주기(받침은 180°) |
| `poses` (또는 `pose`) | `null` | `[{"x","y","yaw"}, ...]` 를 주면 그 자리에 고정(뽑지 않는다). `count` 보다 적으면 오류 |
| `areas` | `null` | 인스턴스마다 가운데가 들 영역 `[{"x","y"}, ...]`. 없으면 `area` |
| `order` | `"x"` (`poses`·`areas` 가 있으면 `"fixed"`) | `"x"` 면 같은 형식끼리 x 작은 쪽부터 번호를 다시 매긴다(인식 순서와 같게). `"fixed"` 면 번호가 곧 역할 |

`layout.items[]` — 물건.

| 키 | 기본 | 뜻 |
|---|---|---|
| `name` | role | 이름. 화면 문장에 쓴다(`i18n.NAMES` 에 있으면 번역) |
| `role` | `"start"` | `start`(집는 것) · `goal`(놓을 곳 표시물) · `obstacle`(방해물). start·goal 이 하나씩 있어야 한다 |
| `on` | 첫 고정물 형식 | 놓이는 고정물 형식. obstacle 은 언제나 start 와 같은 고정물이다 |
| `symbol` | 이름 첫 글자 | 배치 글자(예 `Y○○R`) |
| `above_mm` | `0` | 꽂혔을 때 윗판 위로 나온 높이(가림 원기둥·`in_view` 꼭대기) |
| `cap_r_mm` · `cap_h_mm` · `tube_r_mm` | `0` · `0` · `cap_r_mm` | 뚜껑 반지름·높이, 몸통 반지름(가림 원기둥) |
| `h_mm` · `w_mm` · `gap_mm` | `0` · `3.0` · `1.5` | goal 표시물(링)의 높이·띠 폭·구멍 가장자리에서 띠 안쪽까지 |

그 밖의 `layout` 키.

| 키 | 기본 | 뜻 |
|---|---|---|
| `same_fixture_allowed` | `true` | start 와 goal 이 같은 고정물이어도 되나 |
| `yaw_window` | `null` | 고정물 줄 방향 창(4.3) |
| `discrete` | `[]` | 추천이 함께 고르는 이산 변수(예 뚜껑 색) |
| `rule` | `null` | `{"by": 이산 변수, "goal": {값: {"fixture": 형식, "index": 번호}}, "start_differs": true}` — 값마다 goal 고정물을 정한다. `start_differs` 면 start 는 goal 이 아닌 고정물 |
| `episode_yaw_offset_deg` | `null` | 에피소드에 고정물 자세가 없을 때 `start/goal.yaw + 이 값` 을 줄 방향으로 본다(4.3) |
| `table_z_mm` | `0` | 탁자 높이 |

### 4.3 방향(ψ)

고정물 줄 방향은 다음 순서로 뽑는다. `yaw_range` 가 있으면 그 범위, 없고 `yaw_window` 가 있으면 그 자리의 창 가운데 ± 반폭, 둘 다 없으면 전 범위다.

```json
"yaw_window": {"center_deg": -82.0, "half_deg": 54.0}
"yaw_window": {"half_deg": 54.0, "grid": {"x": [...], "y": [...], "center_deg": [[...]]}}
```

`grid` 는 len(y) × len(x) 의 창 가운데 표이고 이중선형 보간한다. 받침 예제는 FR5 손목(J6)이 초기 자세 ±60° 안에 드는 줄 방향을 9×5 격자로 옮겨 적었다(로봇 모델 없이 같은 창을 쓰려고).

추천은 저장된 에피소드의 방향 특징 ψ 를 이렇게 정한다.

1. 에피소드에 `fixtures`(x, y, yaw)가 있으면 그 점에 가장 가까운 칸을 가진 고정물의 yaw(거리 max(hole_r, 간격/2, 15) + 10 mm 안일 때).
2. 아니면 `start/goal.yaw + episode_yaw_offset_deg`. 받침 예제는 −90° 다(손가락이 줄에 수직으로 잡으므로 잡는 손목 각 − 90° = 줄 방향).
3. 둘 다 없으면 그 자리 창 가운데(창이 없으면 방향 칸 가운데).

분석의 방향 칸은 이와 다르다. 분석은 에피소드의 `yaw` 를 그대로 쓰고, 창 가운데가 숫자(`center_deg`)가 아니면 데이터 yaw 의 원형 중앙값을 쓴다([ANALYSIS.md 4.2](ANALYSIS.md#42-방향-칸)).

## 5. constraints — 놓을 수 있는 배치 검사

후보마다 아래 순서로 검사하고, 처음 걸린 검사에 센다(결과 `recommend.drop`).

자동 검사(spec 에 안 적어도 붙는다):

| 이름 | 조건 |
|---|---|
| `area` | 집는·놓는 자리가 `area` 안 |
| `min_move` | points 이고 `min_move_mm` > 0 일 때. 옮긴 거리 ≥ min_move_mm |
| `yaw_window` | `layout.yaw_window` 가 있을 때. 쓰는(start·goal) 고정물의 줄 방향이 창 안(+1e-6°) |

그다음 `constraints` 를 적힌 순서대로 돈다. 항목마다 `name` 을 주면 그 이름으로 센다(같은 이름은 `#2` 가 붙는다).

| type | 키(기본) | 조건 |
|---|---|---|
| `area` | `x`, `y`, `what`(`"points"`) | 더 좁은 영역. `what` 이 `fixtures` 면 윗판 네 모서리, `both` 면 둘 다 |
| `min_move` | `min_mm` | 옮긴 거리 하한 |
| `reach` | `min_mm`(0), `max_mm`(무한), `origin`([0, 0]) | 베이스에서 거리. fixtures 면 모든 고정물의 모든 칸, points 면 두 점 |
| `gap` | `min_mm`, `between`(모든 형식) | 고정물 윗판 사각형끼리 분리축(SAT) 틈 ≥ min_mm. points 에서는 건너뛴다 |
| `keepout` | `polygon` 또는 `circle {x, y, r}`, `margin_mm`(0), `what`(fixtures 면 `"fixtures"`, 아니면 `"points"`) | 금지 구역. 고정물은 사각형–원 거리, 다각형은 볼록 가정(SAT) |
| `yaw_window` | `center_deg`, `half_deg`, `grid` | layout 창 대신 따로 줄 때 |
| `in_view` | `camera`(첫 카메라), `margin_px`(16), `grow_mm`(0), `roi_px` | 고정물 바닥(탁자 높이, grow_mm 키움) 네 모서리가 화면(또는 roi 다각형) 안, 꼭대기(윗판 + 물건) 네 모서리가 화면 가장자리 margin 안. points 면 두 점(높이 start_z_mm · goal_z_mm) |
| `view_angle` | `camera`, `min_deg`(0) | 칸 줄과 위에서 본 카메라 시선 사이 각 ≥ min_deg(끝 쪽에서 보면 앞 물건이 뒤 칸을 가린다). fixtures 만 |
| `goal_visible` | `camera`, `min_frac`(0.7), `min_minor_px`(없으면 안 봄), `policy_px`(256), `margin_px`(16), `bonus` | goal 표시물 띠 16점 중 화면 안이고 start·장애물 원기둥과 다른 고정물 몸통에 안 가린 비율 ≥ min_frac, 정책 입력 크기로 줄인 띠 상의 짧은 지름 ≥ min_minor_px. `bonus` 는 보이면 점수에 더한다. fixtures 만 |
| `hook` | `fn`(`"module:function"`), `args`({}), `stage`(`"batch"`) | 사용자 함수. 아래 |

카메라가 없거나 모양이 틀린 검사, 그 배치 종류에서 뜻이 없는 검사는 건너뛰고 이유를 `recommend.skipped_checks` 에 남긴다(화면 '다음에 할 일' 아래 줄에도 보인다). 모르는 `type` 도 건너뛴다.

훅은 spec 파일 옆 폴더를 먼저 찾아 불러온다.

- `stage: "batch"`: `fn(C, ctx, **args)` → 후보마다 참·거짓 배열(N,). 튜플 `(배열, dict)` 를 돌려주면 dict 는 정보로 남는다. `C` 는 후보 묶음([RECOMMEND.md 2절](RECOMMEND.md#2-후보-뽑기)), `ctx` 는 `ctx.spec`·`ctx.lay`·`ctx.cams` 를 가진다.
- `stage: "final"`: `fn(option, ctx, **args)` → `bool` 또는 `(bool, 이유)`. 고른 뒤 선택지 후보 몇 개에만 돈다(예산 `recommend.n_plan`). 역기구학·계획 검사처럼 비싼 검사를 넣는 자리다. layoutkit 에는 로봇 모델이 없어 계획 검사가 들어 있지 않다.

```python
# examples/capstone_colorsort/colorsort_hooks.py — 옮기는 직선이 다른 받침 위를 지나지 않게
def path_clear(C, ctx, clear_mm=20.0, n_pts=12):
    ...
    return ok            # (N,) bool
```

## 6. cameras

`in_view`·`view_angle`·`goal_visible` 와 정책 입력 칸 항이 쓴다.

| 키 | 기본 | 뜻 |
|---|---|---|
| `name` | `"cam"` | 검사의 `camera` 가 가리키는 이름 |
| `width` · `height` | (필수) | 화면 크기(px) |
| `K` | (필수) | 3×3 내부 행렬. `K[0][1]` 은 기울기 |
| `dist` | `null` | 브라운 왜곡 `[k1, k2, p1, p2, k3]`(librealsense 순서) |
| `dist_flip` | `false` | `true` 면 다항식 방향을 바꾼다(투영 = 다항식의 반복 역). fr5auto `camera.Cam(intr, flip)` 과 같은 뜻 |
| `T_cam_base` | — | 4×4, X_cam = T · X_base. 없으면 `T_base_cam`(카메라 자세)을 뒤집어 쓴다. 둘 다 없으면 그 카메라를 건너뛴다 |
| `policy_px` | `256` | 정책 입력 크기(정사각, 돌림·크롭 없이 줄임) |
| `img_grid` | `8` | 정책 입력 칸 나눔(8×8) |
| `policy_weight` | `0.0` | 점수의 정책 입력 칸 항 무게. 0 이면 안 쓴다 |

그 밖의 키(`dist_model`, `note` 등)는 읽지 않는다. 투영은 카메라 앞 1 mm 이하인 점을 NaN 으로 둔다.

## 7. 예: 받침 과제

[examples/rack_fr5/spec.json](../examples/rack_fr5/spec.json). FAIRINO FR5 실물 셀의 받침 과제다. 받침 2개(4칸), 빨강 튜브(start), 노랑 튜브(장애물), 빨간 링(goal).

| 키 | 값 |
|---|---|
| `frame.x_left_positive` | `true`(+x = 로봇 왼쪽) |
| `area` | x −200~270 · y 450~650 mm |
| `scales` | h 30 mm · h_yaw 20° |
| `strata` | `start_slot`·`goal_slot` 0~3 고르게 |
| `cameras` | 실물 3인칭 1대(848×480, 2026-11-03 보정, `dist_flip: true`, `policy_weight` 0.4) |
| `layout.fixtures` | `rack` × 2: 170 × 40 mm, 높이 60, 윗판 z 106.44, 칸 4 · 간격 37.18 mm, 구멍 반지름 15 |
| `layout.items` | red(start, above 50 mm) · yellow(obstacle) · ring(goal, h 5 mm) |
| `layout.yaw_window` | 반폭 54°, 가운데 9×5 격자(목표 영역 가운데 약 −82°) |
| `layout.episode_yaw_offset_deg` | −90 |
| `constraints` | reach 150~900 · in_view(margin 16 px, grow 20 mm) · gap 60 mm · view_angle 35° · goal_visible(0.7, 짧은 지름 8 px, bonus 0.2) |
| `holdout` | 12 |

이 spec 에서 고정 시드 후보 16384개 중 검사를 다 통과하는 배치는 121개다. 검사별로 처음 걸린 수는 area 11223 · in_view 2473 · gap 1305 · view_angle 1069 · goal_visible 보임 비율 26 · 짧은 지름 167 이다(yaw_window 는 0 — 뽑을 때 이미 창 안에서 뽑는다. reach 도 0).

## 8. 예: 캡스톤 색 분류

[examples/capstone_colorsort/spec.json](../examples/capstone_colorsort/spec.json). 뚜껑 색(빨강·초록·검정)에 따라 튜브를 정해진 받침이나 버림 통으로 옮긴다. 치수와 자리는 예제 값이다. 아래는 `layout` 을 줄여 옮긴 것이다(설명 키·가림 치수 일부를 뺐다).

```json
"layout": {
  "kind": "fixtures",
  "fixtures": [
    {"name": "rack", "count": 2, "size_mm": [170, 40], "height_mm": 60, "slots": 4, "pitch_mm": 37, "hole_r_mm": 15,
     "yaw_range": [-30, 30], "order": "fixed"},
    {"name": "bin", "count": 1, "size_mm": [110, 110], "height_mm": 80, "slots": 1, "poses": [{"x": 0, "y": 630, "yaw": 0}]}
  ],
  "items": [{"name": "tube", "role": "start", "on": "rack", "above_mm": 50, "cap_r_mm": 17.5},
            {"name": "place", "role": "goal", "on": "rack"}],
  "discrete": [{"name": "color", "values": ["red", "green", "black"]}],
  "rule": {"by": "color", "start_differs": true,
           "goal": {"red": {"fixture": "rack", "index": 0}, "green": {"fixture": "rack", "index": 1},
                    "black": {"fixture": "bin", "index": 0}}},
  "same_fixture_allowed": false
}
```

- `order: "fixed"` — `rack0` 은 빨강 받침, `rack1` 은 초록 받침이다. 번호가 역할이라 x 로 다시 매기지 않는다.
- `bin` 은 `poses` 로 고정, 칸 하나다. 칸 하나뿐인 고정물의 goal 칸은 `goal_slot` 균형에 넣지 않는다.
- `strata`: `color`(목표 비율 0.375 : 0.375 : 0.25) · `start_slot` · `goal_slot`.
- `constraints`: reach 300~760 · gap 40 · keepout(로봇 앞 가운데 거치대 자리, 여유 10 mm) · hook `colorsort_hooks:path_clear`.

## 9. 예: points 최소

고정물 없이 물체를 집어 다른 자리에 놓는 과제다. 아래 spec 과 표(`pick_x`·`pick_y`·`place_x`·`place_y` 열)로 `recommend` 가 돈다.

```json
{
 "task": "cube_pick_place",
 "area": {"x": [250, 450], "y": [-200, 200]},
 "scales": {"h_xy_mm": 30.0, "use_yaw": false},
 "layout": {"kind": "points", "min_move_mm": 60},
 "constraints": [
  {"type": "reach", "min_mm": 200, "max_mm": 600},
  {"type": "keepout", "circle": {"x": 350, "y": 0, "r": 30}, "margin_mm": 10}
 ],
 "holdout": 4
}
```

points 에서는 `gap`·`view_angle`·`goal_visible` 이 뜻이 없어 건너뛴다. 카메라를 주면 `in_view` 는 두 점(높이 `start_z_mm`·`goal_z_mm`)으로 본다.

## 10. init-spec 짐작

`layoutkit init-spec DATA... --out spec.json` 이 데이터로 spec 을 짐작한다.

- `area`: 집은·놓은 자리 범위 + 30 mm 를 10 mm 단위로 바깥쪽에 맞춘다.
- `scales.h_xy_mm`: 영역 짧은 변이 240 mm 이상이면 30, 아니면 짧은 변 / 8(최소 5).
- `strata`: 값 종류가 2~8개인 정수 `discrete` 키 전부(값은 데이터에 나온 것만).
- `scales.use_yaw`: 데이터에 yaw 가 있으면 참.
- `frame.x_left_positive`: `false`.

화면 방향과 영역, strata 는 짐작이다. 받침 v1 꼬리표에서 짐작하면 `obstacle_slot`(값 0·3)·`start_fixture` 같은 키도 strata 에 들어간다. 쓰기 전에 고친다.
