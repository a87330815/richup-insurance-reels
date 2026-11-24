"""게시 전 자동 검수. 사람 검수를 대신하지 않고, 놓치기 쉬운 것을 먼저 거릅니다.

공통 검사(모든 계정): 글자 수, 카드 장수, 출처 유무·날짜 형식·약한 출처, 필수 문구, 금지 이름.
계정별 검사: 계정 설정의 rule_presets + compliance.block / compliance.warn (presets.py 참고).
"""
import re
from . import presets

WEAK_SOURCES = r"^(google\s*trends|구글\s*트렌드|네이버\s*데이터랩|뉴스|인터넷|SNS|유튜브)$"
NUMBER = re.compile(r"\d")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _texts(s):
    yield "title", s.get("title", "")
    yield "hook", s.get("hook", "")
    for i, sl in enumerate(s.get("slides", []), 1):
        yield f"slide{i}.head", sl.get("head", "")
        yield f"slide{i}.body", sl.get("body", "")
    yield "summary", s.get("summary", "")
    yield "caption", s.get("caption", "")
    yield "hashtags", " ".join(s.get("hashtags", []))


def check(script, cfg):
    """[(level, where, message)] 를 돌려줍니다. level 은 'block' 또는 'warn'."""
    out = []
    rules = presets.collect(cfg)
    banned = cfg.get("banned_names", [])
    for where, text in _texts(script):
        for lv, pat, why in rules:
            m = re.search(pat, text, re.I)
            if m:
                out.append((lv, where, f"'{m.group(0)}' — {why}"))
        for name in banned:
            if name and name.lower() in text.lower():
                out.append(("block", where, f"'{name}' — 노출 금지 이름(계정 설정 banned_names)"))

    lim = cfg["limits"]
    if len(script.get("title", "")) > lim["title"]:
        out.append(("warn", "title", f"제목 {len(script['title'])}자 — {lim['title']}자 이하 권장"))
    slides = script.get("slides", [])
    lo, hi = cfg["slide_count"]
    if not lo <= len(slides) <= hi:
        out.append(("warn", "slides", f"본문 카드 {len(slides)}장 — {lo}~{hi}장 권장"))
    for i, sl in enumerate(slides, 1):
        for k in ("head", "body"):
            if len(sl.get(k, "")) > lim[k]:
                out.append(("warn", f"slide{i}.{k}", f"{len(sl[k])}자 — {lim[k]}자 이하 권장"))

    srcs = script.get("sources", [])
    if not srcs:
        out.append(("block", "sources", "출처가 없습니다. 기관·매체명과 날짜를 넣으십시오."))
    for j, src in enumerate(srcs, 1):
        if not src.get("name"):
            out.append(("block", f"sources{j}", "출처 이름이 비었습니다."))
        if not DATE.match(src.get("date", "")):
            out.append(("block", f"sources{j}", "출처 날짜는 YYYY-MM-DD 형식으로 넣으십시오."))
    has_numbers = any(NUMBER.search(t) for w, t in _texts(script) if w not in ("caption", "hashtags"))
    strong = [s for s in srcs if not re.match(WEAK_SOURCES, s.get("name", "").strip(), re.I)]
    if has_numbers and srcs and not strong:
        out.append(("block", "sources", "숫자가 있는데 출처가 검색 트렌드·불명확한 출처뿐입니다."))

    return out


def has_block(results):
    return any(lv == "block" for lv, _, _ in results)


def format_results(results):
    if not results:
        return "검수 통과: 걸린 항목 없음"
    icon = {"block": "[수정필요]", "warn": "[확인]"}
    return "\n".join(f"{icon[lv]} {w}: {m}" for lv, w, m in results)
