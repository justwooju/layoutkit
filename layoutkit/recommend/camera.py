"""카메라 투영 — 핀홀 + 브라운 왜곡. 보임 검사(in_view·goal_visible)와 화면 칸(정책 입력 칸)에 쓴다.

spec.cameras 항목 하나:

    {"name": "third", "width": 848, "height": 480,
     "K": [[fx, s, cx], [0, fy, cy], [0, 0, 1]],
     "dist": [k1, k2, p1, p2, k3] | null,     # librealsense 계수 순서
     "dist_flip": false,                      # true 면 다항식 방향을 바꾼다(아래)
     "T_cam_base": 4×4                        # 카메라←베이스: X_cam = T · X_base (또는 "T_base_cam" = 카메라 자세)
    }

왜곡: librealsense(rs2_project_point_to_pixel) 관례 — f = 1 + k1·r² + k2·r⁴ + k3·r⁶ 로 x·f, 그 뒤 접선항(크기 바뀐 x 로).
  dist_flip = false: 투영이 그 다항식(이상 → 왜곡 좌표), 역투영이 다항식의 반복 역.
  dist_flip = true : 방향을 바꾼다 — 투영이 다항식의 반복 역(뉴턴), 역투영이 다항식.
  fr5auto camera.Cam(intr, flip) 과 같은 뜻·같은 식(실물 3인칭은 보정 잔차로 flip=true 가 골라졌다).
좌표: 카메라 프레임 x 오른쪽 · y 아래 · z 앞, 길이 mm. z ≤ 1 mm 인 점은 NaN.
"""
from __future__ import annotations

import numpy as np


class Camera:
    """spec 카메라 dict → 투영기. fr5auto camera.Cam 과 같은 다항식·같은 반복(0.01 px 안으로 같아야 한다 — tests)."""

    def __init__(self, d: dict):
        self.name = str(d.get("name") or "cam")
        self.w, self.h = int(d["width"]), int(d["height"])
        K = np.asarray(d["K"], float)
        self.fx, self.fy, self.cx, self.cy, self.skew = float(K[0, 0]), float(K[1, 1]), float(K[0, 2]), float(K[1, 2]), float(K[0, 1])
        k = list(d.get("dist") or [0.0] * 5) + [0.0] * 5
        self.k = np.array(k[:5], float)
        self.flip = bool(d.get("dist_flip", False))
        if d.get("T_cam_base") is not None:
            T = np.asarray(d["T_cam_base"], float)
        elif d.get("T_base_cam") is not None:
            Tb = np.asarray(d["T_base_cam"], float)
            R, t = Tb[:3, :3], Tb[:3, 3]
            T = np.eye(4)
            T[:3, :3], T[:3, 3] = R.T, -R.T @ t
        else:
            raise ValueError(f"카메라 {self.name}: T_cam_base 또는 T_base_cam 이 없다")
        self.T_cb = T
        self.R, self.t = T[:3, :3], T[:3, 3]
        self.center = -self.R.T @ self.t                         # 카메라 중심(베이스 좌표)
        self.policy_px = d.get("policy_px", 256)                 # 정책 입력 크기(가로·세로 같은 정사각 — fr5rec 미리보기와 같게 돌림 없이 줄임)
        self.img_grid = int(d.get("img_grid", 8))
        self.policy_weight = float(d.get("policy_weight", 0.0))  # 점수의 정책 입력 칸 항 무게(rackrec weights.img3 / imgw)

    # -- rs.cpp 의 다항식과 그 역(fr5auto camera.Cam._poly / _ipoly 와 같은 식)
    def _poly(self, x, y):
        k1, k2, p1, p2, k3 = self.k
        r2 = x * x + y * y
        f = 1 + k1 * r2 + k2 * r2 * r2 + k3 * r2 * r2 * r2
        x, y = x * f, y * f
        return x + 2 * p1 * x * y + p2 * (r2 + 2 * x * x), y + 2 * p2 * x * y + p1 * (r2 + 2 * y * y)

    def _ipoly(self, xd, yd, iters=30):
        """_poly 의 역 — 뉴턴(수치 야코비안 h = 1e-7), 묶음 전체 오차 < 1e-13 이면 멈춤."""
        x, y = np.array(xd, float), np.array(yd, float)
        for _ in range(iters):
            fx_, fy_ = self._poly(x, y)
            ex, ey = fx_ - xd, fy_ - yd
            if max(float(np.abs(ex).max(initial=0)), float(np.abs(ey).max(initial=0))) < 1e-13:
                break
            h = 1e-7
            ax, ay = self._poly(x + h, y)
            bx, by = self._poly(x, y + h)
            j11, j21 = (ax - fx_) / h, (ay - fy_) / h
            j12, j22 = (bx - fx_) / h, (by - fy_) / h
            det = j11 * j22 - j12 * j21
            x = x - (j22 * ex - j12 * ey) / det
            y = y - (-j21 * ex + j11 * ey) / det
        return x, y

    def distort(self, xn):
        xn = np.asarray(xn, float).reshape(-1, 2)
        if not np.any(self.k):
            return xn.copy()
        f = self._ipoly if self.flip else self._poly
        return np.column_stack(f(xn[:, 0], xn[:, 1]))

    def project_cam(self, Pc):
        """카메라 프레임 점(N×3) → 픽셀(N×2). z ≤ 1 mm 은 NaN."""
        Pc = np.asarray(Pc, float).reshape(-1, 3)
        z = Pc[:, 2]
        ok = z > 1.0
        out = np.full((len(Pc), 2), np.nan)
        if ok.any():
            d = self.distort(Pc[ok, :2] / z[ok, None])
            out[ok] = np.column_stack([d[:, 0] * self.fx + d[:, 1] * self.skew + self.cx, d[:, 1] * self.fy + self.cy])
        return out

    def project(self, Pb):
        """베이스 점(…×3) → 픽셀(…×2)."""
        Pb = np.asarray(Pb, float)
        shp = Pb.shape[:-1]
        P = Pb.reshape(-1, 3)
        return self.project_cam(P @ self.R.T + self.t).reshape(shp + (2,))

    def inside(self, uv, margin=0.0):
        """화면 안(가장자리 margin px) — NaN 은 밖."""
        uv = np.asarray(uv, float)
        u, v = uv[..., 0], uv[..., 1]
        with np.errstate(invalid="ignore"):
            return (u >= margin) & (u <= self.w - 1 - margin) & (v >= margin) & (v <= self.h - 1 - margin)

    def policy_cell(self, Pb):
        """베이스 점 → 정책 입력(policy_px²)의 img_grid × img_grid 칸 번호(밖이면 −1) — rackrec.World.img_cell 과 같다."""
        n = self.img_grid
        s = float(self.policy_px)
        uv = self.project(np.asarray(Pb, float).reshape(-1, 3))
        fin = np.isfinite(uv).all(axis=1)
        u = np.nan_to_num(uv[:, 0], nan=-1.0) * s / self.w
        v = np.nan_to_num(uv[:, 1], nan=-1.0) * s / self.h
        ins = fin & (u >= 0) & (u < s) & (v >= 0) & (v < s)
        k = (np.clip(v // (s / n), 0, n - 1) * n + np.clip(u // (s / n), 0, n - 1)).astype(int)
        return np.where(ins, k, -1)


def cameras(spec: dict) -> dict:
    """spec.cameras → {이름: Camera}. 모양이 틀린 카메라는 건너뛰고 이유를 남긴다(반환 두 번째)."""
    out, bad = {}, []
    for d in spec.get("cameras") or []:
        try:
            c = Camera(d)
            out[c.name] = c
        except (KeyError, ValueError, TypeError) as e:
            bad.append(f"camera {d.get('name')}: {type(e).__name__}: {e}")
    return out, bad
