# Plan: 임베딩 OpenAI API 전환

Spec: `../specs/2026-08-25-openai-embeddings-design.md`

- [x] `core/search.py`: provider 스위치 (`WIKI_EMBED_PROVIDER`, 기본 openai) + provider별 기본 모델
- [x] `_openai_embedder` / `_openai_embed_batch` / `_openai_client` (배치 96, 재시도 4회, dimensions)
- [x] `_default_embedder`를 디스패처로, 기존 로컬 경로는 `_local_embedder`로 이름 변경
- [x] e5 접두사를 provider별로 분기, `SearchIndex(prefixes=...)`로 주입
- [x] `iter_docs`가 `sensitivity`를 싣고, `SearchIndex(skip_sensitivities=...)`가 원격 전송에서 제외
- [x] 차단 대상을 `confidential` 하나로 축소 (work는 전송 허용, 2026-08-25 사용자 결정)
- [x] `.env` 로더(`load_env_file`, 셸 우선) + `.env.example` + gitignore
- [x] 키 부재를 읽을 수 있는 실패로: CLI 안내 + exit 2, 웹 503
- [x] 벡터 캐시 파일명에 provider와 모델명 포함
- [x] 테스트 12개 추가, 전체 155개 통과, ruff clean
- [x] ARCHITECTURE.md의 "No external embedding API" 제약 문장 교체, AGENTS.md에 키 요구 명시

## 남은 것 (사람이 해야 함)

- [ ] `cp .env.example .env` 후 `OPENAI_API_KEY` 채우기 (개인 계정)
- [ ] 실키로 첫 호출 한 번 (응답 스키마, rate limit 확인)
