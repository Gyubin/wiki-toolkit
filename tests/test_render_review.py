"""검토표 스크립트의 실행 경계. 내부 로직 테스트가 아니라 사람이 치는 명령의 결과다."""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_malformed_source_id_gets_a_friendly_error(vault, tmp_path):
    """find_source가 id 형식을 검증하게 되면서 ValueError가 새로 나온다.
    트레이스백이 아니라 "source를 찾을 수 없습니다"로 끝나야 한다."""
    r = subprocess.run(
        [sys.executable, str(REPO / "tools/render_review.py"), str(vault),
         "source-2026-08-28-001", "--out", str(tmp_path / "o.html")],
        capture_output=True, text=True, cwd=REPO)
    assert r.returncode != 0
    assert "source를 찾을 수 없습니다" in (r.stdout + r.stderr)
    assert "Traceback" not in r.stderr
