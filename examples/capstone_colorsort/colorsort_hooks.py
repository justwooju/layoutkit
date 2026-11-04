"""캡스톤 예제의 python 훅 — spec.constraints 의 {"type": "hook", "fn": "colorsort_hooks:path_clear"}.

훅은 후보 묶음 C(layoutkit.recommend.sample 모양)와 ctx(spec·layout·카메라)를 받아 후보마다 통과 여부(불리언 배열)를 돌려준다.
spec 파일 옆 폴더에서 먼저 찾는다.
"""
import numpy as np

from layoutkit.recommend.constraints import rect_point_dist


def path_clear(C, ctx, clear_mm=20.0, n_pts=12):
    """출발 칸 → 목표 칸 직선(위에서 본) 위 점들이, 출발·목표가 아닌 고정물 사각형에서 clear_mm 이상 떨어져 있나."""
    lay = ctx.lay
    t = np.linspace(0.0, 1.0, n_pts)[None, :]
    gx, gy = C["g"][:, 0:1], C["g"][:, 1:2]
    qx, qy = C["q"][:, 0:1], C["q"][:, 1:2]
    px, py = gx + t * (qx - gx), gy + t * (qy - gy)              # N × n_pts
    ok = np.ones(C["n"], bool)
    for i, I in enumerate(lay.instances):
        other = (C["a"] != i) & (C["b"] != i)
        d = rect_point_dist(C["P"][:, i, 0:1], C["P"][:, i, 1:2], C["yaw"][:, i:i + 1], I.type.L, I.type.W, px, py).min(axis=1)
        ok &= ~other | (d >= float(clear_mm))
    return ok
