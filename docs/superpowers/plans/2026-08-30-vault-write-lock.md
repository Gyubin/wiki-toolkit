# vault 쓰기 락 (ExecPlan)

> spec: `../specs/2026-08-30-vault-write-lock-design.md`
> 상태: 완료 (2026-08-30)

1. `core/locking.py` 추가: `lock_path`(~/.cache/wiki-toolkit/locks + vault 절대경로 해시,
   `WIKI_LOCK_DIR` 오버라이드),
   `vault_write_lock`(flock, LOCK_NB 폴링, 타임아웃, 테스트 전용 disable env).
2. `tools.py`: `_locked` 데코레이터를 만들어 `_done()`으로 끝나는 쓰기 핸들러 14개에
   붙인다. 임계구역이 핸들러 전체가 되어 next_seq, 파일 쓰기, `core/index.py`의
   update_index와 append_log, commit_vault가 전부 한 락 안에 들어온다.
3. `tests/test_locking.py`: spawn 프로세스 둘 + Barrier 라운드 동기화.
   - 락 켜고: id 중복 0건 / 커밋 수 = 쓰기 수 / 커밋마다 자기 파일 하나.
   - 락 끄고: 중복 id가 실제로 생긴다 (경쟁 재현 증명, 안 생기면 테스트 실패).
   - 타임아웃이 TimeoutError로 죽는다 / 읽기 핸들러는 락과 무관하다.
   - 락 파일이 vault 밖이다 / disable env는 no-op이다.
4. `ARCHITECTURE.md`: 락의 존재, 임계구역 범위, 병렬화의 대가(claim id의 축별 연속성
   상실, 감사 질의는 source_refs로), 축 내부 분할은 여전히 금지.
5. `uv run ruff check` + `uv run pytest` 전부 통과 후 커밋, push.
