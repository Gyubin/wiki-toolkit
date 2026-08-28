# wiki-toolkit

Markdown vault 하나를 개인 지식 베이스로 키우는 로컬 도구다. 브라우저 클립이나 코딩 세션
같은 원문을 받아서 출처가 달린 주장(claim) 단위로 쪼개고, 사람이 검토한 것만 wiki 페이지와
학습카드로 올린다. vault는 Obsidian으로 읽고, 구조화된 쓰기는 전부 이 repo의 코드가 한다.

이름과 달리 **여기에 에이전트는 없다.** 이 repo는 vault를 다루는 순수 로직(`core/`)과 그것을
MCP 도구 19개로 노출하는 껍데기까지다. 판단은 그 도구를 쥔 Claude Code가 하고, 각 작업의
절차는 `wiki_toolkit/prompts/*.md`에 적혀 있다.

## 핵심 아이디어

- **원문은 진실이 아니라 후보다.** 캡처된 글은 source로 저장되고, 하나의 판정이 통째로
  적용될 만큼 작은 claim으로 쪼개진다. claim은 항상 `unverified`로 태어난다.
- **`verified`로 가는 통로는 하나뿐이다.** `promote_claim`에 근거(`evidence_refs`)를 넘기는
  것이다. 사람 판단으로 올릴 때도 그 판단을 문장으로 적는다. 근거를 문장으로 못 적겠으면
  `attributed`, `opinion`, `accepted_for_now` 중 하나다.
- **claim마다 원문 인용을 붙인다.** claim 문장은 이미 다듬은 표현이므로, 검토할 때 대조할
  원문 구절을 `## 원문` 블록에 그대로 담아 둔다. 인용이 없으면 원문을 미묘하게 비튼 claim이
  검토를 그대로 통과한다.
- **긴 본문은 파일 경로로 넘긴다.** 원문을 도구 인자로 다시 타이핑하는 단계에서 글자가
  조용히 바뀐다. 그래서 `create_source`는 `content_path`를, `update_wiki_page`는
  `body_path`를 받는다.
- **쓰기마다 vault에 git 커밋이 남는다.** 무엇이 언제 바뀌었는지 히스토리로 되짚을 수 있다.
- **다음 할 일을 도구가 알려준다.** 쓰기 도구의 반환값 끝에 "다음: ..." 한 줄이 붙는다.
  파이프라인 단계를 사람이 외울 필요가 없다.

## 파이프라인

```
클립/세션        source 캡처      claim 추출         사람 검토/승격    wiki page          학습카드
           ->                ->               ->                ->                 ->
           create_source     create_claim     promote_claim     create_wiki_page   create_learning_item
```

각 단계가 사람의 다음 행동을 기다린다. 지금 어디까지 왔는지는 `vault_next_step` 도구가
계산해 준다.

## 시작하기

[uv](https://docs.astral.sh/uv/)와 Python 3.11 이상이 필요하다.

```bash
git clone https://github.com/Gyubin/wiki-toolkit.git
cd wiki-toolkit

# 1) vault 만들기 (이 repo 밖의 별도 디렉토리에)
uv run wiki init ~/wiki-vault

# 2) 검색 임베딩 키 설정
cp .env.example .env   # OPENAI_API_KEY를 채운다

# 3) Claude Code에 MCP 서버로 등록
claude mcp add wiki -- uv run --directory "$PWD" wiki mcp ~/wiki-vault
```

등록이 끝나면 Claude Code 안에서 `mcp__wiki__*` 도구 19개가 보인다. 브라우저에서 클립을
모으려면 [Obsidian Web Clipper 설정](docs/web-clipper-setup.md)을 따라 한다.

vault 경로는 어느 명령이든 같은 순서로 정한다: 명시한 인자 > `$WIKI_VAULT` > 현재 디렉토리.
`init`만 vault를 만들고, 나머지 명령은 `06_Metadata/`가 없는 디렉토리를 거부한다(exit 2).

## CLI

```bash
uv run wiki init [vault]             # 폴더 구조와 템플릿 생성 (유일하게 vault를 만드는 명령)
uv run wiki mcp [vault]              # 도구 19개를 stdio MCP 서버로 노출 (Claude Code 등록용)
uv run wiki lint [vault]             # 읽기 전용 위생 검사. error가 있으면 exit 1
uv run wiki search [vault] <질의>    # 하이브리드 검색 (BM25 + 임베딩)
```

## MCP 도구 19개

| 묶음 | 도구 | 하는 일 |
| --- | --- | --- |
| 수집 | `create_source` `triage_record` `update_source_raw` | 원문을 Inbox에 캡처하고 triage 결정(drop, keep-as-link, deep)을 기록한다 |
| claim | `create_claim` `find_similar_claim` `promote_claim` `set_claim_status` `update_claim_quote` `list_pending` | claim 생성(항상 unverified), 중복 확인, 상태 변경. `verified`는 `evidence_refs` 필수 |
| wiki | `create_wiki_page` `update_wiki_page` | 사람이 읽는 페이지 (`03_Resources/` 아래) |
| 학습 | `create_learning_item` `list_due_reviews` `record_review` | 학습카드 생성과 간격 반복 복습 |
| 코딩 세션 | `collect_git_session` `create_session_summary` `create_decision` | repo diff를 읽어 세션 요약과 ADR로 남긴다 (`01_Projects/<repo>/`, sensitivity=work) |
| 검색과 안내 | `search_wiki` `vault_next_step` | vault 전체 검색, 파이프라인의 다음 할 일 |

이미 들어간 것을 고칠 때는 파일을 손으로 고치지 말고 `update_source_raw`,
`update_claim_quote`, `update_wiki_page`를 쓴다. 손으로 고치면 스키마, ID 채번,
verified 게이트를 전부 우회하게 되는데, 이를 막아주는 코드는 없다. 규칙이지 코드가 아니다.

## vault 구조

vault는 이 repo 밖의 별도 디렉토리다(보통 비공개 git repo). `wiki init`이 만드는 구조는:

```
00_Inbox/        # 원문이 처음 떨어지는 곳 (browser-clips, chatgpt-gemini-clips, ...)
01_Projects/     # repo별 세션 요약과 ADR (sensitivity: work)
02_Areas/
03_Resources/    # 사람이 읽는 wiki page (Concepts, Patterns, Glossary, Comparisons, Misconceptions)
06_Metadata/     # 인덱스, 로그, 템플릿
10_Claims/       # 상태별 폴더: pending, verified, attributed, disputed, rejected, outdated
30_Learning/     # 학습카드 (flashcards, quizzes, exercises, skill-maps, weekly-synthesis)
```

claim 상태는 `unverified`에서 시작해 `verified`(근거 필수), `attributed`, `opinion`,
`partially_true`, `accepted_for_now`로 올라가거나 `disputed`, `outdated`, `deprecated`,
`rejected`로 내려간다. 스키마의 원본은 `wiki_toolkit/schema.py` 하나다.

## prompts/는 코드가 아니라 계약서다

`wiki_toolkit/prompts/*.md`는 코드가 읽지 않는다. Claude Code가 작업 전에 직접 읽는
절차서다. 자동으로 붙여주는 계층이 없으므로, 읽지 않으면 triage를 건너뛰거나 claim을 덜
쪼개는 식으로 조용히 어긋난다.

| 파일 | 언제 읽나 |
| --- | --- |
| `system.md` | vault 작업 전 공통 원칙 |
| `ingest.md` | 클립 하나를 source와 claim으로 쪼갤 때 |
| `verify.md` | pending claim을 검토하고 승격할 때 |
| `wiki-page.md` | wiki 페이지를 만들거나 고칠 때 |
| `answer.md` `learning.md` `wrap.md` `lint.md` | 질문 답변, 학습카드, 세션 마무리, 모순 감사 |

## 검색

`search_wiki`와 `wiki search`는 BM25(한글 2-gram)와 임베딩 검색을 RRF로 합친다. 임베딩은
기본이 OpenAI Embeddings API(`text-embedding-3-large`)라 `OPENAI_API_KEY`가 필요하다.

- `sensitivity: confidential` 문서의 본문은 API로 내보내지 않는다 (BM25로만 검색된다).
- 전부 로컬로 돌리려면 `WIKI_EMBED_PROVIDER=local` (fastembed, 첫 실행에 가중치 2.1GB 다운로드).
- 벡터는 디스크에 캐시되고 vault 내용이 바뀐 문서만 다시 임베딩한다.

설정값은 셸 환경변수가 우선이고, 없으면 repo 루트의 `.env`에서 채운다(`.env.example` 참조).
`WIKI_EMBED_MODEL`, `WIKI_EMBED_DIM`, `WIKI_OPENAI_BASE_URL`, `WIKI_EMBED_SEND_SENSITIVE`,
`WIKI_EMBED_CACHE`, `WIKI_ENV_FILE`도 받는다.

## 개발

```bash
uv run pytest        # 테스트
uv run ruff check    # lint
uv run pre-commit install --hook-type pre-commit --hook-type pre-push   # 커밋/푸시 훅
```

import는 `schema -> core -> tools -> __main__` 방향으로만 흐르고, `core/`는 LLM과 웹
의존성이 없는 순수 로직이다. 이 경계는 `tests/test_architecture.py`가 기계적으로 강제한다.

더 읽을 것:

- [ARCHITECTURE.md](ARCHITECTURE.md): 코드 지도와 설계 판단, 지운 것의 기록
- [AGENTS.md](AGENTS.md): 이 repo에서 작업하는 에이전트의 규칙
- `docs/superpowers/`: 변경 이력 (brainstorm, spec, ExecPlan)
