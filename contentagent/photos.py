"""(계정 공통) 카드·릴스 배경 사진.

순서: Unsplash(UNSPLASH_ACCESS_KEY 있을 때) → Openverse(키 없음, CC0·퍼블릭도메인만).
검색어는 대본의 영문 "photo"(표지는 최상위 "photo", 장마다 slides[].photo). 없으면 계정 파일 "photo_fallback".
보도사진·기관 그래픽은 쓰지 않습니다. 사진을 못 받으면 단색 배경으로 진행합니다.
클라우드 예약 작업 환경은 프록시가 사진 사이트를 막으므로 실제로는 GitHub Actions 에서 받습니다.
"""
import io, json, os, urllib.parse, urllib.request
from pathlib import Path

UA = "contentagent/1.0"


def _get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _unsplash(q, key):
    u = "https://api.unsplash.com/search/photos?" + urllib.parse.urlencode(
        {"query": q, "per_page": 10, "orientation": "portrait", "content_filter": "high"})
    res = json.loads(_get(u, {"Authorization": f"Client-ID {key}"}))
    return [{"url": it["urls"]["regular"], "credit": f"Unsplash / {it.get('user', {}).get('name', '')}",
             "page": it.get("links", {}).get("html", "")} for it in res.get("results", []) if it.get("urls")]


def _openverse(q):
    u = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(
        {"q": q, "license": "cc0,pdm", "page_size": 10, "mature": "false"})
    res = json.loads(_get(u, {"Accept": "application/json"}))
    return [{"url": it["url"], "credit": f"{it.get('source', 'Openverse')} ({(it.get('license') or '').upper()})",
             "page": it.get("foreign_landing_url", "")} for it in res.get("results", []) if it.get("url")]


def queries(script, cfg):
    fb = cfg.get("photo_fallback") or ["documents desk", "city morning", "calm office"]
    pages = [script.get("photo")] + [s.get("photo") for s in script["slides"]] + [script.get("end_photo")]
    return [q or fb[i % len(fb)] for i, q in enumerate(pages)]


def fetch(script, cfg, outdir):
    """페이지마다 사진 1장을 outdir/photos/NN.jpg 로. 돌려주는 값: [경로 또는 None], 출처 목록."""
    from PIL import Image
    key = os.environ.get("UNSPLASH_ACCESS_KEY", "")
    pd = Path(outdir) / "photos"; pd.mkdir(parents=True, exist_ok=True)
    used, paths, credits = set(), [], []
    fb = cfg.get("photo_fallback") or ["office desk morning light"]
    for n, q in enumerate(queries(script, cfg), 1):
        got = None
        # 대본 검색어로 못 받으면 계정 기본 검색어로 한 번 더
        for qq in dict.fromkeys([q, fb[n % len(fb)]]):
            for name, fn in ([("unsplash", lambda x: _unsplash(x, key))] if key else []) + [("openverse", _openverse)]:
                try:
                    cands = [c for c in fn(qq) if c["url"] not in used]
                except Exception as e:
                    print(f"  [사진] {name} '{qq}' 검색 실패: {str(e)[:120]}"); continue
                if not cands:
                    print(f"  [사진] {name} '{qq}' 결과 없음")
                for c in cands[:8]:
                    try:
                        im = Image.open(io.BytesIO(_get(c["url"], timeout=30))).convert("RGB")
                    except Exception as e:
                        print(f"  [사진] 내려받기 실패: {str(e)[:80]}"); continue
                    if min(im.size) < 600:
                        continue
                    f = pd / f"{n:02d}.jpg"; im.save(f, quality=90)
                    used.add(c["url"]); got = f; credits.append({"page": n, "query": qq, **c}); break
                if got:
                    break
            if got:
                break
        print(f"  [사진] {n:02d} '{q}' → {'OK ' + credits[-1]['credit'] if got else '없음(단색 배경)'}")
        paths.append(got)
    (pd / "credits.json").write_text(json.dumps(credits, ensure_ascii=False, indent=1), encoding="utf-8")
    return paths, credits
