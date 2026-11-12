"""Tools with a page made for them, used instead of the generated form.

A view gets the tool and draws everything below the tool's title. Most tools
do not need one: the form generated from the input model is enough.
"""

from collections.abc import Callable

from chemsidekick.core.registry import ToolSpec


def _profile(spec: ToolSpec) -> None:
    from chemsidekick.ui.profile_view import render

    render(spec)


VIEWS: dict[str, Callable[[ToolSpec], None]] = {
    "profile": _profile,
}
