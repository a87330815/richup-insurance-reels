import json, os, re, sys

script_path = sys.argv[1]
photo_dir = sys.argv[2]
with open(script_path, encoding='utf-8') as f:
    script = json.load(f)

scenes = script.get('scenes', [])
if not scenes:
    raise SystemExit('검수 실패: 장면이 없습니다')

hook = (script.get('title','') + ' ' + scenes[0].get('subtitle','') + ' ' + scenes[0].get('narration','')).strip()
hook_words = ['진짜', '무조건', '지금', '모르면', '줄어', '위험', '주의', '손해', '수입', '왜']
if not any(w in hook for w in hook_words) or len(hook) < 12:
    raise SystemExit('검수 실패: 첫 장면에 자극적인 훅이 없습니다')

wanted = ['cover'] + [f'scene{i+1}' for i in range(len(scenes))]
missing = [slot for slot in wanted if not os.path.isfile(os.path.join(photo_dir, slot + '.jpg'))]
if missing:
    raise SystemExit('검수 실패: 사진 누락 - ' + ', '.join(missing))

# 사람 장면은 한국인 조건을 한국어·영어 표기 모두 인정한다.
for i, scene in enumerate(scenes, 1):
    q = scene.get('photo_query','').lower()
    if any(x in q for x in ['person','agent','customer','team','people','man','woman']) and not any(x in q for x in ['korean','korea','한국인','한국','대한민국']):
        raise SystemExit(f'검수 실패: scene{i} 한국인 조건 없는 인물 검색어')

if not os.environ.get('ELEVENLABS_API_KEY') or not os.environ.get('ELEVENLABS_VOICE_ID'):
    raise SystemExit('검수 실패: ElevenLabs 음성 키 또는 Voice ID가 없습니다')
print('검수 통과: 훅, 사진 전량, 한국인 인물 조건, ElevenLabs 음성 ID')
