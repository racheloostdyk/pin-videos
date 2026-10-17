#!/usr/bin/env python3
"""Turn a finished 1:2 pin image into a 6-second video pin (1080x2160, H.264, ~1 MB).

Motion: one text line pulses every 2 s, sparkles twinkle around the title, slow
zoom over the whole pin. Optional ingredient tags (single-recipe pins only) pop in
one at a time and float. The food is never animated.

Usage:
  python3 make_video_pin.py PIN.png OUT.mp4 CONFIG.json

CONFIG.json (all coordinates are on the pin scaled to 1000x2000):
{
  "pulse_box": [x0, y0, x1, y1],    # the text line that pulses; leave ~20 px margin
  "pulse_shape": "band" | "circle", # "circle" for round number badges
  "sparkles": [[x, y, phase, size], ...],  # 5-8 points around the title block
  "ingredients": ["2 lbs chicken breast", ...],  # [] for none (roundups, every other recipe)
  "tag_area": [y_top, y_bottom],    # vertical band for tags (over the food photo)
  "tag_x": 500                      # horizontal centre of the tag column
}
"""
import json, math, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont

src, out, cfg_path = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = json.load(open(cfg_path))
W, H, FPS, SECS = 1000, 2000, 30, 6
OUT_W, OUT_H = 1080, 2160
N = FPS * SECS

base = Image.open(src).convert("RGB").resize((W, H), Image.LANCZOS)
ease = lambda t: 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, t)))

# pulsing line
bx0, by0, bx1, by1 = cfg["pulse_box"]
BAND = base.crop((bx0, by0, bx1, by1)).convert("RGBA")
BMASK = Image.new("L", BAND.size, 0)
if cfg.get("pulse_shape") == "circle":
    ImageDraw.Draw(BMASK).ellipse((10, 10, BAND.width - 10, BAND.height - 10), fill=255)
else:
    ImageDraw.Draw(BMASK).rounded_rectangle((14, 10, BAND.width - 14, BAND.height - 10), radius=40, fill=255)
BMASK = BMASK.filter(ImageFilter.GaussianBlur(8))

# ingredient tags
FONT_PATHS = ["/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
              "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
font_path = next((p for p in FONT_PATHS if os.path.exists(p)), None)
font = ImageFont.truetype(font_path, cfg.get("tag_size", 30)) if font_path else ImageFont.load_default()

def make_tag(text):
    l, t, r, b = font.getbbox(text)
    pw, ph = 22, 10
    im = Image.new("RGBA", (r - l + 2 * pw, b - t + 2 * ph), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, im.width - 1, im.height - 1), radius=im.height // 2, fill=(17, 17, 17, 235))
    d.text((pw - l, ph - t), text, font=font, fill=(255, 255, 255, 255))
    return im

tags = [make_tag(x) for x in cfg.get("ingredients", [])]
ty0, ty1 = cfg.get("tag_area", [1200, 1800])
gap = (ty1 - ty0) / max(1, len(tags) - 1)
cx = cfg.get("tag_x", W / 2)

def tag_layer(t):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for i, tg in enumerate(tags):
        p = (t - (0.35 + i * 0.18)) / 0.35
        if p <= 0:
            continue
        k = min(1.0, p)
        pop = 1 + 0.25 * math.sin(math.pi * k) if k < 1 else 1.0
        a = int(255 * min(1.0, k * 1.5))
        dx = math.sin(t * 0.9 + i * 1.3) * 6
        dy = math.sin(t * 0.7 + i * 0.8) * 5
        im = tg.resize((max(1, round(tg.width * pop)), max(1, round(tg.height * pop))), Image.LANCZOS)
        if a < 255:
            im.putalpha(im.getchannel("A").point(lambda v: v * a // 255))
        y = ty0 + i * gap
        layer.alpha_composite(im, (round(cx - im.width / 2 + dx), round(y - im.height / 2 + dy)))
    return layer

def sparkles(t):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for (x, y, phs, r) in cfg.get("sparkles", []):
        k = max(0.0, math.sin(math.pi * ((t / 1.6 + phs) % 1.0))) ** 2
        if k > 0.02:
            rr, a = r * 1.6 * (0.4 + 0.8 * k), int(255 * k)
            for (rx, ry) in ((rr, rr * 0.22), (rr * 0.22, rr)):
                d.polygon([(x - rx, y), (x, y - ry), (x + rx, y), (x, y + ry)], fill=(255, 214, 120, a))
            d.ellipse((x - rr * .18, y - rr * .18, x + rr * .18, y + rr * .18), fill=(255, 255, 255, a))
    return layer

ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                       "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                       "-vf", f"scale={OUT_W}:{OUT_H}:flags=lanczos,format=yuv420p",
                       "-c:v", "libx264", "-preset", "slow", "-b:v", "1700k", "-maxrate", "2100k",
                       "-bufsize", "3400k", "-r", str(FPS), "-movflags", "+faststart", out],
                      stdin=subprocess.PIPE)
for i in range(N):
    t = i / FPS
    fr = base.convert("RGBA")
    p = (t % 2.0) / 0.55
    k = math.sin(math.pi * p) if p < 1 else 0.0
    if k > 0:
        sc = 1 + 0.15 * k
        nb = BAND.resize((round(BAND.width * sc), round(BAND.height * sc)), Image.LANCZOS)
        fr.paste(nb, (round(bx0 + BAND.width / 2 - nb.width / 2), round(by0 + BAND.height / 2 - nb.height / 2)),
                 BMASK.resize(nb.size, Image.LANCZOS))
    if tags:
        fr.alpha_composite(tag_layer(t))
    fr.alpha_composite(sparkles(t))
    z = 1 + 0.05 * ease(i / (N - 1))
    cw, ch = W / z, H / z
    l, tp = (W - cw) / 2, (H - ch) * 0.45
    ff.stdin.write(fr.convert("RGB").resize((W, H), Image.BICUBIC, box=(l, tp, l + cw, tp + ch)).tobytes())
ff.stdin.close()
sys.exit(ff.wait())
