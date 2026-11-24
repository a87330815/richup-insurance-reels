"""(계정 공통) 장면별 내레이션 → TTS 음성.

엔진 순서: ElevenLabs(ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID 가 있을 때) → edge-tts(무료, 키 없음).
둘 다 안 되면 None 을 돌려주고, 렌더는 무음 릴스로 진행합니다(--require-voice 면 중단).

클라우드 예약 작업 환경은 프록시가 TTS 서버를 막습니다. 음성이 들어간 릴스는
GitHub Actions(.github/workflows/contentagent_render.yml)에서 만듭니다. 키는 저장소 Secrets 에 있습니다.
계정 파일의 "voice" 로 계정마다 목소리를 바꿀 수 있습니다:
  {"elevenlabs_voice_id": "", "elevenlabs_model": "", "edge_voice": "ko-KR-SunHiNeural", "edge_rate": "+8%"}
"""
import asyncio, os, shutil, subprocess
from pathlib import Path


def narration(script, cfg):
    """카드 순서(표지, 슬라이드들, 마무리)와 같은 순서의 읽을 문장 목록."""
    lines = [f"{script['title']}. {script.get('hook', '')}".strip()]
    lines += [f"{s['head']}. {s['body']}" for s in script["slides"]]
    lines.append(f"{script.get('summary', script['title'])}. {cfg['cta']}")
    return [ln.replace("…", ".").replace("·", ", ") for ln in lines]


def _vcfg(cfg):
    v = dict(cfg.get("voice") or {})
    return {
        "el_key": os.environ.get("ELEVENLABS_API_KEY", ""),
        "el_voice": v.get("elevenlabs_voice_id") or os.environ.get("ELEVENLABS_VOICE_ID", ""),
        "el_model": v.get("elevenlabs_model") or os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2"),
        "edge_voice": v.get("edge_voice") or os.environ.get("TTS_VOICE", "ko-KR-SunHiNeural"),
        "edge_rate": v.get("edge_rate") or os.environ.get("TTS_RATE", "+8%"),
    }


def _elevenlabs(text, path, v):
    try:
        from elevenlabs.client import ElevenLabs
        audio = ElevenLabs(api_key=v["el_key"]).text_to_speech.convert(
            text=text, voice_id=v["el_voice"], model_id=v["el_model"], output_format="mp3_44100_128")
        with open(path, "wb") as f:
            for chunk in audio:
                f.write(chunk)
        return Path(path).stat().st_size > 1000
    except Exception as e:  # 키 만료·한도 초과 등
        print(f"  [TTS] ElevenLabs 실패: {str(e)[:200]}")
        return False


def _edge(text, path, v):
    try:
        import edge_tts
        asyncio.run(edge_tts.Communicate(text, v["edge_voice"], rate=v["edge_rate"]).save(str(path)))
        return Path(path).stat().st_size > 1000
    except Exception as e:
        print(f"  [TTS] edge-tts 실패: {str(e)[:200]}")
        return False


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True)
    return float(out.stdout.strip() or 0)


def synthesize(script, cfg, outdir):
    """장면별 mp3 를 outdir/voice/ 에 만들고 [(경로, 초)] 와 엔진 이름을 돌려줍니다. 실패하면 (None, 이유)."""
    if not shutil.which("ffprobe"):
        return None, "ffprobe 없음"
    v = _vcfg(cfg)
    engines = []
    if v["el_key"] and v["el_voice"]:
        engines.append(("elevenlabs", _elevenlabs))
    engines.append(("edge-tts", _edge))
    vd = Path(outdir) / "voice"; vd.mkdir(parents=True, exist_ok=True)
    lines = narration(script, cfg)
    for name, fn in engines:
        clips = []
        for n, text in enumerate(lines, 1):
            p = vd / f"{n:02d}.mp3"
            if not fn(text, p, v):
                clips = None; break
            clips.append((p, duration(p)))
            print(f"  [TTS {name}] {n}/{len(lines)} {clips[-1][1]:.1f}초  {text[:30]}…")
        if clips:
            return clips, name
        print(f"  [TTS] {name} 로 끝까지 만들지 못해 다음 엔진으로 넘어갑니다.")
    return None, "TTS 엔진 모두 실패(네트워크 차단 또는 키 문제)"
