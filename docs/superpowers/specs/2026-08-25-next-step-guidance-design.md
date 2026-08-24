# 파이프라인 다음 단계 안내 (Spec)

> 상태: 구현 완료 (2026-08-25)

## 문제

파이프라인이 `클립 -> ingest -> 승인 -> wiki page -> 학습카드` 5단계인데, 각 단계가 사람의
다음 행동을 기다린 채 멈춘다. 사용자가 단계를 외우고 있어야 진행된다. 실제로 2026-08-25에
ingest로 claim 18개를 만든 뒤 "다음에 뭘 해야 하는지 까먹을 것 같다"는 요청이 나왔다.

## 결정

안내를 프롬프트가 아니라 **도구 반환값(데이터 경로)** 에 둔다. 프롬프트에 두면 Claude Code,
웹앱, SDK 에이전트마다 따로 관리해야 하고 모델이 무시할 수 있다.

- `core/pipeline.py` (L1, 순수): `vault_state(vault, today)`와 `next_step(vault, today)`.
- 우선순위는 앞 단계부터 하나만: ingest 대기 클립 > pending claim > wiki page에 안 실린
  verified claim > 복습 도래. 앞이 밀려 있으면 뒤는 말하지 않는다.
- `tools.py`의 `_done`(모든 쓰기 도구)과 `list_pending`이 반환값 끝에 그 한 줄을 붙인다.
- 새 도구 `vault_next_step`(17번째): 각 단계 대기 개수와 다음 한 가지를 함께 보고.
- `CLAUDE.md`에 "그 줄이 오면 답변에 그대로 전달한다"를 적어 모델 쪽 누락을 막는다.

## 계산 방식

파일명이 곧 id라서 claim 본문을 파싱하지 않는다.

- pending / verified: `10_Claims/{pending,verified}/claim-*.md`의 stem 집합.
- wiki page에 안 실린 verified: `verified stem 집합 - (03_Resources 페이지들의 claim_refs 합집합)`.
  파싱은 `03_Resources`만 한다.
- ingest 대기: `00_Inbox` 아래 frontmatter에 `id`가 없는 md.
- 복습 도래: `learning.list_due_reviews`.

## 부수 변경

`build_wiki_server`를 `build_wiki_tools`(도구 리스트) + `build_wiki_server`(MCP 래핑)로 쪼갰다.
SDK의 `Server` 객체에는 핸들러를 꺼낼 공개 경로가 없어서(`_tool_handlers` 없음, 실측 확인)
도구 반환값을 테스트할 방법이 없었다.

## 검증

- `tests/test_pipeline.py` 7개: 빈 vault, 우선순위(앞 단계가 뒤를 가림), 각 단계 전환,
  wiki page 생성이 verified를 해소하는지.
- `tests/test_tools.py` 4개: 실제 도구 핸들러를 불러 반환 문자열에 안내가 붙는지.
  (처음 쓴 테스트는 SDK 내부 속성이 없어 조용히 약한 분기로 빠졌다. 반환값 표본을 눈으로
  확인하고 나서 핸들러 직접 호출로 고쳤다.)
- 전체 173개 통과, ruff clean.
