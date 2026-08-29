# vault 쓰기 락 (Spec)

> 상태: 구현 완료 (2026-08-30)

## 문제

vault에 쓰는 프로세스는 한 번에 하나여야 했다. 그래서 2026-08-29에 클립 26개를 축 7개로
나눠 ingest할 때 서로 독립인 축들을 한 줄로 순서대로 돌 수밖에 없었고 26시간이 걸렸다.

측정치 (2026-08-29, 재측정 불필요):

- vault 파일 1,731개 기준 `git add -A -- 10_Claims` 0.02~0.04초,
  `git diff --cached --quiet` 0.01~0.02초
- 실제 쓰기 사이클 간격은 4~12초 (커밋 타임스탬프에서 측정)
- 즉 git은 사이클의 1% 남짓이고 나머지는 전부 모델 시간이다

락으로 짧은 쓰기 구간만 직렬화하면 비싼 부분(클립 통독, 교차검증 2~4차, 페이지 초안)은
프로세스끼리 겹쳐 돌 수 있다.

## 경쟁 지점 넷 (하나만 막으면 안 된다)

1. `core/ids.py`의 `next_seq`: 디렉터리를 훑어 최대 번호 + 1. 둘이 같은 번호를 딴다.
2. `.git/index.lock`: `commit_vault`의 `git add` -> `git commit`이 겹치면 락을 다툰다.
3. `commit_vault`의 스코프 `git add -A`: 1, 2를 완벽히 막아도 다른 프로세스가 방금 쓴
   미커밋 파일이 내 "created ..." 커밋에 쓸려 들어간다. 파일은 멀쩡한데 감사 추적이
   거짓말을 한다. 제일 안 보이는 지점.
4. `core/index.py`의 `update_index`: read-modify-write라 갱신 하나가 사라진다.
   `append_log`는 O_APPEND라 위험이 낮지만 같은 임계구역에 둔다.

1번만 고치면 오히려 나빠진다: claim은 파일명이 id라 충돌이 `FileExistsError`로 시끄럽게
죽지만, source는 파일명이 제목이라 조용히 둘이 생긴다. 1번만 막으면 그 시끄러운 신호가
사라지고 2, 3, 4번은 조용한 실패로 남는다.

## 설계

- `core/locking.py`: `fcntl.flock` 기반 컨텍스트 매니저 `vault_write_lock(vault, timeout)`.
- 임계구역은 쓰기 핸들러 **전체**다: 번호 따기 -> 파일 쓰기 -> 인덱스/로그 갱신 ->
  git add -> git commit. `_done()`만 감싸면 `next_seq`가 락 밖에 남는다.
- `tools.py`의 `_locked` 데코레이터를 쓰기 핸들러 14개에 붙인다 (`@tool` 안쪽).
  읽기 전용 6개(find_similar_claim, list_pending, list_due_reviews, collect_git_session,
  search_wiki, vault_next_step)에는 걸지 않는다. 읽기는 병렬로 다 된다.
- 락 파일은 vault 밖: 기본 `~/.cache/wiki-toolkit/locks/vault-<vault 절대경로
  해시>.lock`, `WIKI_LOCK_DIR`로 오버라이드(테스트 격리용). vault 안에 두면 자동
  커밋에 쓸려 들어갈 자리를 골라야 하고, vault가 git repo가 아닐 수도 있다.
  tempdir도 안 된다: macOS(dirhelper)와 systemd-tmpfiles가 오래된 파일을 나이로
  지우는데 flock은 타임스탬프를 안 바꿔서, 3일 넘게 쓰는 락 파일이 청소되고 다음
  open()이 새 inode로 "둘 다 획득"을 만든다 (검토에서 실증됨). 같은 이유로 락 파일은
  절대 지우지 않는다. flock은 프로세스가 죽으면 커널이 풀므로 스테일 락이 없다.
- 획득은 LOCK_NB 폴링 + 타임아웃(기본 30초, `WIKI_WRITE_LOCK_TIMEOUT`). 초과하면
  명확한 TimeoutError. 조용히 기다리지 않는다.
- `WIKI_WRITE_LOCK_DISABLE=1`: 경쟁 재현 테스트 전용 스위치. "락을 뺐을 때 테스트가
  실패한다"를 증명할 통로가 필요해서 뒀다. 운영에서 켜지 않는다.

## 검증

- `tests/test_locking.py`: multiprocessing 프로세스 둘 + 라운드마다 Barrier 동기화.
  락 켜고: id 중복 0건, 커밋 수 = 쓰기 수, 커밋마다 자기 파일 하나만 (지점 3).
  락 끄고(같은 하네스): 중복 id가 실제로 생기는지. 안 생기면 하네스가 경쟁을 재현
  못 한 것이므로 테스트가 실패한다. 공허한 통과를 막는 장치 둘: barrier 실패는
  워커를 죽여 exitcode 검사에 걸리고, "시도한 쓰기 수 = 생긴 파일 수 + 핸들러 예외
  수" 항등식을 먼저 확인한다.
- 기존 249개 테스트는 그대로 통과해야 한다.

## 비범위

- 축을 실제로 병렬로 돌리는 것 (락까지가 범위다).
- 한 축을 여러 프로세스로 쪼개는 것 (여전히 금지, ARCHITECTURE.md 참조).
- id 형식 변경 (`{prefix}-{yyyymmdd}-{NNN}` 그대로).
- `commit_vault` 실패 처리 변경 (호출부 `_done`이 이미 경고를 붙인다).
- 검색 임베딩 캐시의 동시성 (~/.cache라 vault 밖이고, 깨져도 재생성된다).
