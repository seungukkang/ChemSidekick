"""Draw any ToolResult in Streamlit, in the shared order:
answer -> evidence (formulas, constants, assumptions, references) -> details.
"""

import re
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import streamlit as st

from chemsidekick.core.schemas import Table, ToolResult

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|>~$])")


def escape_markdown(text: str) -> str:
    return _MD_SPECIAL.sub(r"\\\1", text)


def _frame(t: Table) -> pd.DataFrame:
    # All cells as text: mixed types in one column break Arrow serialization,
    # and the tool already formatted the numbers the way they should be shown.
    rows = [["" if v is None else str(v) for v in row] for row in t.rows]
    # Column names must be unique and non-empty for pandas; pad with invisible spaces.
    columns, seen = [], set()
    for c in t.columns:
        name = c or " "
        while name in seen:
            name += "\u200b"
        seen.add(name)
        columns.append(name)
    return pd.DataFrame(rows, columns=columns)


_MIME = {
    "svg": "image/svg+xml",
    "png": "image/png",
    "sdf": "chemical/x-mdl-sdfile",
    "xyz": "chemical/x-xyz",
    "html": "text/html",
    "json": "application/json",
}


def _column_width(frame: pd.DataFrame, column: str) -> int:
    """Pixel width that fits the longest text in a column (about 8 px per character)."""
    longest = max([len(str(column)), *(len(v) for v in frame[column])])
    return min(640, 8 * longest + 28)


def _table(t: Table) -> None:
    frame = _frame(t)
    # Every column is as wide as its content, so short reference columns ("Check")
    # stay narrow and long values are not cut off. Minor columns are labelled small.
    config = {
        col: st.column_config.TextColumn(width=_column_width(frame, col)) for col in frame.columns
    }
    st.dataframe(
        frame,
        hide_index=True,
        column_config=config,
        width="content",
        height=35 * (len(frame) + 1) + 3,  # header + rows: no inner scroll bar
    )


OnAction = Callable[[str, str], None]


def _action_grid(t: Table, key: str, on_action: OnAction) -> None:
    """A table whose cells are buttons (e.g. a periodic table): one click runs the tool."""
    clickable = set(t.action_columns)
    for r, row in enumerate(t.rows):
        if not any(row):
            st.write("")  # blank spacer row
            continue
        cols = st.columns(len(t.columns), gap=None)
        for c, (col, value) in enumerate(zip(cols, row, strict=True)):
            text = "" if value is None else str(value)
            with col:
                if c in clickable and text:
                    st.button(text, key=f"act-{key}-{r}-{c}", on_click=on_action,
                              args=(t.action_field, text), width="stretch")  # fmt: skip
                elif text:
                    st.markdown(f"<div class='csk-row-label'>{text}</div>", unsafe_allow_html=True)


def render_result(
    result: ToolResult, key: str = "result", on_action: OnAction | None = None
) -> None:
    """Draw a result. `on_action(field, value)` handles clicks on clickable tables."""
    st.markdown(f"### {escape_markdown(result.answer)}")

    # Warnings are about this input or result, so they stay prominent.
    for w in result.warnings:
        st.warning(w)

    for f in result.formulas:
        st.latex(f.latex)

    for t in result.tables:
        if t.title:
            st.markdown(f"**{escape_markdown(t.title)}**")
        if t.action_field and on_action:
            _action_grid(t, key, on_action)
        else:
            _table(t)
    for s in result.structures:
        st.caption(f"3D structure: {s.frames[0].n_atoms} atoms, {len(s.frames)} frame(s)")
    for i, a in enumerate(result.artifacts):
        path = Path(a.path)
        if a.kind == "svg" and path.exists():
            st.image(path.read_text(encoding="utf-8"))
        if path.exists():
            st.download_button(
                f"Download {a.title or path.name}",
                data=path.read_bytes(),
                file_name=path.name,
                mime=_MIME.get(a.kind, "application/octet-stream"),
                key=f"{key}-download-{i}",
            )

    # Footnotes: small, at the bottom.
    for line in [*result.notes, *(f"Assumes: {a}" for a in result.assumptions)]:
        st.caption(escape_markdown(line))
    if result.constants:
        with st.expander("Constants", expanded=False):
            st.dataframe(
                pd.DataFrame(
                    [
                        [c.name, c.symbol, f"{c.value:g}", c.unit, c.source]
                        for c in result.constants
                    ],
                    columns=["Name", "Symbol", "Value", "Unit", "Source"],
                ),
                hide_index=True,
            )
    if result.sources:
        with st.expander("References", expanded=False):
            for s in result.sources:
                st.caption(s)
