"""Draw any ToolResult in Streamlit, in the shared order:
answer -> evidence (formulas, constants, assumptions, references) -> details.
"""

import re
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


def render_result(result: ToolResult, key: str = "result") -> None:
    st.markdown(f"### {escape_markdown(result.answer)}")

    for w in result.warnings:
        st.warning(w)

    # Evidence
    for f in result.formulas:
        st.latex(f.latex)
    if result.constants or result.assumptions:
        with st.expander("Constants and assumptions", expanded=False):
            if result.constants:
                st.dataframe(
                    pd.DataFrame(
                        [
                            [c.name, c.symbol, f"{c.value:g}", c.unit, c.source]
                            for c in result.constants
                        ],
                        columns=["Name", "Symbol", "Value", "Unit", "Source"],
                    ),  # fmt: skip
                    hide_index=True,
                )
            for a in result.assumptions:
                st.markdown(f"- {escape_markdown(a)}")

    # Details
    for t in result.tables:
        if t.title:
            st.markdown(f"**{escape_markdown(t.title)}**")
        st.dataframe(_frame(t), hide_index=True)
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

    if result.sources:
        with st.expander("References", expanded=False):
            for s in result.sources:
                st.caption(s)
