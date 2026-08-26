# 원문 그대로 담기 (Spec)

> 상태: 구현 중 (2026-08-27)

## 문제

**Raw 본문과 claim 인용문이 캡처 원본과 달라도 아무도 모른다.**

2026-08-27에 Web Clipper 클립 4개(합계 119KB)를 인제스트했다. 절차는 다 지켰다. 클립을
전체로 읽었고, source를 만들고, triage를 기록하고, claim 72개를 만들면서 `find_similar_claim`을
돌렸고, 끝나고 파일에서 세서 계약을 확인했다. 그 확인은 통과했다.

그런데 원본 바이트와 대조하니 달랐다.

- 곱슬따옴표 18개를 전부 곧은 따옴표로 바꿔 적었다 (`harness’s` -> `harness's`). 4개 source 전부.
- source-20260827-003에서 단어를 바꿨다. 원문 `푸시할 뻔함`을 `푸시할 뻔했음`으로 적었다.
- 결과적으로 claim 72개 중 6개의 인용문이 원본에 없는 문자열이 됐다.

원인은 절차 위반이 아니라 **도구 인터페이스**다. `create_source`는 `content`를 문자열로만
받는다. 그래서 74KB짜리 클립을 인제스트하려면 모델이 74KB를 도구 인자로 다시 타이핑해야
한다. 그 과정에서 조용히 뒤틀린다. 사람은 물론이고 모델 자신도 눈치채지 못한다.

끝나고 돌린 확인이 통과한 것도 문제였다. 그 확인은 "인용문 블록이 있는가"였지
"원본과 같은가"가 아니었다. 계약(`prompts/ingest.md`)은 `copied verbatim`을 요구하는데
검사는 존재 여부만 봤다.

## 결정

세 가지를 한다. 하나는 원인, 하나는 탐지, 하나는 복구다.

### 1. 원인: 도구가 파일 경로를 받는다

`create_source`와 새 `update_source_raw`가 `content_path`를 받는다. 파일을 그대로 읽어
쓰므로 모델이 본문을 다시 타이핑하지 않는다. 타이핑 단계가 없으면 드리프트도 없다.

- `content`와 `content_path` 중 **정확히 하나**만 받는다. 둘 다 없거나 둘 다 있으면 거부한다.
- 경로 해석과 파일 읽기는 `tools.py`(L2)가 한다. `core/`는 문자열만 다루고 순수하게 남는다
  (AGENTS.md §4).

`create_claim`의 `quote`는 그대로 문자열이다. 인용문은 몇 문장짜리라 타이핑이 정상이고,
아래 2번이 틀린 것을 잡아준다.

### 2. 탐지: lint 규칙 `quote_not_in_source`

claim의 `## 원문` 블록이 그 claim의 `source_refs`가 가리키는 source의 Raw 본문에
문자열로 없으면 warning으로 보고한다.

- blockquote(`> `)를 벗겨서 비교한다.
- 공백만 접어서 비교한다 (줄바꿈 위치는 판정 대상이 아니다).
- `(...)`는 인용 생략 표시로 인정한다. 그 기준으로 쪼개 조각별로 찾는다.
- source가 vault에 없으면 건너뛴다 (`dangling_ref`가 이미 보고한다).

`lint`는 report-only이고 해결은 사람 몫이라는 기존 성격을 그대로 따른다 (AGENTS.md §3).

**이 규칙의 사정거리를 정확히 적어둔다.** 인용문을 *저장된 source*와 비교하므로, 인용문과
source가 **같은 방식으로** 틀렸으면 조용하다. 2026-08-27 사고가 정확히 그랬다. 곱슬따옴표를
source 본문과 인용문 양쪽에서 똑같이 평평하게 적었기 때문에, 이 규칙을 구현해서 실제 vault에
걸어보니 0건이 나왔다. 그 사고를 잡은 것은 lint가 아니라 ingest 전에 커밋해 둔 원본 클립
바이트와의 대조였다.

그래서 두 구멍을 서로 다른 것으로 막는다.

| 어디서 어긋나나 | 무엇이 막나 |
| --- | --- |
| 원본 캡처 -> source Raw 본문 | `content_path` (타이핑 단계가 없으면 어긋날 데가 없다) |
| source Raw 본문 -> claim 인용문 | `quote_not_in_source` |

source를 원본 바이트로 되돌리고 나면 평평해진 인용문들이 그 source와 어긋나므로, 그때는
이 규칙이 고쳐야 할 인용문을 정확히 짚어준다.

### 3. 복구: `update_source_raw`, `update_claim_quote`

이미 들어간 4개 source와 6개 claim을 고칠 통로가 필요하다. 손으로 고치면 스키마와 로그를
우회하므로 도구로 만든다.

- `update_source_raw(source_id, content|content_path, reason)`: `## Raw` 본문만 교체한다.
  frontmatter는 안 건드린다.
- `update_claim_quote(claim_id, quote, reason)`: `## 원문` 블록만 교체한다. **claim 문장과
  status는 안 건드린다.** claim 문장을 바꾸는 것은 주장하는 내용을 바꾸는 일이라 인용문
  수정 도구에 얹으면 안 된다.
- 둘 다 `reason`이 필수다. 캡처를 사후에 바꾸는 일이므로 로그에 왜가 없으면 나중에
  이 vault를 믿을 수 없다. 로그에는 바뀐 글자 수도 같이 남긴다.
- 내용이 같으면 (교체할 게 없으면) 거부한다. 무의미한 로그를 남기지 않는다.

## 왜 범용 문자열 치환 도구가 아닌가

처음에는 `update_source_raw(old, new, expected_count)` 형태를 생각했다. 실제 데이터로
치환 목록을 뽑아보고 접었다.

`r'`는 본문에 6번 나오는데 그중 코드 블록 안의 것은 원본도 곧은 따옴표라 바꾸면 안 된다.
유일하게 걸리도록 좌우로 넓히면 `old`가 `"t'"`, `"nt'"`, `"s'"` 같은 모양이 된다. 유일하긴
하지만 사람이 감사할 수 없고, 그걸 도구 인자로 옮겨 적다가 또 틀릴 수 있다. 원문을 다시
타이핑해서 생긴 문제를 원문 조각을 다시 타이핑해서 고치는 셈이다.

파일 경로를 받으면 그 문제가 통째로 사라진다.

## 검증

- `tests/test_sources.py`: `update_source_raw`가 본문만 바꾸고 frontmatter를 보존하는지,
  `reason` 없이 거부하는지, 같은 내용이면 거부하는지, 로그를 남기는지.
- `tests/test_claims.py`: `update_claim_quote`가 `## 원문`만 바꾸고 claim 문장과 status를
  보존하는지, 인용문이 없던 claim에 붙일 수 있는지.
- `tests/test_lint.py`: 인용문이 source에 있으면 조용하고, 비틀면 `quote_not_in_source`가
  뜨고, `(...)` 생략을 인정하고, source가 없으면 건너뛰는지.
- `tests/test_tools.py`: `content_path`로 만든 source의 본문이 파일과 같은지,
  `content`와 `content_path`를 둘 다 주면 거부하는지, 새 도구 2개가 이름 목록에 있는지.
