"""사실 메모 → 대본(script.json).

세 가지 방법:
1) 예약 에이전트(기본): `prompt` 가 출력한 지시문대로 Claude 가 직접 script.json 을 씀 (API 키 불필요)
2) 사람이: 지시문을 ChatGPT 등에 붙여 넣고 답을 `import`
3) API로: `draft` 명령(OPENAI_API_KEY, 모델은 계정 설정 openai_model)

사실 메모에는 원문 기사 전체가 아니라 '확인한 사실 + 출처(기관·날짜·주소)'를 적습니다.
기사 문장을 그대로 옮기지 않도록 지시문에서 다시 쓰기를 요구합니다.
"""
import json, os, urllib.request, urllib.error

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["series", "title", "hook", "photo", "photo_kr", "slides", "summary", "caption", "hashtags", "sources"],
    "properties": {
        "series": {"type": "string"},
        "title": {"type": "string"},
        "hook": {"type": "string"},
        "photo": {"type": "string"},
        "photo_kr": {"type": "string"},
        "slides": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                   "required": ["head", "body", "photo", "photo_kr"], "properties": {"head": {"type": "string"}, "body": {"type": "string"},
                                                                 "photo": {"type": "string"}, "photo_kr": {"type": "string"}}}},
        "summary": {"type": "string"},
        "caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "sources": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                    "required": ["name", "date", "url"],
                    "properties": {"name": {"type": "string"}, "date": {"type": "string"}, "url": {"type": "string"}}}},
    },
}

BASE_RULES = """공통 규칙(어기면 안 됨):
- 사실 메모에 있는 숫자·사실만 씁니다. 메모에 없는 숫자, 날짜, 전망은 만들지 않습니다.
- 기사 문장을 그대로 옮기지 말고 쉬운 말로 새로 씁니다.
- sources 에는 메모에 적힌 출처만 넣고, date 는 YYYY-MM-DD.
형식:
- title {title}자 이내, 첫 카드에서 궁금하게 만드는 질문형 또는 숫자형.
- hook 은 title 아래 한두 줄.
- slides {lo}~{hi}장. head {head}자 이내, body {body}자 이내. 한 장에 한 가지 내용.
- summary 는 한 줄 정리(40자 이내).
- caption 은 3~5줄 요약 + 질문 한 줄(댓글 유도). 해시태그는 hashtags 에만.
- hashtags 5~8개, 주제에 맞는 한국어 태그.
- photo_kr 는 네이버 이미지 검색용 한국어 검색어(2~4단어, 예: "병원 영수증 서류"), photo 는 같은 뜻의 영어 검색어
  (예: "hospital receipt desk", 네이버에서 못 찾을 때 씀). 표지는 최상위 photo·photo_kr, 장마다 slides[].photo·photo_kr.
  사람 얼굴 클로즈업·특정 회사 로고·뉴스 장면이 나올 검색어는 피하고, 사물·공간·분위기로 고릅니다.
- 카드 글이 그대로 음성(TTS)으로 읽힙니다. 괄호·기호·영문 약어를 줄이고 소리 내 읽기 쉬운 문장으로 씁니다."""


def build_prompt(topic, facts, cfg, series=None):
    lim, (lo, hi) = cfg["limits"], cfg["slide_count"]
    own = "\n".join(f"- {r}" for r in cfg.get("writing_rules", []))
    series = series or cfg["brand"]
    return (f"너는 {cfg['persona']} '{cfg['brand']}'({cfg['handle']})의 카드뉴스 작가야.\n"
            f"말투: {cfg['tone']}.\n독자: {cfg['audience']}.\n\n"
            f"주제: {topic}\n시리즈: {series}\n\n사실 메모(이것만 근거로 씀):\n{facts.strip()}\n\n"
            f"이 계정 규칙(어기면 안 됨):\n{own}\n\n"
            + BASE_RULES.format(title=lim["title"], head=lim["head"], body=lim["body"], lo=lo, hi=hi)
            + "\n\n아래 JSON 형식으로만 답해(설명 붙이지 말 것):\n"
            + json.dumps({"series": series, "title": "", "hook": "", "photo": "", "photo_kr": "", "slides": [{"head": "", "body": "", "photo": "", "photo_kr": ""}],
                          "summary": "", "caption": "", "hashtags": ["#"],
                          "sources": [{"name": "", "date": "YYYY-MM-DD", "url": ""}]}, ensure_ascii=False, indent=1))


def draft_openai(prompt, cfg):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("OPENAI_API_KEY 가 없습니다. 키 없이 하려면 `prompt` 명령으로 ChatGPT에 붙여 넣으십시오.")
    body = {"model": cfg.get("openai_model", "gpt-5-mini"), "input": prompt,
            "text": {"format": {"type": "json_schema", "name": "cardnews", "schema": SCHEMA, "strict": True}}}
    req = urllib.request.Request("https://api.openai.com/v1/responses", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            res = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"OpenAI HTTP {e.code}: {e.read()[:300]!r}")
    for item in res.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    return json.loads(c["text"])
    raise SystemExit("응답에서 대본을 찾지 못했습니다.")


def parse_pasted(text):
    """ChatGPT 답변에서 JSON 부분만 꺼냅니다(```json 감싸기 허용)."""
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e < 0:
        raise SystemExit("붙여 넣은 내용에서 JSON을 찾지 못했습니다.")
    return json.loads(text[s:e + 1])
