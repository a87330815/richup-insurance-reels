"""(계정 공통) 장면별 내레이션 → TTS 음성.

엔진 순서: ElevenLabs(ELEVENLABS_API_KEY + ELEVENLABS_VOICE_ID 가 있을 때) → edge-tts(무료, 키 없음).
둘 다 안 되면 None 을 돌려주고, 렌더는 무음 릴스로 진행합니다(--require-voice 면 중단).

클라우드 예약 작업 환경은 프록시가 TTS 서버를 막습니다. 음성이 들어간 릴스는
GitHub Actions(.github/workflows/contentagent_render.yml)에서 만듭니다. 키는 저장소 Secrets 에 있습니다.
계정 파일의 "voice" 로 계정마다 목소리를 바꿀 수 있습니다:
  {"elevenlabs_voice_id": "", "elevenlabs_model": "", "speed": 1.15, "edge_voice": "ko-KR-SunHiNeural", "edge_rate": "+20%"}
"speed" 는 ElevenLabs 말 빠르기(0.7~1.2, 1.0 이 기본). 목소리의 저장된 설정(안정성 등)은 그대로 두고 빠르기만 바꿉니다.
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
        "speed": min(1.2, max(0.7, float(v.get("speed") or os.environ.get("ELEVENLABS_SPEED") or 1.0))),
    }


def _el_settings(client, v):
    """목소리에 저장된 설정에 speed 만 덮어씁니다. 한 번 받아 두고 장면마다 재사용."""
    if abs(v["speed"] - 1.0) < 1e-6:
        return None
    if "_settings" not in v:
        from elevenlabs import VoiceSettings
        try:
            vo = client.voices
            st = vo.settings.get(v["el_voice"]) if hasattr(vo, "settings") else vo.get_settings(v["el_voice"])
            base = st.model_dump(exclude_none=True) if hasattr(st, "model_dump") else dict(st)
        except Exception as e:
            print(f"  [TTS] 목소리 기본 설정을 못 받아 빠르기만 지정합니다: {str(e)[:120]}")
            base = {}
        base["speed"] = v["speed"]
        v["_settings"] = VoiceSettings(**base)
        print(f"  [TTS] ElevenLabs 빠르기 {v['speed']}")
    return v["_settings"]


def _elevenlabs(text, path, v):
    try:
        from elevenlabs.client import ElevenLabs
        client = ElevenLabs(api_key=v["el_key"])
        extra = {}
        vs = _el_settings(client, v)
        if vs is not None:
            extra["voice_settings"] = vs
        audio = client.text_to_speech.convert(
            text=text, voice_id=v["el_voice"], model_id=v["el_model"], output_format="mp3_44100_128", **extra)
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
