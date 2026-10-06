#!/usr/bin/env python3
"""Vertical (9:16) memorial video for 7.10.2023 in Hebrew, for TikTok / Reels.

Renders frames with Pillow + numpy, synthesizes a soft ambient soundtrack,
and muxes everything with ffmpeg.

Usage: python3 make_video.py --fonts DIR --out DIR
"""
import argparse
import math
import os
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
DURATION = 44.5
SR = 48000

EMOJI_FONT = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

WHITE = (244, 240, 232)
GREY = (170, 166, 160)
GOLD = (232, 196, 120)
YELLOW = (247, 201, 72)
BLUE = (120, 170, 255)

FLAME_X, FLAME_Y = 540, 1190  # base of the flame (top of the wick)


# ---------------------------------------------------------------- helpers

def smooth_noise(t, seed):
    """Cheap smooth pseudo-noise in [-1, 1] from incommensurate sines."""
    r = np.random.default_rng(seed)
    fr = r.uniform(0.7, 3.3, 4)
    ph = r.uniform(0, 2 * math.pi, 4)
    return sum(math.sin(2 * math.pi * f * t + p) for f, p in zip(fr, ph)) / 4


def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def ease_in_out(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def font(path, size, weight):
    f = ImageFont.truetype(path, size)
    try:
        f.set_variation_by_axes([weight])
    except OSError:
        pass
    return f


def render_text(text, fnt, color, glow=0.0):
    """Render one RTL line to a premultiplied float RGBA layer."""
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    bbox = probe.textbbox((0, 0), text, font=fnt, direction="rtl", language="he")
    pad = 40
    w, h = bbox[2] - bbox[0] + 2 * pad, bbox[3] - bbox[1] + 2 * pad
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((pad - bbox[0], pad - bbox[1]), text, font=fnt, fill=255,
                              direction="rtl", language="he")
    a = np.asarray(mask, np.float32) / 255
    rgb = np.empty((h, w, 3), np.float32)
    rgb[:] = np.array(color, np.float32) / 255
    rgb *= a[..., None]
    if glow > 0:
        g = np.asarray(mask.filter(ImageFilter.GaussianBlur(18)), np.float32) / 255 * glow
        rgb += g[..., None] * np.array([1.0, 0.62, 0.3], np.float32)
        a = np.maximum(a, g)
    return rgb, a


def render_emoji(ch, size):
    f = ImageFont.truetype(EMOJI_FONT, 109)
    im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((10, 10), ch, font=f, embedded_color=True)
    im = im.crop(im.getbbox())
    s = size / max(im.size)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    arr = np.asarray(im, np.float32) / 255
    a = arr[..., 3]
    return arr[..., :3] * a[..., None], a


def hstack_layers(layers, gap):
    """Place layers side by side (visual order left -> right), centered vertically."""
    h = max(l[0].shape[0] for l in layers)
    w = sum(l[0].shape[1] for l in layers) + gap * (len(layers) - 1)
    rgb = np.zeros((h, w, 3), np.float32)
    a = np.zeros((h, w), np.float32)
    x = 0
    for lr, la in layers:
        y = (h - lr.shape[0]) // 2
        rgb[y:y + lr.shape[0], x:x + lr.shape[1]] += lr
        a[y:y + lr.shape[0], x:x + lr.shape[1]] = np.maximum(a[y:y + lr.shape[0], x:x + lr.shape[1]], la)
        x += lr.shape[1] + gap
    return rgb, a


def blend(frame, layer, cx, cy, opacity):
    """Composite a premultiplied layer centered at (cx, cy)."""
    rgb, a = layer
    h, w = a.shape
    x0, y0 = int(round(cx - w / 2)), int(round(cy - h / 2))
    fx0, fy0, fx1, fy1 = max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H)
    if fx0 >= fx1 or fy0 >= fy1:
        return
    lx0, ly0 = fx0 - x0, fy0 - y0
    sub_a = a[ly0:ly0 + fy1 - fy0, lx0:lx0 + fx1 - fx0, None] * opacity
    sub_rgb = rgb[ly0:ly0 + fy1 - fy0, lx0:lx0 + fx1 - fx0] * opacity
    region = frame[fy0:fy1, fx0:fx1]
    region *= 1 - sub_a
    region += sub_rgb


# ---------------------------------------------------------------- scenes

def build_scenes(fonts_dir):
    heebo = os.path.join(fonts_dir, "Heebo[wght].ttf")
    frank = os.path.join(fonts_dir, "FrankRuhlLibre[wght].ttf")

    def T(text, size, color=WHITE, face="frank", weight=500, glow=0.0):
        return render_text(text, font(frank if face == "frank" else heebo, size, weight), color, glow)

    ribbon = render_emoji("🎗️", 96)
    flag = render_emoji("🇮🇱", 150)

    # each scene: (start, end, [(layer, y_center, delay), ...])
    return [
        (0.4, 5.0, [
            (T("7.10.2023", 190, face="heebo", weight=800, glow=0.35), 640, 0.0),
            (T("כ״ב בתשרי תשפ״ד", 64, GREY, face="heebo", weight=300), 800, 0.6),
        ]),
        (5.0, 9.3, [
            (T("שבת בבוקר.", 118, weight=600), 600, 0.0),
            (T("שמחת תורה.", 118, weight=600), 750, 0.5),
        ]),
        (9.3, 14.0, [
            (T("בוקר של חג", 96, GREY, weight=400), 590, 0.0),
            (T("שהפך לשבת השחורה", 112, weight=700, glow=0.25), 740, 0.6),
        ]),
        (14.0, 19.6, [
            (T("כ־1,200", 170, face="heebo", weight=800, glow=0.3), 470, 0.0),
            (T("נרצחו", 76, GREY, weight=400), 600, 0.3),
            (T("251", 170, YELLOW, face="heebo", weight=800), 780, 1.1),
            (hstack_layers([ribbon, T("נחטפו", 76, GREY, weight=400)], -22), 910, 1.4),
        ]),
        (19.6, 24.6, [
            (T("בקיבוצים, במושבים ובערים", 82, weight=500), 560, 0.0),
            (T("במסיבת נובה", 82, weight=500), 680, 0.5),
            (T("בבסיסים ובדרכים", 82, weight=500), 800, 1.0),
        ]),
        (24.6, 29.2, [
            (T("שלוש שנים.", 140, weight=700, glow=0.3), 610, 0.0),
            (T("והלב עדיין שם.", 96, GREY, weight=400), 770, 0.8),
        ]),
        (29.2, 34.2, [
            (T("נזכור את כולם.", 120, weight=700), 590, 0.0),
            (T("כל שם. כל פנים. כל סיפור.", 72, GOLD, face="heebo", weight=300), 750, 0.8),
        ]),
        (34.2, 39.2, [
            (T("לעולם לא נשכח", 138, weight=800, glow=0.4), 600, 0.0),
            (T("יהי זכרם ברוך", 92, GOLD, weight=500), 770, 0.9),
        ]),
        (39.2, DURATION, [
            (flag, 470, 0.0),
            (T("עם ישראל חי", 150, weight=800, glow=0.35), 670, 0.5),
            (T("7.10.2023  ·  שלוש שנים", 54, GREY, face="heebo", weight=300), 810, 1.2),
        ]),
    ]


def scene_opacity(t, start, end, delay, last):
    t_in = t - start - 0.15 - delay
    a_in = ease_out(t_in / 0.9)
    a_out = 1.0 if last else 1 - ease_in_out((t - (end - 0.65)) / 0.6)
    rise = (1 - a_in) * 34 - (0 if last else (1 - a_out) * 18)
    return max(0.0, min(a_in, a_out)), rise


# ---------------------------------------------------------------- candle

def make_candle_body():
    w, h = 150, 260
    x = np.linspace(-1, 1, w)
    shade = 0.55 + 0.45 * np.cos(x * math.pi / 2) ** 0.8
    y = np.linspace(0, 1, h)
    warm = np.exp(-y * 5.0)  # top of the candle is lit by the flame
    base = np.array([238, 228, 210], np.float32) / 255
    lit = np.array([255, 196, 120], np.float32) / 255
    rgb = (base[None, None] * (1 - 0.6 * warm[:, None, None]) + lit[None, None] * 0.6 * warm[:, None, None])
    rgb = rgb * shade[None, :, None] * (0.95 - 0.35 * y)[:, None, None]
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h + 30], radius=18, fill=255)
    ImageDraw.Draw(mask).ellipse([0, -14, w - 1, 22], fill=255)
    a = np.asarray(mask, np.float32) / 255
    return rgb.astype(np.float32) * a[..., None], a


def teardrop(w, h, sway, cx, cy, m=1.6, n=120):
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        px = w * math.sin(t) * abs(math.sin(t / 2)) ** m
        py = -h * math.cos(t)
        k = ((h - py) / (2 * h)) ** 2  # tip sways more than the base
        pts.append((cx + px + sway * k, cy + py))
    return pts


def render_flame(t):
    S = 2
    cw, ch = 220, 340
    img = Image.new("RGB", (cw * S, ch * S), (0, 0, 0))
    d = ImageDraw.Draw(img)
    flick = 1 + 0.08 * smooth_noise(t * 2.2, 1)
    sway = 9 * smooth_noise(t * 1.3, 2)
    cx, base = cw / 2 * S, (ch - 70) * S
    for w, h, col in [(46, 105, (255, 120, 30)), (34, 86, (255, 175, 60)),
                      (22, 62, (255, 228, 150)), (11, 34, (255, 252, 235))]:
        hh = h * flick * S
        d.polygon(teardrop(w * S, hh / 2, sway * S * h / 105, cx, base - hh / 2 + 6 * S), fill=col)
    d.ellipse([cx - 9 * S, base - 6 * S, cx + 9 * S, base + 8 * S], fill=(70, 110, 255))
    img = img.resize((cw, ch), Image.LANCZOS)
    soft = img.filter(ImageFilter.GaussianBlur(10))
    arr = np.asarray(img, np.float32) / 255 * 0.85 + np.asarray(soft, np.float32) / 255 * 0.9
    return arr, (cw, ch)


# ---------------------------------------------------------------- render

def make_renderer(scenes):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    bg = np.empty((H, W, 3), np.float32)
    bg[:] = np.array([7, 8, 13], np.float32) / 255
    bg *= (0.75 + 0.5 * (yy / H))[..., None]
    dist = np.sqrt((xx - FLAME_X) ** 2 + ((yy - FLAME_Y) * 0.85) ** 2)
    glow = np.exp(-(dist / 520) ** 2)[..., None] * np.array([1.0, 0.55, 0.22], np.float32)
    halo = np.exp(-(dist / 120) ** 2)[..., None] * np.array([1.0, 0.75, 0.45], np.float32)
    vignette = (1 - 0.55 * (((xx - W / 2) / W) ** 2 + ((yy - H / 2) / H) ** 2) * 2.2).clip(0.3, 1)[..., None]

    body = make_candle_body()
    rng = np.random.default_rng(7)
    n_emb = 46
    emb = {
        "x0": rng.uniform(380, 700, n_emb), "phase": rng.uniform(0, 1, n_emb),
        "speed": rng.uniform(0.035, 0.08, n_emb), "drift": rng.uniform(-60, 60, n_emb),
        "r": rng.uniform(1.2, 3.2, n_emb), "tw": rng.uniform(0, 6.28, n_emb),
    }

    def render_frame(t):
        candle_in = ease_in_out((t - 0.2) / 2.2)
        inten = candle_in * (0.42 + 0.06 * smooth_noise(t * 3.1, 3) + 0.03 * smooth_noise(t * 9.0, 4))
        frame = bg + glow * inten + halo * inten * 0.35

        # candle body
        blend(frame, body, FLAME_X, FLAME_Y + 26 + 130, candle_in)
        # wick
        frame[FLAME_Y - 4:FLAME_Y + 26, FLAME_X - 2:FLAME_X + 2] *= 1 - 0.85 * candle_in
        # flame (additive)
        fl, (cw, ch) = render_flame(t)
        x0, y0 = FLAME_X - cw // 2, FLAME_Y - (ch - 70)
        frame[y0:y0 + ch, x0:x0 + cw] += fl * candle_in

        # embers rising from the flame
        emb_layer = Image.new("L", (W, H), 0)
        ed = ImageDraw.Draw(emb_layer)
        for i in range(n_emb):
            p = (emb["phase"][i] + t * emb["speed"][i]) % 1.0
            ex = emb["x0"][i] + emb["drift"][i] * p + 14 * math.sin(t * 0.9 + emb["tw"][i])
            ey = FLAME_Y - 60 - p * 1050
            alpha = math.sin(p * math.pi) * (0.55 + 0.45 * math.sin(t * 4 + emb["tw"][i])) * candle_in
            r = emb["r"][i]
            ed.ellipse([ex - r, ey - r, ex + r, ey + r], fill=int(200 * max(alpha, 0)))
        e = np.asarray(emb_layer.filter(ImageFilter.GaussianBlur(1.6)), np.float32) / 255
        frame += e[..., None] * np.array([1.0, 0.6, 0.25], np.float32)

        # text
        for si, (start, end, lines) in enumerate(scenes):
            if not (start - 0.1 <= t <= end):
                continue
            last = si == len(scenes) - 1
            for layer, y, delay in lines:
                op, rise = scene_opacity(t, start, end, delay, last)
                if op > 0.003:
                    blend(frame, layer, W / 2, y + rise, op)

        frame *= vignette
        fade = ease_in_out(t / 0.6) * (1 - ease_in_out((t - (DURATION - 1.4)) / 1.3))
        frame *= fade
        return (np.clip(frame, 0, 1) * 255 + 0.5).astype(np.uint8)

    return render_frame


def render_video(scenes, out_path, audio_path):
    render_frame = make_renderer(scenes)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", audio_path,
           "-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-crf", "17",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", str(SR),
           "-movflags", "+faststart", "-shortest", out_path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n_frames = int(DURATION * FPS)
    for fi in range(n_frames):
        proc.stdin.write(render_frame(fi / FPS).tobytes())
        if fi % 150 == 0:
            print(f"frame {fi}/{n_frames}", flush=True)
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed")


# ---------------------------------------------------------------- audio

def note(name):
    names = {"C": -9, "C#": -8, "D": -7, "Eb": -6, "E": -5, "F": -4, "F#": -3,
             "G": -2, "Ab": -1, "A": 0, "Bb": 1, "B": 2}
    pitch, octave = name[:-1], int(name[-1])
    return 440.0 * 2 ** ((names[pitch] + 12 * (octave - 4)) / 12)


def synth_audio(path):
    n = int((DURATION + 0.5) * SR)
    t = np.arange(n) / SR
    out = np.zeros((2, n), np.float32)

    chords = [("D3", ["D4", "F4", "A4"]), ("Bb2", ["D4", "F4", "Bb4"]),
              ("F2", ["C4", "F4", "A4"]), ("C3", ["C4", "E4", "G4"]),
              ("D3", ["D4", "F4", "A4"]), ("Bb2", ["D4", "F4", "Bb4"]),
              ("G2", ["D4", "G4", "Bb4"]), ("D3", ["D4", "F4", "A4"])]
    seg = DURATION / len(chords)
    for ci, (bass, tones) in enumerate(chords):
        s = ci * seg
        e = s + seg + (3.0 if ci == len(chords) - 1 else 1.6)
        i0, i1 = int(s * SR), min(int(e * SR), n)
        tt = t[i0:i1] - s
        env = np.minimum(1, tt / 1.6) * np.clip((e - s - tt) / 1.6, 0, 1)
        env = env ** 1.5
        for k, name in enumerate(tones + [bass]):
            f = note(name)
            amp = 0.11 if name != bass else 0.13
            for ch, det in ((0, 0.9985), (1, 1.0015)):
                ph = 2 * math.pi * f * det * tt + k
                v = np.sin(ph) + 0.22 * np.sin(2 * ph) + 0.06 * np.sin(3 * ph)
                out[ch, i0:i1] += amp * env * v

    # sparse bell melody on chord tones
    melody = [("A5", 0.6), ("F5", 2.9), ("F5", 6.1), ("D5", 8.4), ("A5", 11.6), ("C6", 13.9),
              ("G5", 17.1), ("E5", 19.4), ("A5", 22.6), ("F5", 24.9), ("F5", 28.1), ("D5", 30.4),
              ("D5", 33.6), ("Bb5", 35.9), ("A5", 39.1), ("D5", 41.6)]
    for i, (name, st) in enumerate(melody):
        f = note(name)
        i0 = int(st * SR)
        i1 = min(i0 + int(4.5 * SR), n)
        tt = t[i0:i1] - st
        env = np.minimum(1, tt / 0.008) * np.exp(-tt / 1.3)
        v = np.sin(2 * math.pi * f * tt) + 0.35 * np.sin(2 * math.pi * 2 * f * tt) * np.exp(-tt / 0.4) \
            + 0.12 * np.sin(2 * math.pi * 3.01 * f * tt) * np.exp(-tt / 0.2)
        pan = 0.5 + 0.25 * math.sin(i * 1.7)
        out[0, i0:i1] += 0.09 * env * v * (1 - pan) * 2
        out[1, i0:i1] += 0.09 * env * v * pan * 2

    # simple stereo reverb: FFT convolution with decaying noise
    rng = np.random.default_rng(3)
    ir_len = int(3.2 * SR)
    decay = np.exp(-np.arange(ir_len) / SR / 0.9)
    wet = np.zeros_like(out)
    size = 1 << int(math.ceil(math.log2(n + ir_len)))
    for ch in range(2):
        ir = rng.standard_normal(ir_len).astype(np.float32) * decay
        ir /= np.sqrt(np.sum(ir ** 2))
        wet[ch] = np.fft.irfft(np.fft.rfft(out[ch], size) * np.fft.rfft(ir, size), size)[:n]
    mix = 0.62 * out + 0.55 * wet

    fade = np.minimum(1, t / 1.2) * np.clip((DURATION - t) / 2.0, 0, 1)
    mix *= fade
    mix /= np.max(np.abs(mix)) / 0.7
    pcm = (mix.T * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--preview", type=float, nargs="*", help="only save stills at these times (s)")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    if args.preview:
        render_frame = make_renderer(build_scenes(args.fonts))
        for t in args.preview:
            Image.fromarray(render_frame(t)).save(os.path.join(args.out, f"preview_{t:05.1f}.png"))
        return

    raw_wav = os.path.join(args.out, "_music_raw.wav")
    wav = os.path.join(args.out, "_music.wav")
    synth_audio(raw_wav)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw_wav,
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", str(SR), wav], check=True)

    video = os.path.join(args.out, "oct7_memorial_he_1080x1920.mp4")
    render_video(build_scenes(args.fonts), video, wav)

    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "37.5", "-i", video,
                    "-frames:v", "1", "-q:v", "2", os.path.join(args.out, "cover.jpg")], check=True)
    for p in (raw_wav, wav):
        os.remove(p)
    print("done:", video)


if __name__ == "__main__":
    main()
