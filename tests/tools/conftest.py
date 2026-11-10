import pytest

from chemsidekick.core import runner


@pytest.fixture(autouse=True)
def fresh_workdir(tmp_path):
    """Each test writes its tool files into its own folder."""
    token = runner._WORKDIR.set(tmp_path)
    yield tmp_path
    runner._WORKDIR.reset(token)
