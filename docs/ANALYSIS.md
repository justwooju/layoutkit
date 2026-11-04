# 분석 지표

`layoutkit analyze` 가 계산하는 지표마다 정의·식·문턱·읽는 법을 적는다. 예로 드는 숫자는 받침 v1(`examples/rack_fr5/data/v1_tags.json`, 100판, 무게 0.5)을 혼자 분석한 값이다.
코드는 `layoutkit/analyze/` 다. 결과 dict 모양은 [ARCHITECTURE.md 3절](ARCHITECTURE.md#3-분석-결과result-모양)에 있다.

## 목차

1. [쓰는 에피소드와 무게](#1-쓰는-에피소드와-무게)
2. [지름길](#2-지름길)
3. [옮긴 거리](#3-옮긴-거리)
4. [칸 채움](#4-칸-채움)
5. [서로 다른 자리와 같은 자리 짝](#5-서로-다른-자리와-같은-자리-짝)
6. [이산 칸](#6-이산-칸)
7. [신호등 카드](#7-신호등-카드)
8. [데이터셋 비교](#8-데이터셋-비교)
9. [실행 기록](#9-실행-기록)
10. [받침 v1 · v2 숫자](#10-받침-v1--v2-숫자)
11. [참고문헌](#참고문헌)

## 1. 쓰는 에피소드와 무게

에피소드 하나는 집은 자리 `start`(x, y[, yaw, z])와 놓은 자리 `goal` 을 가진다. 둘 다 있어야 분석에 쓸 수 있다.

| 구분 | 조건 | 결과에서 |
|---|---|---|
| 쓴 판 | 자리가 있고 `outcome` 이 `success` 또는 없음 | 모든 지표 |
| 결과로 뺀 판 | 자리는 있는데 `outcome` 이 그 밖(`fail` · `unsure` …) | `episodes` 에 `excluded` 깃발, 칸 번호·옮긴 거리만 |
| 못 쓴 판 | 자리가 하나라도 없다 | `unusable` 목록 |

`--all-outcomes`(파이썬 `outcomes=None`)면 결과와 상관없이 다 쓴다.

판 무게 w = 데이터셋 무게 × 에피소드 무게다. 예전 데이터를 학습 때 덜 뽑을 생각이면(예 v1 0.5) 그 비율을 무게로 준다.
무게는 상관 ρ, 가까이 비율, 칸 셈(`count`), 이산 칸 비율, 쪽 표의 `acc_w` 에 들어간다. 최근접 이웃 맞힘, 쪽 표 칸 수, 채운 칸 수, 서로 다른 자리 수는 무게 없이 센다.

분석이 붙이는 깃발은 `dup`(같은 자리 짝의 뒤 판) · `near`(가까이 옮김) · `out_of_area`(영역 밖 자리) · `excluded` 다.

## 2. 지름길

모방 학습은 행동을 실제로 정하는 원인(화면 속 놓을 곳)보다 행동과 같이 움직이는 쉬운 단서가 있으면 쉬운 단서를 배운다 [de Haan et al. 2019; Geirhos et al. 2020].
집는 자리만 보면 놓는 자리를 맞힐 수 있는 데이터에서는 정책이 카메라를 덜 보고도 학습 손실을 낮출 수 있다. 세 숫자로 잰다.

### 2.1 가중 상관

`spec.pairs` 의 (출발 특징 a, 목표 특징 b) 짝마다 무게를 준 Pearson 상관이다(`coupling.wcorr`).

$$\bar x = \frac{\sum_i w_i x_i}{\sum_i w_i}, \qquad \rho_w = \frac{\sum_i w_i (x_i - \bar x)(y_i - \bar y)}{\sqrt{\sum_i w_i (x_i - \bar x)^2 \sum_i w_i (y_i - \bar y)^2}}$$

판이 3개 아래이거나 한쪽 분산이 0 이면 값이 없다. `rho` 는 합친 데이터(무게 있음), `rho_by_ds` 는 데이터셋마다(무게 없음)다.
v1: ρ(start.x, goal.x) = −0.807, ρ(start.y, goal.y) = −0.428. 빨강이 한쪽에 있으면 링은 거의 반대쪽이었다는 뜻이다.

### 2.2 쪽 표

쪽 표 축은 `pairs` 에서 처음 나오는 같은 축 짝(기본 x)이다. 기준선은 출발 값 범위의 가운데 (min + max) / 2 다(fr5auto `rackrec.diagnose` 와 같다). `spec.side_split` 에 숫자를 주면 그 값, `"area_mid"` 면 목표 영역 가운데다.

표는 2 × 2 이고 화면 방향을 따른다. 행 = 출발 쪽 [화면 왼쪽, 오른쪽], 열 = 목표 쪽 [화면 오른쪽, 왼쪽] 이라 대각선이 '건너편으로 옮김'이다. `frame.x_left_positive` 면 화면 왼쪽 = 기준선보다 큰 값이다.

$$\mathrm{acc}_\text{side} = \frac{1}{n}\sum_{\text{행}} \max(\text{행의 두 칸})$$

출발 쪽만 알 때 목표 쪽을 행마다 많은 쪽으로 찍으면 맞히는 비율이다. `acc_w` 는 같은 것을 무게로 센 값, `n_cross` 는 대각선 합이다.

v1: 기준선 x = 64.9, 표 [[44, 0], [4, 52]]. 왼쪽(x > 64.9)에서 집은 44판은 모두 오른쪽에 놓았고, 오른쪽에서 집은 56판 중 52판은 왼쪽에 놓았다. acc = (44 + 52) / 100 = 0.96.

### 2.3 최근접 이웃 맞힘

쪽 표는 기준선 하나로 나눈다. 출발 자리가 몇 곳에 몰려 있으면 기준선과 상관없이 목표 쪽이 정해질 수 있다. 그래서 출발 xy 만 보고 목표 쪽(goal[축] > 기준선)을 맞히는 k-최근접 이웃 분류를 한 판씩 빼고(leave-one-out) 돌린다.

- k = min(5, n − 1), 이웃 다수결, 비기면 많은 쪽.
- `knn_acc` = 맞힌 비율, `chance` = 목표 쪽 중 많은 쪽 비율(아무것도 안 보고 많은 쪽을 찍을 때).
- 판이 4개 아래면 값이 없다.

v1: knn_acc 1.00, chance 0.52. 출발 자리만으로 목표 쪽을 100판 모두 맞힌다. v2(19판): 0.58, chance 0.63 — 우연보다 낮다.

## 3. 옮긴 거리

옮긴 거리 = 집은 자리와 놓은 자리의 xy 거리다. `near_mm`(기본 100 mm) 이하면 '가까이'다.

$$d_i = \lVert (x^g_i, y^g_i) - (x^s_i, y^s_i) \rVert, \qquad \text{near share} = \frac{\sum_i w_i\,\mathbf 1[d_i \le \text{near mm}]}{\sum_i w_i}$$

결과 `transfer` 는 값 목록, 최소·중앙·최대, `near_share`(무게), `near_n`(판 수)이다.
가까이 옮긴 판이 없으면 정책은 '먼 곳으로 옮기기'만 본다. 시험에서 가까운 목표가 나오면 학습 때 없던 움직임이다.

v1: 118~380 mm, 중앙 232 mm, 100 mm 이하 0판.

## 4. 칸 채움

### 4.1 육각 칸

목표 영역 가운데에 맞춘 반지름 h(`scales.h_xy_mm`) 육각 배열이다(`coverage.hex_centers`, fr5auto `rackrec` 과 같다). 칸 가운데 간격 √3·h, 줄 사이 1.5·h, 줄은 영역의 긴 변 방향이다. 영역 안에 든 가운데만 칸이 된다.
점은 가장 가까운 칸에 들고, 영역 밖 점은 −1 이다. 칸마다 무게 합(`count`), 판 수(`n`), 데이터셋별 판 수(`count_by_ds`)를 센다. 채운 칸 = 판이 하나라도 든 칸이다.

v1 영역(x −200~270 · y 450~650, h 30 mm): 47칸 중 집은 자리 20칸, 놓은 자리 27칸.

### 4.2 방향 칸

`scales.use_yaw` 이고 yaw 가 있는 에피소드가 있으면 방향 칸을 더한다. 폭은 2·h_yaw 다.

- 창 가운데: `layout.yaw_window.center_deg`(또는 숫자 `center`)가 있으면 그 값, 없으면 데이터 yaw 의 원형 중앙값.
- 창 반폭: `layout.yaw_window.half_deg`, 없으면 데이터 yaw 가 퍼진 만큼(최소 h_yaw).
- 칸 수 Y = ⌈2·반폭 / 폭⌉. 창 밖 yaw 는 가장자리 칸에 넣는다. 주기는 `scales.yaw_period_deg`(기본 360).

받침 spec 의 창은 격자라 가운데가 숫자가 아니다. 그래서 v1 의 방향 칸은 데이터 yaw(잡는 손목 각 77.2°) 가운데 ± 54°, 3칸이다. v1 은 100판의 yaw 가 모두 같아 방향 칸을 더해도 채운 칸 수가 그대로다.

추천의 방향 칸은 정의가 다르다. 추천은 고정물 줄 방향(에피소드 yaw + `episode_yaw_offset_deg`, 주기 180°)으로 센다([SPEC.md 4.3](SPEC.md#43-방향ψ)). 두 값을 섞어 읽지 않는다.

### 4.3 이론 칸 수와 쿠폰 수집

평면을 반지름 h 원으로 빈틈없이 덮는 가장 적은 배치는 육각 배열이고 원 하나가 맡는 넓이는 (3√3/2)h² 다 [Kershner 1939].

$$N_{xy} = \left\lceil \frac{A}{(3\sqrt3/2)\,h^2} \right\rceil, \qquad N_\text{theory} = N_{xy}\cdot\max(1, Y)$$

무작위로 놓을 때 n 칸을 다 채우는 데 드는 판 수의 기댓값은 쿠폰 수집 문제의 n·H_n 이다.

$$\mathbb E[T_n] = n\left(1 + \tfrac12 + \dots + \tfrac1n\right)$$

v1: A = 470 × 200 mm² → N_xy = 41(`n_hex`), Y = 3, N_theory = 123, 무작위 기댓값 663.4판(`coupon_random`). 칸을 골라 채우면 약 123판이다.
공식 칸 수(41)와 실제 배열 칸 수(47)는 다르다. 채움 비율·N_min 의 분모는 배열 칸이나 놓을 수 있는 칸을 쓰고, 공식 값은 이론 하한으로만 보인다.

### 4.4 놓을 수 있는 칸과 N_min

분석만으로는 어느 칸에 실제로 놓을 수 있는지 모른다(로봇 닿음·카메라 시야·고정물 틈 검사가 필요하다). 그래서 `reach` 는 처음에 `null` 이고, 추천을 같이 돌리면 추천이 센 '검사를 통과한 후보가 하나라도 드는 칸'으로 채운다([RECOMMEND.md 3절](RECOMMEND.md#3-놓을-수-있는-칸)).

$$N_\text{min} = \max\big(|R_s| - |F_s \cap R_s|,\ |R_g| - |F_g \cap R_g|\big)$$

R = 놓을 수 있는 칸, F = 채운 칸, s·g = 집는·놓는 쪽이다. 판 하나는 집는 칸 하나와 놓는 칸 하나만 채우므로 고르게 설계해도 이보다 적게는 못 채운다.
`reach` 가 없으면 칸 전부를 놓을 수 있다고 본다(`n_min_basis: "all"`). 방향 칸까지 친 값은 `n_min_yaw` 다.

v1 혼자(reach 없음): N_min = 47 − 20 = 27, 방향 칸까지 141 − 20 = 121. v1 + v2 + 추천(reach 있음): 놓을 수 있는 칸 집는 42 · 놓는 26, 채움 24 · 20 → N_min 18.

화면 '다음에 할 일'의 "앞으로 필요한 판"은 추천을 돌렸으면 추천이 센 (자리, 방향) 칸 기준 값(`recommend.cells.n_min`)을 보인다. 받침 예제에서는 39 다. 명령 출력과 `cards.csv` 의 n_min 카드 값(18)은 자리 칸 기준이다. 두 값은 칸 정의가 달라 다르다.

### 4.5 채움 거리

빈 곳의 크기다. 모든 점(집은·놓은 자리 합침)의 볼록 껍질을 만들고, 껍질 안 격자점에서 그 쪽(집은 자리 또는 놓은 자리) 가장 가까운 점까지 거리의 최댓값을 잰다.

$$h_\text{fill}(P) = \max_{u \in \mathrm{hull}} \min_{p \in P} \lVert u - p \rVert$$

격자 간격은 max(1 mm, √(껍질 넓이 / 60000))다. 판이 3개 아래면 값이 없다.
v1: 집은 자리 61.5 mm, 놓은 자리 55.9 mm(껍질 0.0593 m²). 반지름 약 60 mm 원 안에 판이 하나도 없는 곳이 있다는 뜻이다.

## 5. 서로 다른 자리와 같은 자리 짝

서로 다른 자리 수는 `dup_mm`(기본 12 mm) 욕심 묶음으로 센다(fr5auto `rackrec.clusters` 와 같다). 앞에서부터 아직 묶이지 않은 점 하나를 잡고, 그 점에서 12 mm 안(엄격히 작음)인 묶이지 않은 점을 같은 묶음에 넣는다. 읽은 순서가 결과를 정하므로 순서를 지킨다.

- `spots.start` · `spots.goal`: 집은 자리·놓은 자리 묶음 수.
- `spots.pairs`: (집은 묶음, 놓은 묶음) 짝의 종류 수.

같은 자리 짝은 집은 자리끼리, 놓은 자리끼리 모두 12 mm 안인 두 판이다. 뒤 판에 `dup` 깃발이 붙는다.

v1: 서로 다른 자리 32 · 43 · 99. 같은 자리 짝 1쌍(ep_044–ep_050, 7.9 mm).

판끼리 자리가 겹치는 것 자체는 문제가 아니다. 다만 같은 배치를 여러 번 모으면 배치 수가 늘지 않는다. 일반화는 시연 수보다 환경·물체 수에 더 크게 좌우된다 [Lin et al. 2025].

## 6. 이산 칸

`spec.strata` 마다(예: 집는 칸 번호 0~3) 값별 판 수와 무게 비율을 센다. 목표 비율 `shares` 가 없으면 고르게다.

$$\text{share}_v = \frac{\sum_{i: k_i = v} w_i}{\sum_{i: k_i \ne \varnothing} w_i}, \qquad \text{max dev} = \max_v \left|\text{share}_v - \text{target}_v\right|$$

값은 `discrete.<name>` 을 먼저 보고, 없으면 같은 이름의 점 경로로 본다. 목록에 없는 값은 `n_other` 로 센다.
결과 `discrete` 는 strata 와 상관없이 에피소드의 모든 이산 키의 값 셈이다(값 종류 24개 이하).

v1: 집는 칸 31 / 16 / 8 / 45(3번이 0.45 — 고르면 0.25, max_dev 0.20), 놓는 칸 25 / 22 / 25 / 28. 빨강·노랑 배치는 `Y○○R` 45 · `R○○Y` 31 · `○R○Y` 16 · `Y○R○` 8 의 네 가지뿐이다.
칸 번호가 몰리면 정책은 "끝 칸에서 집는다" 같은 다른 단서를 얻는다.

## 7. 신호등 카드

`analyze/verdict.py` 가 만든다. 문턱은 `spec.targets` 다.

| id | 값 | 좋음 | 주의 | 나쁨 | 화면 이름 |
|---|---|---|---|---|---|
| coupling | `pairs` 중 가장 큰 \|ρ\| | ≤ 0.3 | ≤ 0.5 | 그 위 | 집는↔놓는 곳 상관 |
| predict | 최근접 이웃 맞힘 | ≤ 0.65 | ≤ 0.80 | 그 위 | 놓는 쪽 맞히기 |
| near | 가까이 비율(무게) | ≥ 0.25 | ≥ 0.10 | 그 아래 | 가까이 옮기기 |
| coverage | 채운 칸 / 놓을 수 있는 칸(모르면 / 전체), 집는·놓는 쪽 중 낮은 것 | ≥ 0.80 | ≥ 0.50 | 그 아래 | 칸 채움 |
| strata | 이산 칸 max_dev 중 가장 큰 것 | ≤ 0.10 | ≤ 0.25 | 그 위 | 칸 번호 고르기 |
| dups | 같은 자리 짝의 뒤 판 수 / 쓴 판 수 | 정보 | | | 같은 자리 반복 |
| n_min | N_min | 정보 | | | 앞으로 필요한 판 |

카드는 `code` 와 `args` 만 가진다(예 `coupling_high`, `{"pair": "start.x→goal.x", "rho": -0.807}`). 화면이 사전 틀에 넣어 "왜"와 "할 일"을 쓴다. 값을 낼 수 없는 카드(판이 너무 적다 등)는 빠진다.

v1 혼자: coupling 나쁨 0.807 · predict 나쁨 1.00 · near 나쁨 0.00 · coverage 나쁨 0.43(20/47) · strata 주의 0.20 · dups 0.01 · n_min 27.

## 8. 데이터셋 비교

데이터셋이 둘 이상이면 `compare` 가 같은 지표를 데이터셋마다 나란히 낸다. 칸·영역은 합친 분석과 같은 것을 쓰고, 쪽 기준선은 데이터셋마다 그 데이터셋만 볼 때와 같게 정한다(데이터셋 하나만 분석한 숫자와 같다).

| key | 뜻 | 좋은 쪽 |
|---|---|---|
| `n` | 쓴 판 수 | |
| `rho:<a>→<b>` | 짝마다 ρ(부호 있음) | 0 근처 |
| `rho` | 가장 큰 \|ρ\| | 낮음 |
| `side_acc` · `predict` | 쪽 표 맞힘 · 최근접 이웃 맞힘 | 낮음 |
| `near_share` | 가까이 비율 | 높음 |
| `move_median` | 옮긴 거리 중앙 | |
| `filled_start` · `filled_goal` | 채운 칸 | 높음 |
| `spots_start` · `spots_goal` · `spots_pairs` | 서로 다른 자리 | 높음 |
| `strata_dev` | 이산 칸 max_dev 최대 | 낮음 |
| `same_fixture` · `same_fixture_n` | 같은 고정물 안에서 옮긴 비율 · 판 수(`discrete.same_fixture` 가 있을 때) | |

`diff` 는 마지막 데이터셋 − 첫 데이터셋이다.

## 9. 실행 기록

수집기 실행 기록(fr5auto `runs.jsonl` · `runs_*.csv`)을 주면 `runs` 에 요약한다(`analyze/runs.py`). 녹화가 안 된 실행·실패한 실행도 있어 에피소드 수와 다르다.

- `by_verdict` · `kept` · `decided_by`: 판정별·남긴 라벨별·누가 정했는지별 횟수. `success_rate`, `kept_rate`.
- `by_day`: 날짜마다 n · success · fail · unsure · other(그 밖의 판정) · kept · 실행 시간 중앙.
- `reasons`: 성공이 아닌 실행의 이유. 이유 글을 ` | ` 로 나눈 조각마다 규칙(정규식)으로 code 를 붙이고, 실행 한 번은 code 마다 한 번만 센다. 조각의 글 종류(숫자를 `#` 로 바꾼 것)도 센다.

| code | 맞추는 글(위에서부터 처음 맞는 것) |
|---|---|
| `fixture_lifted` | 뺄 때 받침이 같이 들렸 · lifted |
| `fixture_moved` | 받침이 움직였 · 받침이 조금 밀렸 · 칸 자리가 … 밀렸 · fixture/rack moved |
| `object_not_seen` | 안 보인다 · 떨어뜨렸 · not seen · dropped |
| `goal_state_unknown` | 꽂을/넣을 칸 상태 · goal state |
| `not_recorded` | 기록 시작 실패 · recording failed |
| `aborted` | 따라오지 않 · 중단 · abort |
| `other` | 그 밖 |

- `durations`: 실행 시간 통계(전체·판정별 n · 중앙 · 평균 · p10 · p90 · 최소 · 최대).
- `hover` · `servo`: fr5auto 닫힌 고리 보정 기록(내려가기 전 좌우 맞춤, 넣는 중 미세조정) 요약.

받침 예제 기록(2026-10-31 ~ 11-04): 200회, 성공 판정 148, 남김 149(불확실 하나를 사람이 남김). 성공이 아닌 52회의 이유는 fixture_moved 26 · goal_state_unknown 24 · fixture_lifted 15 · other 9 · not_recorded 2 · object_not_seen 2 · aborted 1 이다. 전체 실행 시간 중앙 23.0 s, 성공만 23.5 s.

## 10. 받침 v1 · v2 숫자

| 지표 | v1 (100판) | v2 (19판) | v1(무게 0.5) + v2 |
|---|---|---|---|
| ρ(start.x, goal.x) | −0.807 | −0.034 | −0.604 |
| ρ(start.y, goal.y) | −0.428 | −0.119 | −0.384 |
| 쪽 표 기준선 · 맞힘 | 64.9 · 0.96 | 30.1 · 0.632 | 31.2 · 0.908 |
| 최근접 이웃 맞힘(우연) | 1.00 (0.52) | 0.579 (0.632) | 0.908 (0.555) |
| 옮긴 거리 최소 · 중앙 · 최대 mm | 118 · 232 · 380 | 37 · 136.5 · 328 | 37 · 226 · 380 |
| 가까이(≤ 100 mm) | 0 % | 21 % (4판) | 5.8 %(무게) |
| 서로 다른 자리 집는 · 놓는 · 짝 | 32 · 43 · 99 | 19 · 19 · 19 | 49 · 56 · 118 |
| 채운 칸 집는 · 놓는 (47칸) | 20 · 27 | 15 · 15 | 26 · 31 |
| 같은 받침 안에서 옮김 | 0 | 8 | 8 |
| 채움 거리 집는 · 놓는 mm | 61.5 · 55.9 | 120.8 · 142.8 | 60.8 · 59.4 |

v2 는 fr5auto 배치 추천으로 모은 묶음이다. 19판만으로 상관이 0 근처로 내려가고 가까이 옮긴 판이 생겼다. 칸은 아직 덜 찼다(채움 거리가 크다).
v2 내보내기에는 yaw 가 없어 v2 혼자 분석할 때 방향 칸은 0 이다.

## 참고문헌

- de Haan, Jayaraman, Levine. Causal Confusion in Imitation Learning. NeurIPS 2019. https://arxiv.org/abs/1905.11979
- Geirhos et al. Shortcut Learning in Deep Neural Networks. Nature Machine Intelligence 2020. https://arxiv.org/abs/2004.07780
- Lin et al. Data Scaling Laws in Imitation Learning for Robotic Manipulation. ICLR 2025. https://arxiv.org/abs/2410.18647
- Kershner. The Number of Circles Covering a Set. American Journal of Mathematics, 1939.
