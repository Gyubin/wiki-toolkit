import pytest

from wiki_agent.core import scaffold


@pytest.fixture
def vault(tmp_path):
    scaffold.scaffold_vault(tmp_path)
    return tmp_path
