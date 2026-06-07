# Personal AI Wiki — Agent App 설계 (Spec)

> 상태: 합의 완료(brainstorming), 구현 계획(writing-plans) 대기
> 날짜: 2026-06-07
> 관련 설계: `personal-ai-wiki-learning-system-design.md` (지식 시스템 원리/스키마의 단일 출처)

## Context

`personal-ai-wiki-learning-system-design.md`는 raw 정보를 검증 가능한 지식·학습 자산으로
바꾸는 **개인 지식 시스템의 원리·스키마·정책**을 정의한다. 그러나 그건 "무엇을/왜"이고,
실제로 **그걸 돌리는 소프트웨어**는 없었다. 이 spec은 그 시스템을 **Claude Agent SDK(Python)
기반 대화형 에이전트 + 로컬 웹앱**으로 구현하기 위한 설계다.

해결하려는 구체적 문제:
- Obsidian은 vault 파일을 **읽고/링크하고/그래프로 보는** 도구일 뿐, 파이프라인(claim 추출·검증·승격·복습)을
  **구동·조작**하지 못한다. → 에이전트 + 워크플로우 UI가 별도로 필요하다.
- 원리 문서의 무결성(claim 스키마, status enum, index/log 일관성)을 **코드로 강제**해야 실제로 지켜진다.

의도한 결과: vault 폴더 하나를 두고 → 웹앱에서 자연어로 ingest/verify/answer/learning을 수행하고,
검증·복습은 버튼으로 처리하며, Obsidian으로 같은 vault를 읽는다.

## Goals (v1)

1. 개인 지식 epistemic 루프: **Ingest → Verify → Answer**, 그리고 **Learning(카드/복습)**.
2. 로컬 웹앱 인터페이스: Chat / Capture / Verify 큐 / Review 큐.
3. 캡처: 웹앱 빠른 캡처(붙여넣기/드롭/URL 페치) + Obsidian Web Clipper 연동.
4. 무결성: claim 스키마·status·ID·index/log를 결정론적 코드로 강제. 검증/sensitivity 게이트.

## Non-goals (v1 — 이후로 미룸)

- `wrap-feature`(코딩 세션 → project wiki/ADR) — work-vault sensitivity(A3) 복잡도 때문에 phase 2.
- `wiki-lint` 자동화, BM25/semantic 검색, 폴더 watcher, 클립보드 워처.
- 멀티유저, 인증, 원격 배포. (단일 사용자 로컬 전용)
- 브라우저 확장 자체 제작(Web Clipper로 대체).

## 기술 스택

| 영역 | 선택 |
|---|---|
| 패키지/실행 | `uv` + `pyproject.toml` (`uv run wiki`) |
| 에이전트 | `claude-agent-sdk` (런타임에 Claude Code CLI 필요), 모델 `claude-opus-4-8` |
| 웹 백엔드 | FastAPI + SSE(채팅 스트리밍) |
| 프론트 | 무빌드 정적 HTML/CSS/JS + HTMX/SSE (Node 빌드 toolchain 없음) |
| 저장소 | 마크다운 vault = git repo |
| 뷰어(병행) | Obsidian (우리가 만들지 않음) |

> SDK 사실(확인됨): `ClaudeSDKClient(options).query()/receive_response()`,
> `ClaudeAgentOptions(system_prompt, model, cwd, allowed_tools, permission_mode, mcp_servers, agents, hooks, can_use_tool, ...)`,
> `@tool(name, desc, input_schema)` + `create_sdk_mcp_server(name, version, tools)` → `mcp_servers={"wiki": server}`,
> 도구명 `mcp__wiki__<tool>`, `AgentDefinition(description, prompt, tools, disallowedTools, model, permissionMode, ...)` (camelCase),
> `permission_mode ∈ {default, acceptEdits, plan, dontAsk, bypassPermissions}`,
> `can_use_tool(tool_name, input, ctx) -> PermissionResultAllow|Deny`.

## 아키텍처

같은 vault 디스크를 공유하는 두 표면:

```
┌─────────────────────────────┐        ┌──────────────────────┐
│  FastAPI 백엔드 (wiki_agent)  │        │  Obsidian (읽기/그래프)│
│  - 웹 UI 서빙                 │  share │  같은 vault 폴더 열람   │
│  - ClaudeSDKClient 세션 래핑  │◄──────►│                       │
│  - 무결성 도구(순수 함수)      │  vault └──────────────────────┘
└──────────┬──────────────────┘  files
           │ uses
   ┌───────▼─────────┐   ┌──────────────────┐
   │ in-proc MCP      │   │ subagents         │
   │ server "wiki"    │   │ ingest/verify/    │
   │ (@tool wrappers) │   │ answer/learning   │
   └──────────────────┘   └──────────────────┘
```

### 핵심 패턴: 도구 로직을 한 번 쓰고 두 번 감싼다
무결성 작업 로직은 `wiki_agent/core/`의 **순수 파이썬 함수**로 둔다. 두 경로가 같은 함수를 호출:
- **에이전트 경로**: `@tool` 래퍼 → MCP 서버 → 채팅에서 추론 흐름이 호출.
- **UI 버튼 경로**: FastAPI 라우트가 같은 함수를 **직접** 호출(LLM 미경유) → 승인/거부/복습기록처럼
  결정론적 작업은 빠르고 안정적으로.

### 채팅 vs 버튼
- **채팅(에이전트)**: 추론 흐름 — ingest(triage+claim추출), verify(증거수집), answer(epistemic 합성), learning(카드생성).
- **버튼(직접 함수)**: 결정론적 — claim 승인/거부, status 전이, 복습 기록, 캡처.

## 데이터 모델

`personal-ai-wiki-learning-system-design.md` §6의 스키마를 **그대로 따른다**. `wiki_agent/schema.py`가
enum(`claim_type`, `status`)·frontmatter·ID 생성의 **단일 출처**(원리 문서 §6.2를 미러). 모든 도구가 이걸로 검증.
대상: Source, Claim, Wiki Page, Learning Item, Decision(§6.5).

## 무결성 계층 — in-process MCP 서버 `wiki`

`create_sdk_mcp_server(name="wiki", tools=[...])`. 각 `@tool`은 `core/`의 순수 함수를 감쌈:

| 도구 | 동작 | 게이트 |
|---|---|---|
| `create_source` | raw 적재 + sensitivity 분류 기록 → `00_Inbox/` | sensitivity≠personal이면 work vault로 라우팅/거부 |
| `triage_record` | drop/keep-as-link/deep 결정을 log에 기록 | — |
| `create_claim` | claim-*.md 생성, `status`는 항상 `unverified` 강제, `proposed_status`만 제안 | — |
| `find_similar_claim` | 정규화 키(주제+주체) dedup 후보 | — |
| `promote_claim` | status 전이 + `10_Claims/` 이동 + claim-index 갱신 | **verified는 `approved_by_human` 또는 `evidence_refs` 없으면 deny (원칙9)** |
| `set_claim_status` | disputed/outdated/superseded 등 강등·연결 | — |
| `create_wiki_page`/`update_wiki_page` | frontmatter·claim_refs·index 보장 | high-risk 미검증 승격 차단 |
| `create_learning_item` | learning-*.md | — |
| `list_due_reviews` / `record_review` | next_review 도래분 + level 전이 | — |
| `append_log`/`update_index` | 다른 도구가 내부 호출(직접 노출 안 함) | — |

## 서브에이전트 (`AgentDefinition`)

| 이름 | 역할 | 도구 allowlist |
|---|---|---|
| `ingest` | clip → triage → atomic claim(unverified) 적재 | Read, Grep, `mcp__wiki__{create_source,triage_record,create_claim,find_similar_claim}` |
| `verify` | repo/docs/test 증거 수집 → 승격/차단 제안 | Read, Grep, Glob, Bash, `mcp__wiki__{promote_claim,set_claim_status,create_wiki_page}` |
| `answer` | epistemic status 구분 답변, 새 통찰은 unverified claim으로 피드백 | Read, Grep, Glob, `mcp__wiki__create_claim` (Write 금지) |
| `learning` | skill map/flashcard/quiz/exercise 생성, 복습 큐 | Read, Grep, `mcp__wiki__{create_learning_item,list_due_reviews,record_review}` |

메인 에이전트 system_prompt = "위키 두뇌": 파이프라인 규칙, 인식론 원칙(raw≠진실, LLM 제안/사람 확정),
출력 형식(원리 §10), triage·sensitivity 규칙, 어떤 요청을 어느 서브에이전트에 위임할지.

## 게이트 — `can_use_tool` 콜백

- **검증 게이트(원칙9/A2)**: `promote_claim`의 `target_status=="verified"`인데 `approved_by_human`도 아니고
  `evidence_refs`도 비면 `PermissionResultDeny`. → 사람이 채팅/버튼으로 승인해야 verified.
- **sensitivity 게이트(A3)**: work/confidential 콘텐츠를 personal vault 경로로 쓰면 deny.
- `core/` 함수 자체에도 같은 검증을 둬서 UI 버튼 경로도 동일하게 보호(이중 방어).

## 웹앱

### 백엔드 엔드포인트 (FastAPI)
- `POST /chat` (SSE) — 사용자 턴을 `ClaudeSDKClient`에 전달, 어시스턴트 출력 스트리밍.
- `POST /capture` — text/file/URL → `create_source`. URL은 백엔드가 페치→마크다운 변환.
- `GET /claims/pending`, `POST /claims/{id}/approve`, `POST /claims/{id}/reject` — verify 큐(직접 함수).
- `GET /reviews/due`, `POST /reviews/{id}/record` — review 큐(직접 함수).

### 프론트 (무빌드)
탭 4개: **Chat**(SSE 스트림) / **Capture**(붙여넣기·드롭·URL) / **Verify**(pending claim + 승인·거부) /
**Review**(due 카드 + 채점). 정적 자산을 FastAPI가 서빙, HTMX/SSE로 상호작용.

### 캡처 경로 (v1)
1. **웹앱 빠른 캡처**: 텍스트 붙여넣기 / 파일 드롭 / URL 입력 → `create_source` → `00_Inbox/`.
2. **Obsidian Web Clipper**: 확장이 `00_Inbox/browser-clips/`에 마크다운 저장(폴더+템플릿만 설정, 빌드 없음).
   에이전트 ingest가 Inbox 신규를 집어감.

## 프로젝트 구조

```
personal-ai-wiki/                 # = 현재 dir (Obsidian vault + git repo)
  00_Inbox/ 01_Projects/ 02_Areas/ 03_Resources/
  06_Metadata/{templates,schema,indexes,logs}/
  10_Claims/{pending,verified,attributed,disputed,rejected,outdated}/
  30_Learning/{skill-maps,flashcards,quizzes,exercises,weekly-synthesis}/
  wiki_agent/
    __main__.py          # `uv run wiki` 엔트리 → 웹서버 기동
    app.py               # FastAPI 앱 + 라우트
    agent.py             # ClaudeSDKClient + ClaudeAgentOptions 조립
    schema.py            # enum/frontmatter/ID — 단일 출처 (원리 §6 미러)
    permissions.py       # can_use_tool 게이트
    subagents.py         # AgentDefinition 4개
    core/                # 순수 함수 (무결성 로직)
      sources.py claims.py wiki.py learning.py index.py
    tools.py             # @tool 래퍼 + create_sdk_mcp_server("wiki", ...)
    prompts/             # 시스템·서브에이전트 프롬프트(.md)
    web/                 # 정적 프론트(html/css/js)
  tests/                 # core/ 함수 단위 테스트
  pyproject.toml
  .gitignore
  docs/superpowers/specs/2026-06-07-personal-ai-wiki-agent-design.md
```

## 테스트

- `core/` 함수는 결정론적 → LLM 없이 단위 테스트(입력 → 파일/frontmatter/index 검증, 잘못된 승격은 게이트가 거부).
- FastAPI 라우트는 `core/`를 직접 호출하므로 TestClient로 통합 테스트(LLM 미경유).
- 에이전트 부팅 + 도구 1개 호출 스모크 테스트 1개(Claude Code CLI 필요).

## 위험/오픈 이슈

- **Claude Code CLI 런타임 의존**: `claude-agent-sdk`는 CLI가 설치돼 있어야 동작. 문서/설치 체크 필요.
- **ClaudeSDKClient 동시성**: 단일 사용자 로컬이므로 세션 1개 가정. 채팅 중 버튼 작업은 `core/` 직접 호출이라 충돌 없음.
- **`hooks`/`can_use_tool` 정확한 시그니처**: 구현 시 SDK 최신 문서로 재확인(이미 핵심은 확인).
- **URL 페치 변환 품질**: 단순 HTML→markdown은 노이즈 가능 → 일단 best-effort, triage가 거름.

## 검증(완료 기준)

엔드투엔드: (1) `uv run wiki`로 웹앱 기동 → (2) Capture에 ChatGPT 대화 붙여넣기 → Inbox source 생성 →
(3) Chat에 "이거 인제스트해줘" → unverified claim 적재 → (4) Verify 큐에서 승인 → verified 승격 + claim-index 갱신 →
(5) Chat에 "X 위키에서 답해줘" → epistemic 형식 답변 → (6) Learning 카드 생성 → Review 큐에 등장.
각 단계 후 Obsidian에서 같은 파일이 보이는지 확인.
