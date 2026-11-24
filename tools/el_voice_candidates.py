"""ElevenLabs 한국어 음성 후보 조회 + 샘플 생성 (Actions 전용, 키는 Secrets)."""
import json, os, sys, urllib.request, urllib.parse
from pathlib import Path

KEY = os.environ["ELEVENLABS_API_KEY"]
CUR = os.environ.get("ELEVENLABS_VOICE_ID", "")
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
TEXT = "보험금 청구에도 기한이 있습니다. 상법 제662조는 보험금청구권을 3년간 행사하지 않으면 시효로 소멸한다고 정하고 있습니다."
BAD = ("gyeong", "busan", "daegu", "jeolla", "jeju", "chungcheong", "dialect", "satoori", "saturi", "north", "pyongyang")

def api(path, data=None, method=None, raw=False):
    req = urllib.request.Request("https://api.elevenlabs.io" + path, method=method or ("POST" if data is not None else "GET"),
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={"xi-api-key": KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        b = r.read()
    return b if raw else json.loads(b)

rep = {}
try:
    s = api("/v1/user/subscription"); rep["plan"] = {k: s.get(k) for k in ("tier", "character_count", "character_limit", "voice_slots_used", "voice_limit", "professional_voice_limit")}
except Exception as e: rep["plan_err"] = str(e)[:200]
mine = api("/v2/voices?page_size=100").get("voices", [])
rep["my_voices"] = [{"id": v["voice_id"], "name": v["name"], "category": v.get("category"), "labels": v.get("labels"),
                     "current": v["voice_id"] == CUR} for v in mine]
if CUR and not any(v["current"] for v in rep["my_voices"]):
    try:
        v = api(f"/v1/voices/{CUR}"); rep["current_voice"] = {"name": v["name"], "labels": v.get("labels"), "category": v.get("category")}
    except Exception as e: rep["current_voice_err"] = str(e)[:200]
shared = []
for page in range(3):
    q = urllib.parse.urlencode({"language": "ko", "page_size": 100, "page": page, "sort": "usage_character_count_1y"})
    try:
        r = api("/v1/shared-voices?" + q)
    except Exception as e:
        rep["shared_err"] = str(e)[:200]; break
    shared += r.get("voices", [])
    if not r.get("has_more"): break
def flat(v): return json.dumps(v, ensure_ascii=False).lower()
rows = []
for v in shared:
    rows.append({k: v.get(k) for k in ("voice_id", "public_owner_id", "name", "gender", "age", "accent", "use_case", "descriptive",
                                         "category", "cloned_by_count", "usage_character_count_1y", "free_users_allowed", "description")}
                | {"dialect": any(b in flat(v) for b in BAD), "verified_languages": [
                    (l.get("language"), l.get("accent"), l.get("locale")) for l in (v.get("verified_languages") or [])]})
rep["shared_ko_count"] = len(rows)
rep["shared_ko"] = rows
(out / "voices.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

# 후보: 사투리 아님 + 정보/내레이션/대화 용도 + 많이 쓰인 순
good = [r for r in rows if not r["dialect"] and (r.get("use_case") or "") in ("informative_educational", "narrative_story", "conversational", "news", "social_media", "entertainment_tv", "")]
good.sort(key=lambda r: -(r.get("usage_character_count_1y") or 0))
pick = good[:int(os.environ.get("N_SAMPLES", "6"))]
sd = out / "samples"; sd.mkdir(exist_ok=True)
done = []
for i, r in enumerate(pick, 1):
    vid = r["voice_id"]
    try:
        if not any(m["voice_id"] == vid for m in mine):
            try:
                api(f"/v1/voices/add/{r['public_owner_id']}/{vid}", {"new_name": f"ko-{r['name']}"[:40]})
            except Exception as e:
                print("add 실패", r["name"], str(e)[:150])
        audio = api(f"/v1/text-to-speech/{vid}?output_format=mp3_44100_128",
                    {"text": TEXT, "model_id": "eleven_multilingual_v2"}, raw=True)
        fn = f"{i:02d}_{r['gender']}_{r['name']}".replace("/", "_").replace(" ", "_")[:60] + ".mp3"
        (sd / fn).write_bytes(audio); done.append({"file": fn, **r}); print("샘플 OK", fn)
    except Exception as e:
        print("샘플 실패", r["name"], str(e)[:200])
(out / "samples.json").write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(rep.get("plan"), ensure_ascii=False), rep.get("current_voice"), len(rows), "shared ko")
