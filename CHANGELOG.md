# 변경 기록

최신이 위다. 날짜는 그 버전을 만든 날이다.

## v0.1.0 — 2026-11-04

첫 공개본. FR5-AutoCollect 의 받침 과제 배치 추천기(`fr5auto/rackrec.py`)를 과제와 데이터 형식에 묶이지 않게 떼어 낸 것이다.

- 어댑터: fr5rec 폴더 · 받침 꼬리표 JSON · 특징 묶음, LeRobot v2.x parquet(pyarrow), CSV · JSON · JSONL 표(열 이름 짐작 · `map`), layoutkit 에피소드 JSON, fr5auto 실행 기록. 형식 자동 판별.
- 궤적 사건 찾기(`events.detect`): 그리퍼 문턱·닫힘 방향 자동 짐작, 히스테리시스, 깜빡임 지우기, 멈춘 프레임 중앙값으로 자리, 다시 잡기 구간 고르기.
- 분석: 가중 상관, 쪽 표, 최근접 이웃 맞힘, 옮긴 거리·가까이 비율, 육각 칸·방향 칸 채움, N_min · 쿠폰 수집, 채움 거리, 12 mm 자리 묶음 · 같은 자리 짝, 이산 칸 치우침, 데이터셋 비교, 실행 기록 요약, 신호등 카드 7개.
- 추천: spec 선언 배치(`points` · `fixtures`), Halton 후보, 검사(area · reach · gap · keepout · yaw_window · in_view · view_angle · goal_visible · python 훅), 가우스 과정 사후 분산 점수, 고르기 · 선택지 A/B/C, 시험 배치(k-center), 큐. 받침 spec 에서 fr5auto 와 같은 후보 · 같은 통과 121개.
- 화면: 외부 요청 없는 HTML 한 장(카드 · 다음에 할 일 · 지도 · 칸 지도 · 지름길 · 옮긴 거리 · 칸 번호 · 비교 · 시간표 · 수집 기록 · 표), ko/en, 인쇄, PNG 내보내기(matplotlib).
- 명령: `analyze` · `recommend` · `compare` · `watch` · `report` · `init-spec` · `demo` · `pipeline`.
- 예제: FR5 받침 과제(실물 v1 100판 · v2 19판 · 실행 기록 200회 · 3인칭 보정), 캡스톤 색 분류(가짜 데이터 · python 훅), LeRobot 가짜 데이터 생성.
- 시험 5개 파일(받침 숫자 재현 · 어댑터 · 추천 · 명령 · 화면).
