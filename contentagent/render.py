"""(계정 공통) script.json → 카드 PNG(1080x1350, 캐러셀) + 릴스 프레임(1080x1920) + 릴스 MP4 + caption.txt

선택: photos=True 면 페이지마다 배경 사진(contentagent/photos.py), voice=True 면 장면별 TTS 음성(contentagent/voice.py).
음성이 있으면 장면 길이는 음성 길이에 맞춥니다. 둘 다 인터넷이 열린 곳(GitHub Actions)에서만 됩니다.

글꼴은 config.font_paths 에서 처음 찾은 것을 씁니다(윈도 맑은 고딕, 맥 애플 SD 고딕 네오 등).
"""
import shutil, subprocess, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SIZES = {"card": (1080, 1350), "reel": (1080, 1920)}


def find_font(cfg):
    for p in cfg["font_paths"]:
        if Path(p).exists():
            return p
    raise SystemExit("한글 글꼴을 찾지 못했습니다. accounts/_defaults.json(또는 계정 파일)의 font_paths 에 글꼴 파일 경로를 넣으십시오.")


def with_photo(base, photo, bg_hex):
    """사진을 꽉 차게 자르고, 글씨가 읽히도록 브랜드 배경색으로 덮습니다(위 55% → 아래 88%)."""
    W, H = base.size
    ph = Image.open(photo).convert("RGB")
    s = max(W / ph.width, H / ph.height)
    ph = ph.resize((int(ph.width * s) + 1, int(ph.height * s) + 1), Image.LANCZOS)
    l, t = (ph.width - W) // 2, (ph.height - H) // 2
    ph = ph.crop((l, t, l + W, t + H))
    mask = Image.linear_gradient("L").resize((W, H))  # 위 0 → 아래 255
    mask = mask.point(lambda v: int(140 + v * (225 - 140) / 255))
    return Image.composite(base, ph, mask)


class Painter:
    def __init__(self, cfg, kind):
        self.cfg, self.kind = cfg, kind
        self.W, self.H = SIZES[kind]
        self.c = cfg["colors"]
        self.font_path = find_font(cfg)
        self.pad = 90
        # 릴스는 위아래 UI(계정명·캡션)에 가리지 않도록 안전 영역을 둡니다.
        self.top, self.bottom = (120, self.H - 120) if kind == "card" else (300, self.H - 420)

    def font(self, size):
        return ImageFont.truetype(self.font_path, size)

    def new(self, photo=None):
        im = Image.new("RGB", (self.W, self.H), self.c["bg"])
        if photo:
            im = with_photo(im, photo, self.c["bg"])
        return im, ImageDraw.Draw(im)

    def wrap(self, d, text, font, width):
        lines = []
        for para in text.split("\n"):
            cur = ""
            for word in para.split(" "):
                trial = f"{cur} {word}".strip()
                if d.textlength(trial, font=font) <= width:
                    cur = trial
                    continue
                if cur:
                    lines.append(cur)
                cur = ""
                for ch in word:  # 한 단어가 한 줄보다 길면 글자 단위로 자름
                    if d.textlength(cur + ch, font=font) > width and cur:
                        lines.append(cur); cur = ""
                    cur += ch
            lines.append(cur)
        return lines

    def block(self, d, xy, text, size, fill, width, gap=1.35, max_lines=None):
        f = self.font(size)
        lines = self.wrap(d, text, f, width)
        if max_lines and len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1].rstrip()[:-1] + "…"
        x, y = xy
        for ln in lines:
            d.text((x, y), ln, font=f, fill=fill)
            y += int(size * gap)
        return y

    def tag(self, d, xy, text, size=40):
        f = self.font(size)
        w = d.textlength(text, font=f)
        x, y = xy
        d.rounded_rectangle((x, y, x + w + 48, y + size + 30), radius=16, fill=self.c["accent"])
        d.text((x + 24, y + 12), text, font=f, fill=self.c["bg"])
        return y + size + 30

    def footer(self, d, page, total, source_line):
        f = self.font(30)
        y = self.bottom - 40
        d.text((self.pad, y), self.cfg["brand"], font=self.font(34), fill=self.c["accent"])
        pg = f"{page}/{total}"
        d.text((self.W - self.pad - d.textlength(pg, font=f), y + 2), pg, font=f, fill=self.c["sub"])
        if source_line:
            self.block(d, (self.pad, y - 56), source_line, 26, self.c["sub"], self.W - 2 * self.pad, max_lines=1)


def source_line(script):
    s = script["sources"][0]
    more = f" 외 {len(script['sources']) - 1}건" if len(script["sources"]) > 1 else ""
    return f"출처: {s['name']} ({s['date']}){more}"


def stack(p, d, items):
    """items = [(종류, 값, 크기, 색, 줄간격, 뒤여백, 최대줄)] 를 세로 가운데(약간 위)에 배치."""
    w = p.W - 2 * p.pad
    def height(it):
        kind, val, size, _, gap, after, mx = it
        if kind == "tag": return size + 30 + after
        if kind == "bar": return 10 + after
        n = len(p.wrap(d, val, p.font(size), w))
        return int(size * gap) * (min(n, mx) if mx else n) + after
    total = sum(height(it) for it in items)
    avail_top, avail_bot = p.top, p.bottom - 140
    y = avail_top + max(0, int((avail_bot - avail_top - total) * 0.42))
    for it in items:
        kind, val, size, color, gap, after, mx = it
        if kind == "tag": y = p.tag(d, (p.pad, y), val, size) + after
        elif kind == "bar":
            d.rectangle((p.pad, y, p.pad + 120, y + 10), fill=p.c["accent"]); y += 10 + after
        else: y = p.block(d, (p.pad, y), val, size, color, w, gap=gap, max_lines=mx) + after
    return y


def draw_cover(p, script, total, photo=None):
    im, d = p.new(photo)
    items = [("tag", script.get("series") or p.cfg["brand"], 44, None, 0, 60, None),
             ("text", script["title"], 112 if p.kind == "card" else 120, p.c["text"], 1.22, 50, 4),
             ("bar", None, 0, None, 0, 50, None)]
    if script.get("hook"):
        items.append(("text", script["hook"], 52, p.c["sub"], 1.35, 0, 3))
    stack(p, d, items)
    p.footer(d, 1, total, source_line(script))
    return im


def draw_slide(p, script, i, sl, total, photo=None):
    im, d = p.new(photo)
    stack(p, d, [("text", f"{i:02d}", 64, p.c["accent"], 1.3, 30, 1),
                 ("text", sl["head"], 84, p.c["accent"], 1.22, 50, 3),
                 ("text", sl["body"], 58, p.c["text"], 1.5, 0, 8)])
    p.footer(d, i + 1, total, source_line(script))
    return im


def draw_end(p, script, total, photo=None):
    im, d = p.new(photo)
    items = [("tag", "한 줄 정리", 44, None, 0, 50, None),
             ("text", script.get("summary", script["title"]), 76, p.c["text"], 1.25, 60, 4),
             ("text", p.cfg["cta"], 46, p.c["accent"], 1.35, 60, 2),
             ("text", "출처", 34, p.c["sub"], 1.4, 6, 1)]
    items += [("text", f"· {s['name']} ({s['date']})", 32, p.c["sub"], 1.4, 0, 2) for s in script["sources"][:4]]
    stack(p, d, items)
    p.block(d, (p.pad, p.bottom - 150), p.cfg["disclaimer"], 28, p.c["sub"], p.W - 2 * p.pad, max_lines=2)
    p.footer(d, total, total, None)
    return im


def frames(script, cfg, kind, photos=None):
    p = Painter(cfg, kind)
    total = len(script["slides"]) + 2
    ph = list(photos or []) + [None] * total
    out = [draw_cover(p, script, total, ph[0])]
    out += [draw_slide(p, script, i, sl, total, ph[i]) for i, sl in enumerate(script["slides"], 1)]
    out.append(draw_end(p, script, total, ph[total - 1]))
    return out


def caption_text(script, cfg):
    parts = [script.get("caption", "").strip()]
    for extra in cfg.get("required_caption", []) + [cfg["disclaimer"]]:
        if extra and extra not in parts[0]:
            parts.append(extra)
    parts.append("출처\n" + "\n".join(f"- {s['name']} ({s['date']}){' ' + s['url'] if s.get('url') else ''}" for s in script["sources"]))
    tags = list(dict.fromkeys(script.get("hashtags", []) + cfg["default_hashtags"]))[:12]
    parts.append(" ".join(tags))
    return "\n\n".join(p for p in parts if p)


def make_reel(paths, out, seconds, clips=None):
    """장면마다 짧은 mp4 를 만든 뒤 이어 붙입니다. clips=[(mp3, 초)] 가 있으면 장면 길이 = 음성 + 0.5초."""
    ff = shutil.which("ffmpeg")
    if not ff:
        return None
    tmp = Path(tempfile.mkdtemp())
    segs = []
    for n, png in enumerate(paths):
        seg = tmp / f"{n:02d}.mp4"
        if clips:
            mp3, dur = clips[n]
            dur = round(dur + 0.5, 2)
            audio = ["-i", str(mp3)]
            af = ["-af", "apad,loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "44100", "-ac", "2"]
        else:
            dur = seconds
            audio = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
            af = []
        cmd = [ff, "-y", "-loglevel", "error", "-loop", "1", "-framerate", "30", "-i", str(png), *audio, *af,
               "-t", str(dur), "-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
               "-tune", "stillimage", "-c:a", "aac", "-b:a", "128k", str(seg)]
        subprocess.run(cmd, check=True)
        segs.append(seg)
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in segs), encoding="utf-8")
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", "-movflags", "+faststart", str(out)], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return out


def render(script, cfg, outdir, reel=True, photos=False, voice=False, require_voice=False):
    outdir = Path(outdir)
    (outdir / "cards").mkdir(parents=True, exist_ok=True)
    made, notes = [], []
    ph = None
    if photos:
        from . import photos as photomod
        ph, credits = photomod.fetch(script, cfg, outdir)
        notes.append(f"배경 사진 {sum(1 for x in ph if x)}/{len(ph)}장 (출처 photos/credits.json)")
    clips = None
    if reel and voice:
        from . import voice as voicemod
        clips, engine = voicemod.synthesize(script, cfg, outdir)
        if clips:
            notes.append(f"음성: {engine}, 총 {sum(d for _, d in clips):.0f}초")
        elif require_voice:
            raise SystemExit(f"음성을 만들지 못했습니다: {engine}")
        else:
            notes.append(f"음성 없음(무음 릴스): {engine}")
    for n, im in enumerate(frames(script, cfg, "card", ph), 1):
        f = outdir / "cards" / f"{n:02d}.png"; im.save(f); made.append(f)
    if reel:
        (outdir / "reel_frames").mkdir(exist_ok=True)
        rf = []
        for n, im in enumerate(frames(script, cfg, "reel", ph), 1):
            f = outdir / "reel_frames" / f"{n:02d}.png"; im.save(f); rf.append(f)
        mp4 = make_reel(rf, outdir / "reel.mp4", cfg["reel_seconds_per_slide"], clips)
        if mp4: made.append(mp4)
    (outdir / "caption.txt").write_text(caption_text(script, cfg), encoding="utf-8")
    made.append(outdir / "caption.txt")
    for n in notes:
        print(n)
    return made
