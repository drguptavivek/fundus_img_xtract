"""Generate the synthetic fundus images used by the grader PWA demo mode.

Deterministic, no patient data: a warm retinal background with a bright optic
disc and cup, radiating vessels, and a few small dark lesions so every image
filter, the loupe and the annotation tools have something to act on.

Run inside Compose:
  docker compose exec -u $(id -u):$(id -g) -e UV_CACHE_DIR=/tmp/.uv-cache web \
    uv run python scripts/make_demo_fundus.py
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SIZE = 1400
OUT = Path(__file__).resolve().parents[1] / "static" / "grader-pwa" / "demo"


def _vessel(draw, start, angle, length, width, rng, colour, depth=0):
    x, y = start
    points = [(x, y)]
    for _ in range(int(length / 12)):
        angle += rng.normal(0, 0.09)
        x += 12 * math.cos(angle)
        y += 12 * math.sin(angle)
        points.append((x, y))
    draw.line(points, fill=colour, width=max(1, int(width)), joint="curve")
    if depth < 3 and width > 2:
        for sign in (-1, 1):
            branch_at = points[int(len(points) * rng.uniform(0.35, 0.75))]
            _vessel(draw, branch_at, angle + sign * rng.uniform(0.35, 0.8), length * 0.55, width * 0.6, rng, colour, depth + 1)


def make_fundus(seed: int, disc_x_frac: float, macula_x_frac: float) -> Image.Image:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    cx = cy = SIZE / 2
    r = np.hypot(xx - cx, yy - cy) / (SIZE / 2)
    # Warm background darkening toward the periphery, with mild grain.
    base = np.zeros((SIZE, SIZE, 3), dtype=np.float32)
    shade = np.clip(1.05 - 0.55 * r**1.6, 0, 1)
    base[..., 0] = 190 * shade
    base[..., 1] = 78 * shade
    base[..., 2] = 34 * shade
    base += rng.normal(0, 3.5, base.shape).astype(np.float32)
    # Macula: a darker pigmented patch opposite the disc.
    mx = SIZE * macula_x_frac
    macula = np.exp(-(((xx - mx) ** 2 + (yy - cy) ** 2) / (2 * (SIZE * 0.09) ** 2)))
    base[..., 0] -= 45 * macula
    base[..., 1] -= 22 * macula
    base[..., 2] -= 10 * macula
    image = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")

    draw = ImageDraw.Draw(image)
    dx, dy = SIZE * disc_x_frac, cy - SIZE * 0.02
    disc_r = SIZE * 0.075
    draw.ellipse((dx - disc_r, dy - disc_r * 1.08, dx + disc_r, dy + disc_r * 1.08), fill=(245, 196, 120))
    cup_r = disc_r * 0.42
    draw.ellipse((dx - cup_r, dy - cup_r * 1.05, dx + cup_r, dy + cup_r * 1.05), fill=(252, 232, 178))
    # Vessels leave the disc in arcades above and below.
    vessel_colour = (112, 22, 14)
    toward_macula = math.pi if macula_x_frac < disc_x_frac else 0.0
    for sign in (-1, 1):
        for width, spread in ((11, 0.55), (7, 0.95)):
            angle = toward_macula + sign * spread + rng.normal(0, 0.05)
            _vessel(draw, (dx, dy + sign * disc_r * 0.3), angle, SIZE * 0.42, width, rng, vessel_colour)
        _vessel(draw, (dx, dy), sign * math.pi / 2 + rng.normal(0, 0.1), SIZE * 0.3, 5, rng, vessel_colour, depth=1)
    # A few small dark lesions to find with the loupe and mark with the tools.
    for _ in range(9):
        angle, dist = rng.uniform(0, 2 * math.pi), rng.uniform(0.15, 0.5) * SIZE / 2
        lx, ly = cx + dist * math.cos(angle), cy + dist * math.sin(angle)
        lr = rng.uniform(3, 7)
        draw.ellipse((lx - lr, ly - lr, lx + lr, ly + lr), fill=(96, 18, 12))
    # Two pale hard-exudate clusters near the macula.
    for _ in range(2):
        ex, ey = mx + rng.normal(0, SIZE * 0.05), cy + rng.normal(0, SIZE * 0.05)
        for _ in range(rng.integers(6, 12)):
            px, py = ex + rng.normal(0, 14), ey + rng.normal(0, 14)
            pr = rng.uniform(1.5, 3.5)
            draw.ellipse((px - pr, py - pr, px + pr, py + pr), fill=(250, 228, 170))
    image = image.filter(ImageFilter.GaussianBlur(0.9))
    # Circular field of view on black, like a real camera frame.
    mask = Image.fromarray((np.hypot(xx - cx, yy - cy) <= SIZE / 2 * 0.98).astype(np.uint8) * 255, "L")
    frame = Image.new("RGB", (SIZE, SIZE), (0, 0, 0))
    frame.paste(image, mask=mask)
    return frame


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    # Right eye: the macula lies temporal (to the left of the disc in the image);
    # left eye is the mirror image. One disc-centred and one macula-centred view each.
    views = {
        "od-disc.png": dict(seed=7, disc_x_frac=0.50, macula_x_frac=0.24),
        "od-macula.png": dict(seed=8, disc_x_frac=0.78, macula_x_frac=0.50),
        "os-disc.png": dict(seed=11, disc_x_frac=0.50, macula_x_frac=0.76),
        "os-macula.png": dict(seed=12, disc_x_frac=0.22, macula_x_frac=0.50),
    }
    for stale in ("fundus-od.png", "fundus-os.png", "od-disc.jpg", "od-macula.jpg", "os-disc.jpg", "os-macula.jpg"):
        (OUT / stale).unlink(missing_ok=True)
    for name, params in views.items():
        make_fundus(**params).save(OUT / name, optimize=True)
        print(name, (OUT / name).stat().st_size // 1024, "KB")
