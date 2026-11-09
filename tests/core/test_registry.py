import pytest
from pydantic import BaseModel

from chemsidekick.core.registry import Registry, RegistryError, discover
from chemsidekick.core.schemas import ToolResult


class EchoInput(BaseModel):
    text: str = "hi"


def make_registry() -> Registry:
    """A fresh registry with two fake tools, so tests never touch the real one."""
    reg = Registry()

    @reg.tool(
        name="echo",
        title="Echo",
        summary="Repeat the input text",
        category="reference",
        keywords=["repeat", "parrot"],
    )
    def echo(inp: EchoInput) -> ToolResult:
        return ToolResult(answer=inp.text)

    @reg.tool(
        name="shape",
        title="Shape Viewer",
        summary="Show a molecule in 3D",
        category="structure",
        keywords=["3d", "geometry"],
        resources="medium",
    )
    def shape(inp: EchoInput) -> ToolResult:
        return ToolResult(answer="shape")

    return reg


def test_register_and_run():
    reg = make_registry()
    spec = reg.get("echo")
    assert spec.input_model is EchoInput
    assert spec.run(EchoInput(text="hello")).answer == "hello"
    assert len(reg) == 2


def test_group_by_category_keeps_category_order_and_skips_empty():
    reg = make_registry()
    groups = reg.by_category()
    assert list(groups) == ["structure", "reference"]
    assert [s.name for s in groups["structure"]] == ["shape"]


@pytest.mark.parametrize(
    ("query", "expected_first"),
    [
        ("echo", "echo"),  # exact name
        ("sha", "shape"),  # name prefix
        ("3d", "shape"),  # keyword
        ("parr", "echo"),  # keyword substring
        ("viewer", "shape"),  # title
        ("molecule", "shape"),  # summary
        ("ECHO", "echo"),  # case-insensitive
    ],
)
def test_search(query, expected_first):
    assert make_registry().search(query)[0].name == expected_first


def test_search_no_match_and_empty_query():
    reg = make_registry()
    assert reg.search("zzz") == []
    assert [s.name for s in reg.search("  ")] == ["echo", "shape"]


def _declare(reg: Registry, **overrides):
    kwargs = dict(name="t", title="T", summary="s", category="reference")
    kwargs.update(overrides)

    @reg.tool(**kwargs)
    def t(inp: EchoInput) -> ToolResult:
        return ToolResult(answer="")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"name": "echo"}, "already registered"),
        ({"name": "list"}, "reserved"),
        ({"name": "Bad_Name"}, "lowercase"),
        ({"category": "cooking"}, "unknown category"),
        ({"resources": "huge"}, "resources must be"),
    ],
)
def test_invalid_declarations_fail_immediately(overrides, message):
    with pytest.raises(RegistryError, match=message):
        _declare(make_registry(), **overrides)


def test_function_signature_is_checked():
    reg = Registry()
    with pytest.raises(RegistryError, match="Pydantic model"):

        @reg.tool(name="a", title="A", summary="", category="reference")
        def a(inp: str) -> ToolResult:
            return ToolResult(answer="")

    with pytest.raises(RegistryError, match="-> ToolResult"):

        @reg.tool(name="b", title="B", summary="", category="reference")
        def b(inp: EchoInput) -> str:
            return ""


def test_discover_runs_without_tools():
    # No real tools exist yet; discovery must still work.
    assert discover() is not None
