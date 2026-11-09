import json

import pytest
from pydantic import BaseModel

from chemsidekick.core.registry import Registry
from chemsidekick.core.results import RecentStore
from chemsidekick.core.schemas import Artifact, ToolResult

REG = Registry()


class Inp(BaseModel):
    x: int = 1


@REG.tool(name="demo", number=1, title="Demo", summary="", category="reference")
def demo(inp: Inp) -> ToolResult:
    return ToolResult(answer=f"x={inp.x}")


def add(store: RecentStore, x: int, with_file: bool = False):
    number, folder = store.new_folder("demo")
    result = demo(Inp(x=x))
    if with_file:
        f = folder / "a.xyz"
        f.write_text("data")
        result = result.model_copy(update={"artifacts": [Artifact(kind="xyz", path=f)]})
    return store.record(
        number, folder, REG.get("demo"), Inp(x=x), result, elapsed_s=0.01, peak_memory_mb=None
    )


def test_numbers_increase_and_newest_first(tmp_path):
    store = RecentStore(tmp_path / "recent")
    for x in range(3):
        add(store, x)
    entries = store.entries()
    assert [e.number for e in entries] == [3, 2, 1]
    assert entries[0].answer == "x=2"
    assert entries[0].tool_id == "REF-01"
    assert store.get().number == 3
    assert store.get(1).answer == "x=0"


def test_only_newest_limit_are_kept(tmp_path):
    store = RecentStore(tmp_path / "recent", limit=5)
    for x in range(8):
        add(store, x)
    assert [e.number for e in store.entries()] == [8, 7, 6, 5, 4]
    assert len(list((tmp_path / "recent").iterdir())) == 5
    with pytest.raises(LookupError, match="#1 is not in the recent results"):
        store.get(1)


def test_run_file_records_input_and_relative_artifacts(tmp_path):
    store = RecentStore(tmp_path / "recent")
    entry = add(store, 7, with_file=True)
    run = json.loads((entry.path / "run.json").read_text())
    assert run["input"] == {"x": 7}
    assert run["tool_id"] == "REF-01"
    assert run["result"]["artifacts"][0]["path"] == "a.xyz"


def test_save_copies_everything(tmp_path):
    store = RecentStore(tmp_path / "recent")
    add(store, 1, with_file=True)
    dest = store.save(None, tmp_path / "saved")
    assert dest.parent == tmp_path / "saved" / "demo"
    assert (dest / "run.json").exists() and (dest / "a.xyz").exists()
    # Saving twice in the same second does not overwrite.
    assert store.save(None, tmp_path / "saved") != dest


def test_discard_and_empty_store(tmp_path):
    store = RecentStore(tmp_path / "recent")
    with pytest.raises(LookupError, match="no recent results"):
        store.get()
    number, folder = store.new_folder("demo")
    store.discard(folder)
    assert store.entries() == []
