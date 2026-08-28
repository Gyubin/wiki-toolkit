import pytest

from wiki_toolkit.core import scaffold


@pytest.fixture(autouse=True)
def _no_real_env_file(monkeypatch, tmp_path):
    """개발자의 실제 repo .env가 테스트 프로세스에 새지 않게 한다.

    cli.main()이 load_env_file()을 무조건 부르는데, 이 머신의 repo 루트에는 진짜 키가 든
    .env가 있다. 격리하지 않으면 테스트 결과가 머신과 실행 순서에 의존하게 된다.
    """
    monkeypatch.setenv("WIKI_ENV_FILE", str(tmp_path / "no-such.env"))


@pytest.fixture
def vault(tmp_path):
    scaffold.scaffold_vault(tmp_path)
    return tmp_path
