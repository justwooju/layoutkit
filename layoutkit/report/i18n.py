"""화면 말 사전(ko/en). 분석 결과(result)는 코드·숫자만 담고, 사람이 읽는 글은 여기서 만든다.

- T[lang][key] — 패널 제목·범례·표 머리 등 고정 글.
- CARD[lang][code] — 신호등 카드 code 별 (왜, 할 일) 틀. args 와 카드 값으로 채운다.
- WHY[lang][code] — 추천 이유 코드, REASON[lang][code] — 수집 실패 이유 코드, FLAG, METRIC, NAMES(물체 이름).
모르는 코드는 일반 문장(카드 id·상태 기준)으로 대신한다 — 화면이 비지 않게.
"""
from __future__ import annotations

T = {
    "ko": {
        "lang": "ko",
        "status.good": "좋음", "status.warn": "주의", "status.bad": "나쁨", "status.info": "정보",
        "made": "만든 시각", "episodes_unit": "판", "cells_unit": "칸", "weight": "무게", "print": "인쇄",
        "datasets": "데이터셋", "toggle_hint": "눌러서 켜기/끄기",
        "target": "목표", "chance": "우연", "todo": "할 일", "why": "왜",
        # 카드 이름
        "card.coupling": "집는↔놓는 곳 상관", "card.predict": "놓는 쪽 맞히기",
        "card.near": "가까이 옮기기", "card.coverage": "칸 채움", "card.strata": "칸 번호 고르기",
        "card.dups": "같은 자리 반복", "card.n_min": "앞으로 필요한 판",
        "unit.pp": "%p 차이", "unit.pairs": "쌍", "unit.eps": "판",
        # 다음에 할 일
        "next.title": "다음에 할 일", "next.none": "추천 없음 — recommend 를 같이 돌리면 여기에 다음 배치가 나온다",
        "next.cmd": "layoutkit recommend DATA --spec spec.json",
        "next.feasible": "후보 {n_cand}개 중 조건을 통과한 배치 {n_feasible}개에서 골랐다",
        "next.skipped": "검사 못 한 조건: {checks}", "next.holdout": "시험 전용으로 떼어 둔 배치 {n}개(지도에 회색 ×)",
        "next.on_map": "지도에 점선으로 표시", "next.notes": "참고",
        "rec.put": "{item_obj} {pos}{empty}({xy})에", "rec.empty": " 빈 칸",
        "rec.goal_same": "{goal_top} 같은 {fixture} {slot}번 칸", "rec.goal_other": "{goal_top} 다른 {fixture} {slot}번 칸({pos})",
        "rec.goal_point": "{goal_top} {pos}({xy})", "rec.move": "{mm} mm 옮김",
        "pos.left": "왼쪽", "pos.right": "오른쪽", "pos.center": "가운데", "pos.top": "위", "pos.bottom": "아래",
        "pos.map": "지도 {p}",
        # 지도
        "map.title": "위에서 본 지도 — 어디서 집어 어디에 놓았나",
        "map.sub": "● 집는 곳 → ○ 놓는 곳 · 색 = 데이터셋 · 회색 영역 = 목표 영역 · 점선 = 추천 배치",
        "map.arrows": "화살표", "map.dots": "점만", "map.start": "집는 곳", "map.goal": "놓는 곳",
        "map.rec": "추천 배치", "map.area": "목표 영역", "map.cells": "칸(h {h:g} mm)", "map.fixture": "고정물",
        "map.holdout": "시험 배치(추천이 피함)", "map.holdout_tip": "시험 전용 배치 {id} — 학습용 추천이 피하는 자리", "map.left_is": "← +x(로봇 왼쪽)", "map.selected": "선택", "map.clear": "선택 지우기",
        "map.back": "표로 돌아가기 ↓",
        # 칸 지도
        "cells.title": "칸 지도 — 빈 곳은 어디인가",
        "cells.start": "집는 곳: 놓을 수 있는 {reach}칸 중 {filled}칸 채움 · 빈 칸 {empty}",
        "cells.goal": "놓는 곳: 놓을 수 있는 {reach}칸 중 {filled}칸 채움 · 빈 칸 {empty}",
        "cells.start_all": "집는 곳: {n}칸 중 {filled}칸 채움", "cells.goal_all": "놓는 곳: {n}칸 중 {filled}칸 채움",
        "cells.empty": "빈 칸(놓을 수 있음)", "cells.noreach": "놓을 수 없음", "cells.count": "판 수",
        "cells.tip": "칸 {k}", "cells.reach_yes": "놓을 수 있음", "cells.reach_no": "놓을 수 없음",
        "cells.rec": "추천 {labels}",
        # 지름길
        "sc.title": "지름길 — 집는 곳만 보고 놓는 곳을 알 수 있나",
        "sc.bad": "지름길 위험: 집는 곳만 보고도 놓는 쪽을 {acc} 맞힌다 (우연 {chance})",
        "sc.warn": "지름길 조금: 집는 곳으로 놓는 쪽을 {acc} 맞힌다 — 우연({chance})보다 높다",
        "sc.good": "지름길 없음: 놓는 쪽을 맞히는 정도가 우연({chance})에 가깝다 ({acc})",
        "sc.scatter": "{a} ↔ {b}", "sc.merged": "합침", "sc.table": "쪽 표 — 가운데 {axis} {split} mm 로 나눔",
        "sc.row": "집는 곳 {side}", "sc.col": "놓는 곳 {side}", "sc.rowline": "{a} → {b} {k}/{n}",
        "sc.gauge": "집는 곳으로 놓는 쪽 맞힘(최근접 {k}개)", "sc.gauge_side": "집는 쪽만으로 놓는 쪽 맞힘(쪽 표)", "sc.skew": "쏠림",
        "sc.left": "왼쪽", "sc.right": "오른쪽", "sc.split": "가운데",
        # 옮긴 거리
        "tr.title": "옮긴 거리 — 짧게 옮긴 판이 있나",
        "tr.x": "옮긴 거리 [mm] (집는 곳 → 놓는 곳)", "tr.y": "누적 비율",
        "tr.near": "가까이 ≤{mm} mm", "tr.target": "목표: 이 점보다 위({share} 이상)",
        "tr.legend": "{name} · 가까이 {near} · 중앙 {med} mm",
        # 이산 칸
        "st.title": "칸 번호 — 고르게 나왔나",
        "st.sub": "가장 큰 차이 {dev} (목표 ≤ {good})", "st.even": "고르게", "st.more": "많음", "st.less": "적음",
        "st.share": "비율",
        # 비교
        "cmp.title": "데이터셋 비교 — 같은 지표 나란히", "cmp.low": "낮을수록 좋음", "cmp.high": "높을수록 좋음", "cmp.zero": "0에 가까울수록 좋음",
        # 시간표
        "tl.title": "시간표 — 언제 모았고 결과는 어땠나",
        "tl.sub": "에피소드를 시각 순으로(가로 = 순서, 세로선 = 날짜 바뀜)",
        "runs.title": "수집 기록 — 날짜별 결과 (남김/전체)", "runs.reasons": "성공이 아닌 {n}회의 이유 (한 회에 여럿일 수 있다)",
        "runs.sub": "자동 수집 {n}회 중 {kept}판 남김 · 한 판 중앙 {med} s",
        "runs.y": "회",
        # 결과
        "oc.success": "성공", "oc.fail": "실패", "oc.unsure": "불확실", "oc.none": "모름", "oc.norec": "기록 안 됨",
        "oc.abort": "중단", "oc.other": "그 밖",
        # 표
        "tbl.title": "에피소드 표", "tbl.all": "전체", "tbl.search": "id 찾기", "tbl.shown": "{n}판 중 {m}판",
        "tbl.ds": "데이터셋", "tbl.outcome": "결과", "tbl.flag": "깃발", "tbl.none": "없음",
        "col.thumb": "그림", "col.id": "id", "col.ds": "데이터셋", "col.t": "시각", "col.outcome": "결과",
        "col.start": "집는 곳 (x, y)", "col.goal": "놓는 곳 (x, y)", "col.move": "옮긴 mm", "col.cells": "칸",
        "col.flags": "깃발",
        "tbl.hint": "줄을 누르면 지도에서 강조", "tbl.unusable": "집은·놓은 자리가 없는 {n}판은 표에서 뺐다",
        # 말풍선
        "tip.move": "옮긴 거리", "tip.cells": "칸", "tip.t": "시각", "tip.outcome": "결과",
        # 접기
        "fold": "접기/펴기",
        "frame.x": "x [mm]", "frame.y": "y [mm]",
        "feat.start": "집는 곳", "feat.goal": "놓는 곳",
        "footer": "layoutkit {version} · 외부 요청 없는 한 장 HTML",
    },
    "en": {
        "lang": "en",
        "status.good": "Good", "status.warn": "Watch", "status.bad": "Bad", "status.info": "Info",
        "made": "Created", "episodes_unit": "ep", "cells_unit": "cells", "weight": "weight", "print": "Print",
        "datasets": "Datasets", "toggle_hint": "click to show/hide",
        "target": "target", "chance": "chance", "todo": "Do", "why": "Why",
        "card.coupling": "Pick ↔ place link", "card.predict": "Place-side guess",
        "card.near": "Short transfers", "card.coverage": "Cells filled", "card.strata": "Slot balance",
        "card.dups": "Repeated spots", "card.n_min": "Episodes still needed",
        "unit.pp": "pp off", "unit.pairs": "pairs", "unit.eps": "ep",
        "next.title": "What to collect next", "next.none": "No recommendation — run recommend as well to see the next layouts here",
        "next.cmd": "layoutkit recommend DATA --spec spec.json",
        "next.feasible": "picked from {n_feasible} feasible layouts out of {n_cand} candidates",
        "next.skipped": "checks not run: {checks}", "next.holdout": "{n} layouts held out for testing (grey × on the map)",
        "next.on_map": "dashed on the map", "next.notes": "Notes",
        "rec.put": "Put {item} {pos}{empty} ({xy})", "rec.empty": " in an empty cell",
        "rec.goal_same": "{goal_top} in slot {slot} of the same {fixture}", "rec.goal_other": "{goal_top} in slot {slot} of the other {fixture} ({pos})",
        "rec.goal_point": "{goal_top} {pos} ({xy})", "rec.move": "{mm} mm move",
        "pos.left": "left", "pos.right": "right", "pos.center": "center", "pos.top": "top", "pos.bottom": "bottom",
        "pos.map": "{p} of the map",
        "map.title": "Top view — where things were picked and placed",
        "map.sub": "● pick → ○ place · colour = dataset · grey box = target area · dashed = recommended",
        "map.arrows": "Arrows", "map.dots": "Dots only", "map.start": "pick", "map.goal": "place",
        "map.rec": "recommended", "map.area": "target area", "map.cells": "cells (h {h:g} mm)", "map.fixture": "fixture",
        "map.holdout": "held-out (avoided)", "map.holdout_tip": "held-out test layout {id} — training recommendations avoid it", "map.left_is": "← +x (robot's left)", "map.selected": "Selected", "map.clear": "Clear",
        "map.back": "Back to table ↓",
        "cells.title": "Cell maps — where are the gaps",
        "cells.start": "Pick: {filled} of {reach} feasible cells filled · {empty} empty",
        "cells.goal": "Place: {filled} of {reach} feasible cells filled · {empty} empty",
        "cells.start_all": "Pick: {filled} of {n} cells filled", "cells.goal_all": "Place: {filled} of {n} cells filled",
        "cells.empty": "empty (feasible)", "cells.noreach": "not feasible", "cells.count": "episodes",
        "cells.tip": "cell {k}", "cells.reach_yes": "feasible", "cells.reach_no": "not feasible",
        "cells.rec": "recommended {labels}",
        "sc.title": "Shortcut — can the pick spot alone tell where it goes",
        "sc.bad": "Shortcut risk: the pick spot alone tells the place side {acc} of the time (chance {chance})",
        "sc.warn": "Some shortcut: the pick spot tells the place side {acc} of the time — above chance ({chance})",
        "sc.good": "No shortcut: guessing the place side from the pick spot is close to chance ({chance}) — {acc}",
        "sc.scatter": "{a} ↔ {b}", "sc.merged": "pooled", "sc.table": "Side table — split at {axis} = {split} mm",
        "sc.row": "pick {side}", "sc.col": "place {side}", "sc.rowline": "{a} → {b} {k}/{n}",
        "sc.gauge": "place side guessed from pick ({k} nearest)", "sc.gauge_side": "place side guessed from pick side (side table)", "sc.skew": "lopsided",
        "sc.left": "left", "sc.right": "right", "sc.split": "split",
        "tr.title": "Transfer distance — are there short moves",
        "tr.x": "transfer distance [mm] (pick → place)", "tr.y": "cumulative share",
        "tr.near": "near ≤{mm} mm", "tr.target": "target: pass above this point ({share}+)",
        "tr.legend": "{name} · near {near} · median {med} mm",
        "st.title": "Slots — evenly used?",
        "st.sub": "largest gap {dev} (target ≤ {good})", "st.even": "even", "st.more": "more", "st.less": "fewer",
        "st.share": "share",
        "cmp.title": "Dataset comparison — same metrics side by side", "cmp.low": "lower is better", "cmp.high": "higher is better", "cmp.zero": "closer to 0 is better",
        "tl.title": "Timeline — when episodes were collected and how they ended",
        "tl.sub": "episodes in time order (x = order, vertical lines = new day)",
        "runs.title": "Collection runs — outcome per day (kept/total)", "runs.reasons": "why {n} runs were not successes (a run can have several)",
        "runs.sub": "{kept} kept out of {n} automatic runs · median run {med} s",
        "runs.y": "runs",
        "oc.success": "success", "oc.fail": "fail", "oc.unsure": "unsure", "oc.none": "unknown", "oc.norec": "not recorded",
        "oc.abort": "aborted", "oc.other": "other",
        "tbl.title": "Episodes", "tbl.all": "all", "tbl.search": "find id", "tbl.shown": "{m} of {n} shown",
        "tbl.ds": "dataset", "tbl.outcome": "outcome", "tbl.flag": "flag", "tbl.none": "none",
        "col.thumb": "img", "col.id": "id", "col.ds": "dataset", "col.t": "time", "col.outcome": "outcome",
        "col.start": "pick (x, y)", "col.goal": "place (x, y)", "col.move": "move mm", "col.cells": "cells",
        "col.flags": "flags",
        "tbl.hint": "click a row to highlight it on the map", "tbl.unusable": "{n} episodes without pick/place positions are not listed",
        "tip.move": "moved", "tip.cells": "cells", "tip.t": "time", "tip.outcome": "outcome",
        "fold": "collapse/expand",
        "frame.x": "x [mm]", "frame.y": "y [mm]",
        "feat.start": "pick", "feat.goal": "place",
        "footer": "layoutkit {version} · single HTML file, no external requests",
    },
}

# 신호등 카드: code → (왜, 할 일). 채울 값: value(형식된 값), target, 그리고 args 의 키(형식된 것).
CARD = {
    "ko": {
        "coupling_high": ("{a}와 {b}가 함께 움직인다 (ρ {rho})", "둘을 따로 고른 배치를 더 모은다 — 아래 추천"),
        "coupling_warn": ("{a}와 {b} 사이에 끌림이 남아 있다 (ρ {rho})", "추천 배치로 몇 판 더 모아 {target} 로"),
        "coupling_ok": ("{a}와 {b}가 거의 따로 움직인다 (ρ {rho})", "지금처럼 모은다"),
        "predict_high": ("집는 곳만 보고도 놓는 쪽을 {acc} 맞힌다 (우연 {chance})", "같은 집는 곳에서 놓는 쪽을 바꿔 가며 모은다"),
        "predict_warn": ("집는 곳으로 놓는 쪽을 {acc} 맞힌다 — 우연보다 높다", "반대 쪽에 놓는 판을 조금 더"),
        "predict_ok": ("집는 곳으로는 놓는 쪽을 잘 못 맞힌다 ({acc})", "지금처럼 모은다"),
        "near_low": ("{near_mm} mm 안으로 옮긴 판이 {share} 뿐 (목표 {target})", "짧게(≤{near_mm} mm) 옮기는 판을 넣는다"),
        "near_ok": ("{near_mm} mm 안으로 옮긴 판이 {share} — 충분하다", "지금처럼 모은다"),
        "coverage_low": ("놓을 수 있는 칸 중 집는 곳 {filled_start}/{reach_start}, 놓는 곳 {filled_goal}/{reach_goal}칸만 찼다",
                         "빈 칸(칸 지도의 주황 테)부터 채운다"),
        "coverage_ok": ("칸을 거의 다 채웠다 (집는 곳 {filled_start}/{reach_start}, 놓는 곳 {filled_goal}/{reach_goal})",
                        "남은 빈 칸만 마저 채운다"),
        "strata_skew": ("{name} {value}번이 {share} — 고르면 {target_share}", "{value}번이 {dir} 나오게 배치를 고른다"),
        "strata_ok": ("칸 번호가 고르게 나온다 (가장 큰 차이 {value})", "지금처럼 모은다"),
        "dups_info": ("집는 곳·놓는 곳이 둘 다 {dup_mm} mm 안인 같은 자리 {n}쌍", "같은 자리 반복은 새 정보가 적다 — 새 자리로"),
        "n_min_info": ("빈 칸을 다 채우려면 적어도 {n_min}판 더 (무작위면 약 {coupon}판)", "추천 배치를 따라 모은다"),
        "n_min_rec": ("놓을 수 있는 빈 (자리, 방향) 칸을 다 채우려면 적어도 {n_min}판 더", "추천 배치를 따라 모은다"),
        "_bad": ("{title}: {value} (목표 {target})", "아래 추천 배치로 보충한다"),
        "_warn": ("{title}: {value} (목표 {target})", "조금 더 모아 본다"),
        "_good": ("{title}: {value} (목표 {target})", "지금처럼 모은다"),
        "_info": ("{title}: {value}", "참고만"),
        "dir.less": "덜", "dir.more": "더",
    },
    "en": {
        "coupling_high": ("{a} and {b} move together (ρ {rho})", "collect layouts that pick them independently — see below"),
        "coupling_warn": ("some pull left between {a} and {b} (ρ {rho})", "a few more recommended layouts to reach {target}"),
        "coupling_ok": ("{a} and {b} are nearly independent (ρ {rho})", "keep collecting as is"),
        "predict_high": ("the pick spot alone tells the place side {acc} of the time (chance {chance})",
                         "from the same pick spot, alternate the place side"),
        "predict_warn": ("the pick spot tells the place side {acc} of the time — above chance", "a few more opposite-side placements"),
        "predict_ok": ("the pick spot barely tells the place side ({acc})", "keep collecting as is"),
        "near_low": ("only {share} moved within {near_mm} mm (target {target})", "add short moves (≤{near_mm} mm)"),
        "near_ok": ("{share} moved within {near_mm} mm — enough", "keep collecting as is"),
        "coverage_low": ("only pick {filled_start}/{reach_start} and place {filled_goal}/{reach_goal} feasible cells filled",
                         "fill the empty cells first (orange outline in the cell maps)"),
        "coverage_ok": ("cells nearly all filled (pick {filled_start}/{reach_start}, place {filled_goal}/{reach_goal})",
                        "fill the few remaining cells"),
        "strata_skew": ("{name} {value} is {share} — even would be {target_share}", "choose layouts with {dir} {name} {value}"),
        "strata_ok": ("slots are evenly used (largest gap {value})", "keep collecting as is"),
        "dups_info": ("repeated spot pairs: {n} (pick and place both within {dup_mm} mm)",
                      "repeats add little — use new spots"),
        "n_min_info": ("at least {n_min} more episodes to fill every empty cell (about {coupon} at random)",
                       "follow the recommended layouts"),
        "n_min_rec": ("at least {n_min} more episodes to fill every empty feasible (spot, orientation) cell",
                      "follow the recommended layouts"),
        "_bad": ("{title}: {value} (target {target})", "top up with the recommended layouts below"),
        "_warn": ("{title}: {value} (target {target})", "collect a little more"),
        "_good": ("{title}: {value} (target {target})", "keep collecting as is"),
        "_info": ("{title}: {value}", "for reference"),
        "dir.less": "fewer", "dir.more": "more",
    },
}

# 추천 이유 코드
WHY = {
    "ko": {"empty_start_cell": "빈 집는 칸을 채움", "empty_goal_cell": "빈 놓는 칸을 채움", "adds_near": "가까이 옮기기 부족을 채움",
           "lowers_coupling": "좌우 상관을 낮춤", "balances_strata": "칸 번호를 고르게", "new_yaw": "새 방향",
           "far_from_data": "모은 데이터에서 먼 곳", "relaxed": "조건을 조금 풀어서 고름", "novel_start": "새 집는 자리",
           "novel_goal": "새 놓는 자리", "low_effort": "지금 장면에서 덜 옮김", "retry_deleted": "지운 판 다시"},
    "en": {"empty_start_cell": "fills an empty pick cell", "empty_goal_cell": "fills an empty place cell",
           "adds_near": "adds a short move", "lowers_coupling": "lowers the left–right correlation",
           "balances_strata": "balances the slots", "new_yaw": "new orientation", "far_from_data": "far from collected data",
           "relaxed": "picked with relaxed checks", "novel_start": "new pick spot", "novel_goal": "new place spot",
           "low_effort": "little rearranging", "retry_deleted": "redo a deleted episode"},
}

# 수집 실행 실패·불확실 이유 코드
REASON = {
    "ko": {"fixture_moved": "받침이 허용보다 움직였다", "fixture_lifted": "뺄 때 받침이 같이 들렸다",
           "object_not_seen": "놓은 뒤 물체가 안 보인다", "goal_state_unknown": "놓을 칸 상태를 못 정했다",
           "not_recorded": "기록이 시작되지 않았다(점검 목록)", "aborted": "팔이 계획대로 안 움직여 중단", "other": "그 밖의 이유"},
    "en": {"fixture_moved": "rack moved beyond tolerance", "fixture_lifted": "rack lifted while pulling out",
           "object_not_seen": "object not seen after placing", "goal_state_unknown": "target slot state not determined",
           "not_recorded": "recording not started (checklist)", "aborted": "arm did not follow the plan", "other": "other"},
}

FLAG = {
    "ko": {"dup": "같은 자리", "near_holdout": "시험 배치 근처", "out_of_area": "영역 밖", "near": "가까이", "no_goal": "놓은 곳 없음",
           "excluded": "결과로 뺌"},
    "en": {"dup": "repeat", "near_holdout": "near held-out", "out_of_area": "outside area", "near": "near", "no_goal": "no place",
           "excluded": "excluded"},
}

METRIC = {
    "ko": {"n": "에피소드 수", "rho": "|ρ| {pair}", "predict": "놓는 쪽 맞힘(집는 곳으로)", "near_share": "가까이 옮긴 비율",
           "move_median": "옮긴 거리 중앙 (mm)", "spots_start": "서로 다른 집는 곳", "spots_goal": "서로 다른 놓는 곳",
           "spots_pairs": "서로 다른 (집는, 놓는) 짝", "filled_start": "채운 칸 — 집는 곳", "filled_goal": "채운 칸 — 놓는 곳",
           "same_fixture": "같은 고정물 안에서 옮긴 비율", "coverage": "칸 채움 비율", "strata_dev": "칸 번호 가장 큰 차이",
           "n_success": "성공 판", "rho_pair": "ρ {pair}", "side_acc": "놓는 쪽 맞힘(쪽 표)", "same_fixture_n": "같은 고정물 안에서 옮긴 판"},
    "en": {"n": "episodes", "rho": "|ρ| {pair}", "predict": "place side guessed from pick", "near_share": "share of short moves",
           "move_median": "median move (mm)", "spots_start": "distinct pick spots", "spots_goal": "distinct place spots",
           "spots_pairs": "distinct (pick, place) pairs", "filled_start": "cells filled — pick", "filled_goal": "cells filled — place",
           "same_fixture": "moved within the same fixture", "coverage": "cells filled share", "strata_dev": "largest slot gap",
           "n_success": "successes", "rho_pair": "ρ {pair}", "side_acc": "place side guessed (side table)",
           "same_fixture_n": "episodes within the same fixture"},
}

# 물체·고정물 이름(spec.layout 의 name) — 없으면 이름 그대로
NAMES = {
    "ko": {"red": "빨강", "yellow": "노랑", "blue": "파랑", "green": "초록", "black": "검정", "white": "하양", "ring": "링",
           "rack": "받침", "tube": "튜브", "cup": "컵", "box": "상자", "start_slot": "집는 칸 번호", "goal_slot": "놓는 칸 번호",
           "object": "물체", "target": "놓을 곳", "place": "놓을 자리", "bin": "버림 통", "color": "색"},
    "en": {"red": "red", "yellow": "yellow", "blue": "blue", "green": "green", "black": "black", "white": "white", "ring": "ring",
           "rack": "rack", "tube": "tube", "cup": "cup", "box": "box", "start_slot": "pick slot", "goal_slot": "place slot",
           "object": "object", "target": "target", "place": "place spot", "bin": "discard bin", "color": "color"},
}


def t(lang: str, key: str, **kw) -> str:
    """고정 글 하나. 없으면 ko → key 순서로 대신."""
    s = T.get(lang, {}).get(key) or T["ko"].get(key) or key
    if kw:
        try:
            return s.format_map(_Safe(kw))
        except (IndexError, ValueError):
            return s
    return s


class _Safe(dict):
    """빠진 자리 채움 값은 '?' — 화면이 깨지지 않게."""

    def __missing__(self, k):
        return "?"


def name(lang: str, n) -> str:
    if n is None:
        return ""
    return NAMES.get(lang, {}).get(str(n), str(n))


def feature(lang: str, f: str) -> str:
    """'start.x' → '집는 곳 x'."""
    if not f:
        return ""
    head, _, tail = str(f).partition(".")
    if head in ("start", "goal"):
        return f"{t(lang, 'feat.' + head)} {tail}".strip()
    return str(f)


def ko_obj(word: str, kind: str = "eul") -> str:
    """한국어 조사 고르기: 받침 있으면 '을/은/과', 없으면 '를/는/와'. 영어 단어면 그대로 '을'."""
    if not word:
        return word
    ch = word[-1]
    code = ord(ch) - 0xAC00
    if 0 <= code < 11172:
        has = code % 28 != 0
    else:
        has = False
    pair = {"eul": ("을", "를"), "eun": ("은", "는"), "gwa": ("과", "와")}[kind]
    return word + (pair[0] if has else pair[1])
