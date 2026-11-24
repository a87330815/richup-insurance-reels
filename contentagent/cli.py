"""사용법 (저장소 최상위에서). 모든 명령은 --account <계정id> 가 필요합니다(accounts/<id>.json).

  python -m contentagent accounts                                 계정 목록
  python -m contentagent new <계정id>                              새 계정 파일 만들기(_template.json 복사)
  python -m contentagent --account richup plan                    오늘(KST) 시리즈·주제 후보·납품 폴더
  python -m contentagent --account richup prompt "<주제>" facts.txt   대본 지시문 출력 (API 불필요)
  python -m contentagent --account richup import 답변.txt <결과폴더>     붙여 넣은 답변 → script.json
  python -m contentagent --account richup draft "<주제>" facts.txt <결과폴더>   OpenAI API로 대본
  python -m contentagent --account richup check <script.json>      검수만 (block 있으면 종료코드 1)
  python -m contentagent --account richup render <script.json> [--no-reel] [--photos] [--voice] [--require-voice]
                                                                  검수 → 카드·릴스·캡션 (사진·음성은 인터넷 되는 곳에서)
  python -m contentagent --account richup remote <script.json>     GitHub Actions 렌더(사진+음성) 요청 내용 출력
  python -m contentagent --account richup fetch <결과폴더> [--wait 900]   Actions 결과(contentagent-out 브랜치) 받아오기

공통 옵션: --series "<시리즈 이름>" (없으면 오늘 요일 시리즈)
결과폴더 예: contentagent/out/richup/2026-11-25_실손청구
"""
import json, sys
from pathlib import Path
from . import accounts, compliance, draft, render


def _opt(args, name, default=None):
    if name in args:
        i = args.index(name); v = args[i + 1]; del args[i:i + 2]; return v
    return default


def _flag(args, name):
    if name in args:
        args.remove(name); return True
    return False


def _save_script(script, outdir, cfg):
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    f = out / "script.json"
    f.write_text(json.dumps(script, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"대본 저장: {f}\n{compliance.format_results(compliance.check(script, cfg))}")
    return f


def _plan_text(cfg):
    p = accounts.plan(cfg)
    lines = [f"계정: {cfg['brand']} ({cfg['handle']})  상태: {cfg.get('status', '')}",
             f"오늘: {p['date']} ({p['weekday']})"]
    if not p["series"]:
        lines.append("오늘은 쉬는 날입니다(series_by_weekday 에 없음). 만들지 않습니다.")
    else:
        s = p["series"]
        lines += [f"시리즈: {s['name']}", f"방향: {s['brief']}"]
    lines.append("주제 후보 풀: " + " / ".join(cfg.get("topic_pool", [])))
    lines.append("출처 우선순위: " + " > ".join(cfg.get("sources_priority", [])))
    dl = cfg["delivery"]
    lines.append(f"납품: 드라이브 '{dl.get('drive_folder_name')}' id {dl.get('drive_folder_id') or '(미설정)'} / "
                 f"업무일지 id {dl.get('log_folder_id') or '(미설정)'}")
    return "\n".join(lines)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    account = _opt(args, "--account")
    series = _opt(args, "--series")
    no_reel = _flag(args, "--no-reel")
    photos = _flag(args, "--photos")
    voice = _flag(args, "--voice")
    require_voice = _flag(args, "--require-voice")
    wait = int(_opt(args, "--wait", "0"))
    if not args:
        sys.exit(__doc__)
    cmd, rest = args[0], args[1:]
    if cmd == "accounts":
        for a in accounts.list_ids():
            c = accounts.load(a)
            print(f"{a}\t{c['brand']}\t{c['handle']}\t{c.get('status', '')}")
        return
    if cmd == "new" and len(rest) == 1:
        print(f"만들었습니다: {accounts.new(rest[0])}  — 비어 있는 항목을 채우십시오.")
        return
    if not account:
        sys.exit("--account <계정id> 가 필요합니다.\n\n" + __doc__)
    cfg = accounts.load(account)
    if not series:
        p = accounts.plan(cfg)
        series = p["series"]["name"] if p["series"] else None
    if cmd == "plan":
        print(_plan_text(cfg))
    elif cmd == "prompt" and len(rest) == 2:
        print(draft.build_prompt(rest[0], Path(rest[1]).read_text(encoding="utf-8"), cfg, series))
    elif cmd == "import" and len(rest) == 2:
        _save_script(draft.parse_pasted(Path(rest[0]).read_text(encoding="utf-8")), rest[1], cfg)
    elif cmd == "draft" and len(rest) == 3:
        pr = draft.build_prompt(rest[0], Path(rest[1]).read_text(encoding="utf-8"), cfg, series)
        _save_script(draft.draft_openai(pr, cfg), rest[2], cfg)
    elif cmd == "check" and len(rest) == 1:
        res = compliance.check(json.loads(Path(rest[0]).read_text(encoding="utf-8")), cfg)
        print(compliance.format_results(res))
        sys.exit(1 if compliance.has_block(res) else 0)
    elif cmd == "render" and len(rest) == 1:
        sf = Path(rest[0])
        script = json.loads(sf.read_text(encoding="utf-8"))
        res = compliance.check(script, cfg)
        print(compliance.format_results(res))
        if compliance.has_block(res):
            sys.exit("[수정필요] 항목을 고친 뒤 다시 실행하십시오. 렌더링하지 않았습니다.")
        made = render.render(script, cfg, sf.parent, reel=not no_reel, photos=photos,
                             voice=voice or require_voice, require_voice=require_voice)
        print("만든 파일:\n" + "\n".join(f"  {m}" for m in made))
        if not no_reel and not any(str(m).endswith(".mp4") for m in made):
            print("ffmpeg 이 없어 릴스 MP4는 건너뛰었습니다(reel_frames/ 의 이미지는 있음).")
    elif cmd == "remote" and len(rest) == 1:
        from . import remote
        print(remote.request(account, Path(rest[0])))
    elif cmd == "fetch" and len(rest) == 1:
        from . import remote
        sys.exit(0 if remote.fetch(account, Path(rest[0]), wait) else 1)
    else:
        sys.exit(__doc__)
