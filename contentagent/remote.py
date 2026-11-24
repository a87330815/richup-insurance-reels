"""클라우드 예약 작업 ↔ GitHub Actions 렌더 연결.

클라우드 작업환경은 프록시가 TTS·사진 서버를 막습니다. 그래서
 1) `remote <script.json>` 이 workflow_dispatch 입력값(JSON)을 출력하고,
 2) 에이전트가 GitHub 도구(actions_run_trigger, run_workflow)로 contentagent_render.yml 을 main 에서 실행하면
    러너가 Secrets(ELEVENLABS_API_KEY·ELEVENLABS_VOICE_ID·UNSPLASH_ACCESS_KEY)로 사진+음성 릴스를 만들어
    contentagent-out 브랜치의 <계정>/<결과폴더>/ 에 올립니다.
 3) `fetch <결과폴더> --wait 900` 이 그 결과를 git 으로 받아 로컬 결과폴더를 덮어씁니다.
결과물은 main 에 커밋하지 않습니다(contentagent-out 은 결과 전용 브랜치).
"""
import base64, json, shutil, subprocess, time
from pathlib import Path

BRANCH = "contentagent-out"
WORKFLOW = "contentagent_render.yml"


def request(account, script_path):
    script_path = Path(script_path)
    b64 = base64.b64encode(script_path.read_bytes()).decode()
    if len(b64) > 60000:
        raise SystemExit("대본이 너무 깁니다(입력 한도 65,535자).")
    return json.dumps({"workflow_id": WORKFLOW, "ref": "main",
                       "inputs": {"account": account, "folder": script_path.parent.name, "script_b64": b64}},
                      ensure_ascii=False, indent=1)


def _git(*a, cwd="."):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)


def fetch(account, outdir, wait=0):
    outdir = Path(outdir)
    rel = f"{account}/{outdir.name}"
    deadline = time.time() + wait
    while True:
        r = _git("fetch", "-q", "--depth", "1", "origin", f"+refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}")
        if r.returncode == 0:
            st = _git("show", f"origin/{BRANCH}:{rel}/status.json")
            if st.returncode == 0:
                status = json.loads(st.stdout)
                break
        if time.time() >= deadline:
            print(f"아직 결과가 없습니다: {BRANCH}:{rel}/status.json")
            return False
        time.sleep(20)
    print("Actions 결과:", json.dumps(status, ensure_ascii=False))
    if not status.get("ok"):
        return False
    tmp = outdir / "_remote"
    shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir(parents=True)
    # -z: 한글 경로가 따옴표·8진수로 바뀌지 않게
    ls = [n for n in _git("ls-tree", "-r", "-z", "--name-only", f"origin/{BRANCH}", f"{rel}/").stdout.split("\0") if n]
    for name in ls:
        dest = outdir / name[len(rel) + 1:]
        dest.parent.mkdir(parents=True, exist_ok=True)
        blob = subprocess.run(["git", "show", f"origin/{BRANCH}:{name}"], capture_output=True).stdout
        dest.write_bytes(blob)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"받음: {len(ls)}개 파일 → {outdir}")
    return True
