# -*- coding: utf-8 -*-
"""
collect_trends.py — 트렌드 키워드 수집기

Google Trends Korea RSS + 네이버 실시간 검색어에서 화제 키워드를 수집한다.
API 키 없이 동작한다.

수집 결과는 out/trends.json에 저장되고, scriptgen.py가 이를 읽어
LLM에 넘겨 "사실만 뽑아 완전히 새 문장으로" 대본을 생성한다.

카테고리 자동 분류:
  - 당일 화제 이슈 (40%)
  - 생활·지원금·제도 (25%)
  - 놀라운 사건·화제 (15%)
  - 경제·부동산 (20%) ← 기존 collect.py가 담당, 여기선 안 건드림

사용:
  python collect_trends.py              # 트렌드 수집 → out/trends.json
  python collect_trends.py --list       # 수집 결과 미리보기
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "out")

# 제외 키워드 — 연예·스포츠만 제외. 경제·선거·환율은 설계사 관심 주제이므로 허용
EXCLUDE_PATTERNS = [
    # 국내 정당 정치 (경제정책·선거 영향은 허용)
    r"(여당|야당|민주당|국민의힘|더불어|정당|탄핵|의원)",
    # 연예
    r"(아이돌|걸그룹|보이그룹|드라마|예능|방송|출연|열애|결혼|이혼)",
    # 스포츠
    r"(프로야구|K리그|EPL|챔피언스리그|올림픽|월드컵|축구|야구|농구)",
    r"(팬미팅|컴백|신곡|뮤직비디오|화보|팬사인회)",
]
EXCLUDE_RE = re.compile("|".join(EXCLUDE_PATTERNS))

# 카테고리 분류 키워드 — 설계사 관심 주제 우선
CATEGORY_RULES = {
    "보험·금융규제": [
        r"(보험|생명보험|손해보험|GA|설계사|모집|수수료|해약|환급금|보장|1200|킥스|IFRS|RBC)",
        r"(금감원|금융위|금융감독|인가|제재|과징금|민원|완전판매|불완전판매)",
        r"(변액|연금|종신|달러|외화|저축보험|실손|건강보험|간편보험)",
    ],
    "경제·환율·금리": [
        r"(금리|환율|달러|엔화|위안|원달러|기준금리|한은|한국은행|Fed|연준|FOMC)",
        r"(주가|코스피|코스닥|나스닥|S&P|다우|증시|주식시장)",
        r"(인플레이션|디플레이션|경기|GDP|성장률|고용|실업|무역|수출|수입)",
        r"(유가|원유|WTI|브렌트|관세|무역전쟁|경제전쟁)",
    ],
    "선거·정책·글로벌": [
        r"(선거|대통령|트럼프|바이든|해리스|대선|미국|중국|일본|EU)",
        r"(정책|규제|세금|세제|개정|시행|제도|정부)",
        r"(전쟁|지정학|중동|우크라이나|NATO|안보)",
    ],
    "생활·제도변경": [
        r"(지원금|환급|보조금|급여|수당|연금|세금|공제|감면|혜택|신청|시행|개정)",
        r"(건강보험|의료|병원|약국)",
    ],
}


def classify_category(title, snippet=""):
    """키워드와 스니펫으로 카테고리를 분류한다."""
    text = f"{title} {snippet}"
    for cat, patterns in CATEGORY_RULES.items():
        for p in patterns:
            if re.search(p, text):
                return cat
    return "당일 화제 이슈"  # 기본값


def is_excluded(title, snippet=""):
    """프로젝트 기준에서 제외하는 주제인지 확인."""
    text = f"{title} {snippet}"
    return bool(EXCLUDE_RE.search(text))


def trend_key(title):
    """중복 판정용 키."""
    return hashlib.sha1(title.encode("utf-8")).hexdigest()[:16]


def fetch_google_trends_kr():
    """Google Trends Korea daily trends RSS를 가져온다. API 키 불필요."""
    import requests
    url = "https://trends.google.co.kr/trending/rss?geo=KR"
    items = []
    try:
        r = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; issue-reels-bot/1.0)"
        })
        r.raise_for_status()

        # RSS XML 파싱 — 간단한 정규식 (의존성 최소화)
        for block in re.findall(r"<item>(.*?)</item>", r.text, re.S):
            title_m = re.search(r"<title>([^<]+)</title>", block)
            traffic_m = re.search(r"<ht:approx_traffic>([^<]+)</ht:approx_traffic>", block)
            news_items = re.findall(r"<ht:news_item_title>([^<]+)</ht:news_item_title>", block)
            news_snippets = re.findall(r"<ht:news_item_snippet>([^<]+)</ht:news_item_snippet>", block)

            if not title_m:
                continue

            title = title_m.group(1).strip()
            traffic = traffic_m.group(1).strip() if traffic_m else ""
            snippet = news_snippets[0] if news_snippets else ""
            news_title = news_items[0] if news_items else ""

            items.append({
                "keyword": title,
                "traffic": traffic,
                "news_title": news_title,
                "snippet": snippet,
                "source_type": "google_trends",
            })
        print(f"  Google Trends: {len(items)}건")
    except Exception as e:
        print(f"  [경고] Google Trends 수집 실패: {e}")
    return items


def fetch_naver_datalab():
    """네이버 DataLab 실시간 검색어 (비공식 — API 키 불필요).
    실패해도 Google Trends가 있으므로 치명적이지 않다."""
    import requests
    items = []
    try:
        # 네이버 실시간 급상승 검색어 (signal 페이지)
        url = "https://datalab.naver.com/keyword/realtimeList.naver"
        r = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (compatible; issue-reels-bot/1.0)",
            "Referer": "https://datalab.naver.com/",
        })
        if r.status_code == 200:
            # JSON 응답에서 키워드 추출
            try:
                data = r.json()
                for rank_item in data.get("data", []):
                    for kw_item in rank_item.get("data", []):
                        keyword = kw_item.get("keyword", "").strip()
                        if keyword:
                            items.append({
                                "keyword": keyword,
                                "traffic": "",
                                "news_title": "",
                                "snippet": "",
                                "source_type": "naver_datalab",
                            })
            except (json.JSONDecodeError, KeyError):
                # HTML 응답일 수도 있음 — 키워드 추출 시도
                keywords = re.findall(r'"keyword"\s*:\s*"([^"]+)"', r.text)
                for kw in keywords[:20]:
                    items.append({
                        "keyword": kw,
                        "traffic": "",
                        "news_title": "",
                        "snippet": "",
                        "source_type": "naver_datalab",
                    })
        print(f"  네이버 DataLab: {len(items)}건")
    except Exception as e:
        print(f"  [알림] 네이버 DataLab 수집 실패 (비필수): {e}")
    return items


def load_seen_trends():
    """이미 처리한 트렌드 키 목록."""
    path = os.path.join(OUT_DIR, "seen_trends.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def save_seen_trends(seen):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "seen_trends.json")
    # 최근 500개만 유지 (오래된 건 다시 수집 가능하도록)
    recent = sorted(seen)[-500:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(recent, f, ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser(description="트렌드 키워드 수집")
    ap.add_argument("--list", action="store_true", help="수집 결과 미리보기")
    args = ap.parse_args()

    print("트렌드 수집 시작")

    # 1. 수집
    raw = []
    raw.extend(fetch_google_trends_kr())
    raw.extend(fetch_naver_datalab())

    if not raw:
        print("\n[경고] 트렌드 수집 결과 0건")
        return 1

    # 2. 중복 제거 (키워드 기준)
    seen_keywords = set()
    deduped = []
    for item in raw:
        kw = item["keyword"]
        if kw in seen_keywords:
            continue
        seen_keywords.add(kw)
        deduped.append(item)

    # 3. 프로젝트 기준 필터 (정치·연예·스포츠 제외)
    filtered = []
    excluded = 0
    for item in deduped:
        if is_excluded(item["keyword"], item.get("snippet", "")):
            excluded += 1
            continue
        filtered.append(item)

    # 4. 카테고리 분류
    for item in filtered:
        item["category"] = classify_category(
            item["keyword"], item.get("snippet", "")
        )
        item["key"] = trend_key(item["keyword"])

    # 5. 이미 처리한 트렌드 제거
    seen = load_seen_trends()
    new_items = [item for item in filtered if item["key"] not in seen]

    if args.list:
        print(f"\n전체 {len(raw)}건 → 중복제거 {len(deduped)}건 → 필터통과 {len(filtered)}건 → 신규 {len(new_items)}건 (제외 {excluded}건)")
        for item in new_items:
            print(f"  [{item['category']}] {item['keyword']}"
                  f"{' (' + item['traffic'] + ')' if item.get('traffic') else ''}")
        return 0

    # 6. 저장
    for item in new_items:
        seen.add(item["key"])
    save_seen_trends(seen)

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "trends.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "items": new_items,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n트렌드 수집 {len(new_items)}건 · 제외 {excluded}건 → {out}")

    # 카테고리별 집계
    cats = {}
    for item in new_items:
        cats[item["category"]] = cats.get(item["category"], 0) + 1
    for cat, cnt in sorted(cats.items()):
        print(f"  {cat}: {cnt}건")

    return 0


if __name__ == "__main__":
    sys.exit(main())
