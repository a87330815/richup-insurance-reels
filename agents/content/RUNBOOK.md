# 콘텐츠 에이전트 업무지침서 (모든 계정 공통)

예약 작업이 `ACCOUNT=<계정id>` 를 주고 이 문서를 읽게 합니다. 계정마다 다른 것은 **전부** `accounts/<계정id>.json` 에 있습니다.
이 문서와 엔진 코드(`contentagent/`)는 계정이 늘어도 고치지 않습니다. 사람 확인 없이 끝까지 진행하고, 막히면 업무일지에 이유를 남깁니다.

## 0. 준비
- 저장소 최상위에서 `pip install pillow` (ffmpeg 이 있으면 릴스 MP4까지 만듭니다).
- `python3 -m contentagent --account $ACCOUNT plan` 을 실행해 오늘(KST) 시리즈, 주제 후보, 출처 우선순위, 납품 폴더 id 를 확인합니다.
  "쉬는 날"이면 업무일지에 `휴무`만 남기고 끝냅니다.
- 계정 파일의 `writing_rules`, `rule_presets`, `banned_names`, `status` 를 읽습니다. `status` 가 `draft_only` 면 게시하지 않습니다(지금 모든 계정).

## 1. 지난 주제 확인
드라이브 납품 폴더(`delivery.drive_folder_id`)의 하위 폴더 이름(`YYYY-MM-DD_주제`)을 보고 최근 14일 주제와 겹치지 않게 합니다.

## 2. 주제 고르기
오늘 시리즈의 `brief` 에 맞게, `topic_pool` 과 최근 3일 공식 자료를 함께 보고 1개를 고릅니다.
WebSearch 로 `sources_priority` 순서대로 찾습니다. 언론 기사는 사실 확인용이며 출처에는 원 자료 기관을 적습니다.
구글 뉴스 RSS·구글 트렌드는 출처로 쓰지 않습니다.

## 3. 사실 메모
고른 자료를 WebFetch(없으면 web-fetch 에이전트)로 읽고 `contentagent/out/$ACCOUNT/YYYY-MM-DD_주제/facts.txt` 에
숫자·사실·출처(기관, 날짜, 주소)만 적습니다. 공공누리 유형을 알면 적습니다. 예: `agents/content/examples/richup/facts.txt`

## 4. 대본
`python3 -m contentagent --account $ACCOUNT prompt "주제" <facts.txt>` 가 출력하는 지시문(계정 규칙 포함)과 JSON 형식 그대로,
**직접** 같은 폴더에 `script.json` 을 씁니다(API 호출 없음). 예: `agents/content/examples/richup/script.json`

## 5. 검수·제작
`python3 -m contentagent --account $ACCOUNT render <폴더>/script.json`
- `[수정필요]` 가 나오면 고쳐서 다시 실행합니다. 세 번 고쳐도 안 되면 주제를 바꿉니다.
- `[확인]` 은 만들되 업무일지에 그대로 옮겨 적습니다.
- `cards/01.png` 와 마지막 카드를 열어 글자 깨짐·잘림을 눈으로 확인합니다.
- 여기서 나온 릴스는 **무음·단색 배경 예비본**입니다(클라우드는 TTS·사진 서버가 막혀 있음).

## 5-1. 사진 + 음성 릴스 (GitHub Actions)
배경 사진(네이버 이미지 검색 → Unsplash → Openverse)과 TTS 음성(ElevenLabs, 실패 시 edge-tts)은 저장소 Secrets 를 쓰는 Actions 에서 만듭니다.
1. `python3 -m contentagent --account $ACCOUNT remote <폴더>/script.json` → 출력된 JSON 그대로
   GitHub 도구 `actions_run_trigger`(method `run_workflow`, owner `a87330815`, repo `richup-insurance-reels`,
   workflow_id `contentagent_render.yml`, ref `main`, inputs 는 출력의 inputs)로 실행합니다.
2. `python3 -m contentagent --account $ACCOUNT fetch <폴더> --wait 540` (Bash timeout 600000 으로, 보통 3~5분).
   결과가 아직 없다고 나오면 한 번 더 실행합니다(합계 최대 약 18분). 같은 폴더 이름을 다시 렌더할 때는
   이전 결과가 먼저 보일 수 있으니 status.json 의 run_id 가 바뀌었는지 확인합니다.
   성공하면 `cards/`, `reel.mp4`, `caption.txt` 가 사진·음성 들어간 본으로 바뀝니다.
3. 실패하거나 15분 안에 안 오면 5번의 예비본을 납품하고, 업무일지에 `음성 실패: <status.json 의 notes>` 를 적습니다.
사진은 대본의 `photo_kr`(한국어, 네이버)을 먼저 쓰고, 못 받으면 `photo`(영문)·계정 파일 `photo_fallback` 순서입니다. `photo_kr` 이 없으면 카드 제목으로 네이버를 검색합니다. 보험사 이름·로고가 보이는 결과는 자동으로 뺍니다. 사진 출처는 `photos/credits.json`.

## 6. 납품
`delivery.drive_folder_id` 아래 `YYYY-MM-DD_주제` 폴더를 만들고 `reel.mp4`, `caption.txt`, `script.json`, `cards/*.png` 를 올립니다
(create_file, base64Content 에 `sha256:<해시>:<절대경로>` 파일 참조). 드라이브 도구가 없으면 `/mnt/project-files/<브랜드>-카드뉴스/` 에 복사합니다.

## 7. 업무일지
`delivery.log_folder_id` 에 `YYYY-MM-DD <브랜드>` 텍스트 파일: 시리즈, 주제, 출처, 검수 결과([확인] 항목 포함), 드라이브 폴더 주소, 막힌 점.
경영실장 에이전트가 이 일지를 읽어 대표 브리핑에 올립니다.

## 8. 끝 보고
한 줄: `<브랜드> | 시리즈 | 주제 | 드라이브 폴더 주소`. 실패하면 어느 단계에서 왜 막혔는지.

## 금지 (모든 계정)
- 메모에 없는 숫자, 기사 문장 그대로 옮기기, 출처 사진·그래픽 사용.
- 인스타·페이스북·유튜브·틱톡에 직접 게시(`status` 가 `auto_post` 가 되기 전까지). 이 저장소의 기존 게시 워크플로 실행.
- 저장소 main 에 결과물 커밋(드라이브로만 납품). Actions 가 쓰는 `contentagent-out` 브랜치는 예외. 다른 계정의 저장소·토큰 사용.
