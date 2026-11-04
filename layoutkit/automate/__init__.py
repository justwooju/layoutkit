"""자동화 — watch(폴더 감시 → 다시 만들기) · pipeline(build 한 번 · 설정 파일 실행 · CSV 내보내기)."""
from .pipeline import build, export_cards_csv, export_episodes_csv, run_config  # noqa: F401
from .watch import fingerprint, watch  # noqa: F401
