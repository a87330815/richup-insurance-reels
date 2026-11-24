# -*- coding: utf-8 -*-
"""
news_collect.py — 보험업계 뉴스 수집기

네이버 뉴스 RSS + 주요 언론사 RSS로 실시간 이슈를 수집한다.
수집 결과는 out/news.json으로 저장.

사용:
  python news_collect.py                    # 기본 카테고리 수집
  python news_collect.py --category 경제    # 특정 카테고리
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
import xml.etree.ElementTree as ET

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "out")
SEEN_FILE = os.path.join(OUT_DIR, "news_seen.json")

# ── Google News RSS (공개, 키 불필요) ─────────────────────
# @ga.world 스타일 주제 비중:
#   보험·상품 인사이트  30%  — 변액/달러 상품 중심
#   영업 스킬·마인드셋  25%  — 설계사 현장 역량
#   의료·건강 트렌드    20%  — 중대질병·의료비·AI의료
#   경제·환율·금리      25%  — 환율, 금리, 미국/글로벌
#
# ※ 물가·부동산 제외 / 정치·연예·스포츠 제외

TOPIC_WEIGHT = {
    "GA·업계": 25,
    "보험상식·팩트체크": 30,
    "보상·의료": 20,
    "영업·리쿠르팅": 15,
    "사람·성장": 10,
}

# ga.world의 강점인 GA 현장정보·보험상식·팩트체크·인터뷰 구성을
# 리치업지점 관점으로 재편한다. 일반 경제뉴스는 보험 상담과 직접 연결되는
# 환율·금리만 제한적으로 포함한다.
NEWS_SOURCES = {
    "GA 제도·수수료": {
        "url": "https://news.google.com/rss/search?q=GA+법인보험대리점+수수료+금융감독원+보험설계사&hl=ko&gl=KR&ceid=KR:ko",
        "topic": "GA·업계",
    },
    "보험사·GA 동향": {
        "url": "https://news.google.com/rss/search?q=보험사+GA+채널+보험대리점+업계&hl=ko&gl=KR&ceid=KR:ko",
        "topic": "GA·업계",
    },
    "보험 제도 변경": {
        "url": "https://news.google.com/rss/search?q=보험+제도+개정+금융위원회+금융감독원&hl=ko&gl=KR&ceid=KR:ko",
        "topic": "GA·업계",
    },
    "보험상식 팩트체크": {
        "url": "https://news.google.com/rss/search?q=보험+소비자+유의사항+금감원+팩트체크&hl=ko&gl=KR&ceid=KR:ko",
        "topic": "보험상식·팩트체크",
    },
    "종신·연금·변액": {
        "url": "https://news.google.com/rss/search?q=종신보험+연금보험+변액보험+소비자+주의&hl=ko&gl=KR&ceid=KR:ko",
        "topic": "보험상식·팩트체크",
    },
    "달러보험·환율": {
        "url": "https://news.google.com/rss/search?q=달러보험+달러연금+환율+금리+보험&hl=ko&gl=KR&ceid=KR:ko",
        "topic": "보험상식·팩트체크",
    },
    "보험금 청구·분쟁": {
        "url": "https://news.google.com/rss/search?q=보험금+청구+분쟁+판례+금융감독원&hl=ko&gl=KR&ceid=KR:ko",
        "topic": "보상·의료",
    },
    "암·중증치료": {
        "url": "https://news.google.com/rss/search?q=암+표적항암+면역항암+치료비+건강보험&hl=ko&gl=KR&ceid=KR:ko",
        "topic": "보상·의료",
    },
    "치매·간병": {
        "url": "https://news.google.com/rss/search?q=치매+간병+장기요양+간병비+보험&hl=ko&gl=KR&ceid=KR:ko",
        "topic": "보상·의료",
    },
    "보험영업 현장": {
        "url": "https://news.google.com/rss/search?q=보험설계사+영업+고객상담+보장분석&hl=ko&gl=KR&ceid=KR:ko",
        "topic": "영업·리쿠르팅",
    },
    "리쿠르팅·조직성장": {
        "url": "https://news.google.com/rss/search?q=보험설계사+리쿠르팅+조직+교육+GA&hl=ko&gl=KR&ceid=KR:ko",
        "topic": "영업·리쿠르팅",
    },
    "우수설계사·인터뷰": {
        "url": "https://news.google.com/rss/search?q=보험설계사+인터뷰+우수인증설계사+성공사례&hl=ko&gl=KR&ceid=KR:ko",
        "topic": "사람·성장",
    },
}


# 언론사 표현 필터 (저작권 보호)
PRESS_RE = re.compile(
    r"무단\s*전재|재배포\s*금지|저작권자|[가-힣]{2,4}\s*기자"
    r"|\b(YTN|KBS|MBC|SBS|JTBC)\b"
)

# HTML 태그 제거
TAG_RE = re.compile(r"<[^>]+>")


def clean_text(text):
    """HTML 태그 제거, 엔티티 디코딩, 공백 정리."""
    text = TAG_RE.sub("", unescape(text or ""))
    return re.sub(r"\s+", " ", text).strip()


def article_key(title, link):
    """중복 판정용 해시."""
    base = f"{title}|{link}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=1)


def fetch_rss(url, category, timeout=15):
    """RSS 피드를 파싱해 기사 리스트를 반환."""
    articles = []
    try:
        r = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (issue-reels-bot/1.0)"
        })
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"  [경고] RSS 실패 ({category}): {e}")
        return articles

    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title", ""))
        link = (item.findtext("link", "") or "").strip()
        desc = clean_text(item.findtext("description", ""))
        pub_date = (item.findtext("pubDate", "") or "").strip()

        if not title or len(title) < 10 or not pub_date:
            continue
        # Google News 검색은 수년 전 기사도 섞는다. 최근 14일 기사만 수집한다.
        try:
            published = parsedate_to_datetime(pub_date)
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if published < now - timedelta(days=14) or published > now + timedelta(days=2):
                continue
        except (TypeError, ValueError, OverflowError):
            continue
        # 언론사 표현 필터
        if PRESS_RE.search(desc):
            desc = ""  # 본문에서 언론사 표현만 제거, 제목은 유지

        articles.append({
            "title": title,
            "link": link,
            "description": desc[:300],  # 300자로 제한
            "pub_date": pub_date,
            "category": category,
        })

    return articles


def fetch_news_via_search(query, category, timeout=15):
    """Google News RSS 검색으로 뉴스 수집."""
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
    return fetch_rss(url, category, timeout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default=None, help="특정 카테고리만 수집")
    ap.add_argument("--max", type=int, default=15, help="카테고리당 최대 기사 수")
    args = ap.parse_args()

    sources = NEWS_SOURCES
    if args.category:
        sources = {k: v for k, v in NEWS_SOURCES.items() if v["topic"] == args.category or k == args.category}

    seen = load_seen()
    all_articles = []
    dropped = 0

    for cat, src in sources.items():
        url = src["url"]
        topic = src["topic"]
        print(f"  [{topic} > {cat}] 수집 중...")
        articles = fetch_rss(url, cat)
        count = 0
        for art in articles:
            if count >= args.max:
                break
            k = article_key(art["title"], art["link"])
            if k in seen:
                continue
            # 제목에 언론사 표현이 있으면 폐기
            if PRESS_RE.search(art["title"]):
                dropped += 1
                continue
            seen.add(k)
            art["key"] = k
            art["topic"] = topic  # 주제 분류 태그
            all_articles.append(art)
            count += 1
        print(f"    → {count}건 수집")

    # 주제별 통계
    topic_counts = {}
    for art in all_articles:
        t = art.get("topic", "기타")
        topic_counts[t] = topic_counts.get(t, 0) + 1
    print(f"\n주제별 수집: {topic_counts}")

    # 저장
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "news.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "topic_weight": TOPIC_WEIGHT,
            "topic_counts": topic_counts,
            "items": all_articles,
        }, f, ensure_ascii=False, indent=2)
    save_seen(seen)

    print(f"\n수집 완료: {len(all_articles)}건 · 폐기 {dropped}건 → {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
