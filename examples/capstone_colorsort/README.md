# 캡스톤 예제 — 뚜껑 색으로 튜브 나누기

받침 2개(4칸씩)와 버림 통 하나, 50 mL 튜브 8개(뚜껑 빨강·초록·검정). 규칙은 **색 → 정해진 고정물**이다.
빨강은 빨강 받침(`rack0`)으로, 초록은 초록 받침(`rack1`)으로, 검정은 버림 통(`bin0`)으로 간다. 에피소드 하나가 튜브 하나를 옮긴다.
치수와 자리는 예제 값이다(실물 보정이 아니다).

## spec 에서 볼 곳

| 키 | 이 예제에서 |
|---|---|
| `layout.kind` | `fixtures` — 고정물을 놓고 물건을 그 칸에 둔다(`points` 면 집는·놓는 자리를 영역에서 직접 고른다) |
| `layout.fixtures` | `rack` × 2(자리·방향 ±30° 를 추천이 고름, `order: fixed` = 번호가 곧 역할) · `bin` × 1(`poses` 로 고정, 칸 1) |
| `layout.items` | `tube`(start, 받침 칸) · `place`(goal) |
| `layout.discrete` | 추천이 함께 고르는 이산 변수 `color` |
| `layout.rule` | `color` 값마다 goal 고정물. `start_differs` = 이미 제자리인 튜브는 옮기지 않는다 |
| `strata` | 고르게 채울 이산 칸: `color`(목표 비율 3 : 3 : 2) · `start_slot` · `goal_slot`(버림 통은 칸이 하나라 빠진다) |
| `constraints` | `reach` · `gap`(고정물 사이 40 mm) · `keepout`(로봇 앞 거치대 자리) · `hook`(옮기는 길이 다른 받침 위를 지나지 않게 — `colorsort_hooks.py`) |

빨강 받침이 늘 같은 쪽에 있으면 "출발 쪽만 보고 목표 쪽을 맞히는" 지름길이 생긴다. 그래서 두 받침의 자리는 영역 어디든 될 수 있게 두었다.

## 돌려 보기

```bash
python3 examples/capstone_colorsort/make_synth.py          # data/skewed.json · data/even.json (30판씩)
```

```python
import sys; sys.path.insert(0, "examples/capstone_colorsort")
from make_synth import load
from layoutkit import spec
from layoutkit.recommend import recommend

sp = spec.load("examples/capstone_colorsort/spec.json")
rec = recommend([load("examples/capstone_colorsort/data/skewed.json")], sp, n=3, seed=1)
for o in rec["options"]:
    print(o["label"], o["discrete"]["color"], o["start"], o["goal"], o["why_codes"])
```

두 묶음은 이렇게 다르다(시드 1).

| | 상관 \|ρ(start.x, goal.x)\| | 채운 (자리, 방향) 칸 start · goal | 앞으로 N_min |
|---|---|---|---|
| skewed 만 | 0.97 | 3 · 3 (놓을 수 있는 칸 52 · 48) | 49 |
| skewed + even | 0.70 | 20 · 14 | 34 |

`skewed` 는 받침 자리가 고정이고 빨강이 70 %, 칸이 끝 쪽(2·3 → 0·1)뿐이다. `even` 은 놓을 수 있는 배치 중 무작위이고 색은 목표 비율대로다.
추천 A·B·C 는 빈 칸을 먼저 채우고 상관을 낮추는 배치를 고른다. 이유는 `why_codes` 로 남는다(`empty_start_cell` · `lowers_coupling` · `balances_strata` …).
