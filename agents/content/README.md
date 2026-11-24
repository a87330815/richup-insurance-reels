# 범용 콘텐츠 에이전트

**계정 하나 = 설정 파일 하나.** 같은 엔진(`contentagent/`)과 같은 업무지침서(`RUNBOOK.md`)로 어떤 인스타 정보 계정이든 돌립니다.

```
accounts/
  _defaults.json   모든 계정 공통 기본값(글꼴, 글자 수 제한, 카드 장수)
  _template.json   새 계정용 빈 양식
  richup.json      리치업지점 (@goodrich_richup) — 첫 적용
contentagent/      엔진: plan · prompt · check · render (카드 1080x1350, 릴스 1080x1920, caption.txt)
  presets.py       검수 규칙 묶음: finance_basic / insurance / recruiting
agents/content/
  RUNBOOK.md       예약 작업이 읽는 업무 순서(계정 공통)
  examples/        계정별 사실 메모·대본 예시
```

## 계정 파일에서 정하는 것
| 항목 | 뜻 |
|---|---|
| `handle`, `brand`, `colors` | 계정명, 카드에 찍히는 이름, 색 |
| `persona`, `audience`, `tone`, `writing_rules` | 누구에게 어떤 말투로, 무엇을 쓰지 말지(대본 지시문에 그대로 들어감) |
| `series_by_weekday` | 요일별 시리즈 이름과 방향. 빠진 요일은 휴무 |
| `topic_pool`, `sources_priority` | 주제 후보, 믿을 출처 순서 |
| `rule_presets`, `banned_names`, `compliance` | 자동 검수(block = 제작 중단, warn = 확인 표시) |
| `disclaimer`, `required_caption`, `default_hashtags`, `cta` | 카드·캡션에 자동으로 붙는 문구 |
| `schedule`, `delivery` | 실행 시각, 드라이브 납품 폴더·업무일지 폴더 id |
| `status` | `draft_only`(납품까지만) / `auto_post`(자동 게시, 아직 없음) |

## 새 계정 추가 (5분)
1. `python3 -m contentagent new <계정id>` → `accounts/<계정id>.json` 생성
2. 빈칸 채우기. 금융이면 `rule_presets` 에 `finance_basic`, 보험이면 `insurance` 추가
3. 드라이브 `AI회사_납품함` 아래 `<브랜드>_매일콘텐츠` 폴더를 만들고 id 를 `delivery.drive_folder_id` 에
4. `python3 -m unittest tests.test_contentagent` (모든 계정 설정을 자동 점검)
5. 예약 작업 하나 추가: 프롬프트의 `ACCOUNT=` 값만 바꿔서 복사

## 리치업지점 검수 요점
- `굿리치`·`goodrich` 이름이 제목·본문·캡션·해시태그 어디든 나오면 제작 중단
- 보장·지급 장담, 최저 보험료 같은 최상급 표현, 가입·해지·갈아타기 권유, 보험금 꼼수, 댓글로 병력·주민번호 받기 → 중단
- 리크루팅: 월 ○○만원 보장, 정착지원금 금액 장담 → 중단
- 특정 보험사명·상품·보험료 예시, 실제 고객 사례 → 확인 표시
- 캡션에 승환계약 불이익 안내 문구, 마지막 카드에 "특정 상품 권유 아님" 문구 자동 삽입

## 이 저장소의 기존 파이프라인과의 관계
루트의 `collect.py`·`scriptgen.py`·`publish*.py` 와 GitHub Actions 워크플로는 그대로 둡니다(이번 변경에서 건드리지 않음).
새 에이전트는 그 코드를 쓰지 않고, 결과를 저장소가 아니라 드라이브로만 납품합니다.
