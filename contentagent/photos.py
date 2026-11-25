"""(계정 공통) 카드·릴스 배경 사진.

순서: 네이버 이미지 검색(NAVER_CLIENT_ID·NAVER_CLIENT_SECRET 있을 때, 한국어 검색어)
   → Unsplash(UNSPLASH_ACCESS_KEY 있을 때) → Openverse(키 없음, CC0·퍼블릭도메인만).
네이버는 쫌봐봐(issue-reels)와 같은 NAVER API HUB 엔드포인트·헤더를 씁니다.
한국어 검색어는 대본의 "photo_kr"(표지는 최상위, 장마다 slides[].photo_kr). 없으면 표지=title, 장=head, 마무리=summary.
영문 검색어는 "photo"(Unsplash·Openverse용). 없으면 계정 파일 "photo_fallback".
네이버 결과 중 계정 banned_names·보험사 이름이 제목/출처에 보이는 사진은 뺍니다. 사진을 못 받으면 단색 배경으로 진행합니다.
클라우드 예약 작업 환경은 프록시가 사진 사이트를 막으므로 실제로는 GitHub Actions 에서 받습니다.
"""
import io, json, os, re, urllib.parse, urllib.request
from pathlib import Path

UA = "contentagent/1.0"


def _get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


NAVER_URL = "https://naverapihub.apigw.ntruss.com/search/v1/image"  # NAVER API HUB (issue-reels 와 동일)
# 보험사·금융사 로고나 광고 이미지가 배경으로 깔리지 않게 거릅니다(계정 banned_names 와 함께).
_BRAND_BLOCK = ["삼성생명", "삼성화재", "한화생명", "교보생명", "DB손해", "DB손보", "현대해상", "KB손해", "KB손보",
                "메리츠", "흥국", "신한라이프", "동양생명", "미래에셋생명", "NH농협", "롯데손해", "AIA", "라이나", "ABL",
                "로고", "logo", "광고"]


def _naver(q):
    cid, sec = os.environ.get("NAVER_CLIENT_ID", "").strip(), os.environ.get("NAVER_CLIENT_SECRET", "").strip()
    u = NAVER_URL + "?" + urllib.parse.urlencode({"query": q, "display": 15, "sort": "sim", "filter": "large"})
    res = json.loads(_get(u, {"X-NCP-APIGW-API-KEY-ID": cid, "X-NCP-APIGW-API-KEY": sec}))
    out = []
    for it in res.get("items", []):
        if not it.get("link"):
            continue
        title = re.sub(r"<.*?>", "", it.get("title", ""))
        out.append({"url": it["link"], "credit": f"Naver 이미지 검색 / {title[:40]}",
                    "page": it.get("sourceUrl") or it["link"], "title": title})
    return out


def _blocked(c, cfg):
    hay = " ".join(str(c.get(k, "")) for k in ("title", "page", "url")).lower()
    if any(w.lower() in hay for w in cfg.get("banned_names") or []):
        return True
    title = str(c.get("title", "")).lower()  # 보험사 이름은 제목만 봄(영문 약어가 주소에 우연히 섞이는 것 방지)
    return any(w.lower() in title for w in _BRAND_BLOCK)


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


def queries_kr(script, cfg):
    """네이버용 한국어 검색어. photo_kr 이 없으면 카드 제목을 씁니다."""
    pages = ([script.get("photo_kr") or script.get("title", "")]
             + [s.get("photo_kr") or s.get("head", "") for s in script["slides"]]
             + [script.get("end_photo_kr") or script.get("summary") or script.get("title", "")])
    return [(q or "").strip() for q in pages]


def fetch(script, cfg, outdir):
    """페이지마다 사진 1장을 outdir/photos/NN.jpg 로. 돌려주는 값: [경로 또는 None], 출처 목록."""
    from PIL import Image
    key = os.environ.get("UNSPLASH_ACCESS_KEY", "")
    pd = Path(outdir) / "photos"; pd.mkdir(parents=True, exist_ok=True)
    used, paths, credits = set(), [], []
    naver = bool(os.environ.get("NAVER_CLIENT_ID", "").strip() and os.environ.get("NAVER_CLIENT_SECRET", "").strip())
    print(f"  [사진] 공급자: {'naver → ' if naver else ''}{'unsplash → ' if key else ''}openverse")
    fb = cfg.get("photo_fallback") or ["office desk morning light"]
    for n, (q, qk) in enumerate(zip(queries(script, cfg), queries_kr(script, cfg)), 1):
        got = None
        # 1) 네이버(한국어) 2) 대본 영문 검색어 3) 계정 기본 검색어 순서로 시도
        tries = ([("naver", qk, _naver)] if naver and qk else [])
        for qq in dict.fromkeys([q, fb[n % len(fb)]]):
            tries += ([("unsplash", qq, lambda x: _unsplash(x, key))] if key else []) + [("openverse", qq, _openverse)]
        for name, qq, fn in tries:
            try:
                cands = [c for c in fn(qq) if c["url"] not in used and not _blocked(c, cfg)]
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
                used.add(c["url"]); got = f; credits.append({"page": n, "query": qq, "source": name, **c}); break
            if got:
                break
        print(f"  [사진] {n:02d} '{qk or q}' → {('OK ' + credits[-1]['source'] + ' / ' + credits[-1]['credit']) if got else '없음(단색 배경)'}")
        paths.append(got)
    (pd / "credits.json").write_text(json.dumps(credits, ensure_ascii=False, indent=1), encoding="utf-8")
    return paths, credits
