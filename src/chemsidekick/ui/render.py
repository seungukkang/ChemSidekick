"""Draw any ToolResult in Streamlit, in the shared order:
answer -> highlights -> warnings -> formulas -> drawings and 3D structures -> tables
and files -> footnotes
(notes, assumptions, constants, references) in small text at the bottom.
"""

import html
import re
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import streamlit as st

from chemsidekick.core.schemas import Artifact, Highlight, Table, ToolResult
from chemsidekick.core.viewer import viewer_html

VIEWER_HEIGHT = 520

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|>~$])")
_NUMBER = re.compile(r"^[−+-]?\d[\d.,]*(\(\d+\))?( ?[a-zA-Zµ%]+)?$")

# Small tables are drawn as plain HTML (clean, full width); big ones as an
# interactive data grid (sorting, search, download).
HTML_TABLE_MAX_ROWS = 60

# Colors for tagged cells (e.g. periodic-table blocks). Tiles share one neutral
# fill; the tag color is used for the border, so it reads in light and dark themes.
TAG_COLORS = ["#f43f5e", "#f59e0b", "#3b82f6", "#10b981", "#8b5cf6", "#f97316"]

# Tile grids (clickable tables): every tile is the same size and the gap between
# rows equals the gap between columns. Section gaps (Table.column_gaps) are a bit
# wider; widths are in tiles.
TILE_HEIGHT_PX = 68
TILE_GAP_PX = 4
LABEL_WIDTH = 0.55
SECTION_GAP = 0.22

CSS = """
<style>
.csk-table { width: 100%; border-collapse: collapse; margin: .25rem 0 1.25rem; font-size: .95rem; }
.csk-table th { text-align: left; font-weight: 600; font-size: .8rem; opacity: .6;
    padding: 6px 12px; border-bottom: 1px solid rgba(128,128,128,.35); }
.csk-table, .csk-table tr, .csk-table th, .csk-table td { border-left: none !important;
    border-right: none !important; border-top: none !important; }
.csk-table td { padding: 7px 12px; border-bottom: 1px solid rgba(128,128,128,.14) !important; }
.csk-table td:first-child { opacity: .8; }
.csk-table.compact td:first-child { white-space: nowrap; width: 1%; padding-right: 28px; }
.csk-table .num { text-align: center; font-variant-numeric: tabular-nums; }
.csk-table.compact .num { text-align: left; }
.csk-table .minor { width: 1%; white-space: nowrap; text-align: right;
    font-size: .78rem; opacity: .5; }
.csk-hl { border: 1px solid rgba(128,128,128,.25); border-radius: 12px;
    padding: 10px 14px; height: 100%; }
.csk-hl .label { font-size: .75rem; opacity: .6; margin-bottom: 2px; }
.csk-hl .value { font-size: 1.25rem; font-weight: 600; line-height: 1.4; }
.csk-card-title { text-align: center; font-weight: 600; font-size: .9rem; }
.csk-card-note { text-align: center; font-size: .75rem; opacity: .6; min-height: 1.1em; }
.csk-col-label { text-align: center; font-size: .7rem; opacity: .5; }
.csk-row-label { text-align: center; font-size: .75rem; opacity: .5; }
.csk-legend { display: flex; gap: 16px; font-size: .8rem; margin: 10px 0 4px; flex-wrap: wrap; }
.csk-legend span { display: inline-flex; align-items: center; gap: 6px; }
.csk-legend i { width: 14px; height: 14px; border-radius: 4px; display: inline-block;
    border: 2px solid; }
div[class*="st-key-tiles-"], div[class*="st-key-tiles-"] div[data-testid="stVerticalBlock"],
div[class*="st-key-tiles-"] div[data-testid="stHorizontalBlock"] {
    gap: __GAP__px !important; }
div[class*="st-key-tiles-"] div[data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important; }
div[class*="st-key-tiles-"] div[data-testid="stColumn"] { min-width: 0 !important; }
div[class*="st-key-tiles-"] .csk-row-label { line-height: __TILE_H__px; }
div[class*="st-key-tiles-"] .csk-section-gap { height: 10px; }
div[class*="st-key-act-"] button { height: __TILE_H__px; min-height: __TILE_H__px; width: 100%;
    padding: 3px 2px; border-radius: 7px; line-height: 1.15;
    background: rgba(128,128,128,.07); border: 1.5px solid rgba(128,128,128,.4);
    transition: background .12s, transform .12s; }
div[class*="st-key-act-"] button:hover { transform: translateY(-1px); }
div[class*="st-key-act-"] button p { margin: 0; max-width: 100%; overflow: hidden;
    white-space: nowrap; text-overflow: ellipsis; }
div[class*="st-key-act-"] button div[data-testid="stMarkdownContainer"] {
    display: flex; flex-direction: column; align-items: center; width: 100%; min-width: 0; }
div[class*="st-key-act-"] button div[data-testid="stMarkdownContainer"] p:nth-child(1) {
    font-size: .58rem; opacity: .6; }
div[class*="st-key-act-"] button div[data-testid="stMarkdownContainer"] p:nth-child(2) {
    font-size: 1.05rem; font-weight: 700; line-height: 1.1; }
div[class*="st-key-act-"] button div[data-testid="stMarkdownContainer"] p:nth-child(3) {
    font-size: .5rem; opacity: .75; }
div[class*="st-key-act-"] button div[data-testid="stMarkdownContainer"] p:nth-child(4) {
    font-size: .52rem; opacity: .65; font-variant-numeric: tabular-nums; }
</style>
"""
CSS = CSS.replace("__GAP__", str(TILE_GAP_PX)).replace("__TILE_H__", str(TILE_HEIGHT_PX))


def escape_markdown(text: str) -> str:
    return _MD_SPECIAL.sub(r"\\\1", text)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def _frame(t: Table) -> pd.DataFrame:
    # All cells as text: mixed types in one column break Arrow serialization,
    # and the tool already formatted the numbers the way they should be shown.
    rows = [["" if v is None else str(v) for v in row] for row in t.rows]
    columns, seen = [], set()
    for c in t.columns:  # unique, non-empty names (pandas requirement)
        name = c or " "
        while name in seen:
            name += "​"
        seen.add(name)
        columns.append(name)
    return pd.DataFrame(rows, columns=columns)


def is_compact(t: Table) -> bool:
    """A short label/value table (at most 3 columns) that can share a row with another."""
    return len(t.columns) <= 3 and not t.action_field


def html_table(t: Table) -> str:
    """A small table as clean HTML: minor columns small, grey, and right-aligned."""
    texts = [["" if v is None else str(v) for v in row] for row in t.rows]
    numeric = set()
    for c in range(len(t.columns)):
        values = [row[c] for row in texts if row[c]]
        if c and values and all(_NUMBER.match(v) for v in values):
            numeric.add(c)

    def cls(c: int) -> str:
        if c in t.minor_columns:
            return ' class="minor"'
        return ' class="num"' if c in numeric else ""

    head = "".join(f"<th{cls(c)}>{html.escape(col)}</th>" for c, col in enumerate(t.columns))
    body = "".join(
        "<tr>" + "".join(f"<td{cls(c)}>{html.escape(v)}</td>" for c, v in enumerate(row)) + "</tr>"
        for row in texts
    )
    kind = "csk-table compact" if is_compact(t) else "csk-table"
    return f'<table class="{kind}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _data_grid(t: Table) -> None:
    st.dataframe(_frame(t), hide_index=True, height=min(600, 35 * (len(t.rows) + 1) + 3))


OnAction = Callable[[str, str], None]


def _tag_colors(t: Table) -> dict[str, str]:
    return {tag: TAG_COLORS[i % len(TAG_COLORS)] for i, tag in enumerate(t.tags)}


def grid_slots(t: Table, row: list) -> list[int | None]:
    """Column order for one row of a tile grid: column indexes, with None for a
    section gap. Every row has the same slots, so all tiles have the same width.
    A gap between two cells of the same tag (e.g. inside the f-block row) is moved
    to the end of the row, keeping that row's tiles together."""

    def tag(c: int) -> str | None:
        text = "" if row[c] is None else str(row[c])
        info = t.cells.get(text) if text else None
        return info.tag if info else None

    slots: list[int | None] = []
    moved = 0
    for c in range(len(t.columns)):
        if c in t.column_gaps:
            if c > 0 and tag(c) is not None and tag(c) == tag(c - 1):
                moved += 1
            else:
                slots.append(None)
        slots.append(c)
    return slots + [None] * moved


def _tile_label(text: str, info) -> str:
    """Button label: number, symbol, then small lines (one paragraph each)."""
    if info is None:
        return text
    parts = [escape_markdown(p) for p in [info.top, text, *info.lines] if p is not None]
    if info.unconfirmed and info.lines and info.lines[-1]:
        parts[-1] = f"*{parts[-1]}*"
    return "\n\n".join(p if p else "&nbsp;" for p in parts)


def _action_grid(t: Table, key: str, on_action: OnAction) -> None:
    """A table whose cells are tiles (e.g. a periodic table): one click runs the tool."""
    colors = _tag_colors(t)
    css = "".join(
        f'div[class*="st-key-act-"][class*="-tag-{tag}-"] button {{ border-color: {color}; }}'
        f'div[class*="st-key-act-"][class*="-tag-{tag}-"] button:hover '
        f"{{ background: {color}26; border-color: {color}; }}"
        for tag, color in colors.items()
    )
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

    clickable = set(t.action_columns)

    def width(c: int | None) -> float:
        if c is None:
            return SECTION_GAP
        return 1.0 if c in clickable else LABEL_WIDTH

    with st.container(key=f"tiles-{key}"):
        # Column labels (e.g. group numbers) above the grid.
        slots = grid_slots(t, t.columns)
        for col, c in zip(st.columns([width(c) for c in slots], gap=None), slots, strict=True):
            if c is not None and t.columns[c]:
                with col:
                    st.markdown(
                        f"<div class='csk-col-label'>{html.escape(t.columns[c])}</div>",
                        unsafe_allow_html=True,
                    )
        for r, row in enumerate(t.rows):
            if not any(row):
                st.markdown("<div class='csk-section-gap'></div>", unsafe_allow_html=True)
                continue
            slots = grid_slots(t, row)
            cols = st.columns([width(c) for c in slots], gap=None)
            for col, c in zip(cols, slots, strict=True):
                text = "" if c is None or row[c] is None else str(row[c])
                if not text:
                    continue
                with col:
                    if c in clickable:
                        info = t.cells.get(text)
                        tag = info.tag if info else ""
                        st.button(
                            _tile_label(text, info),
                            key=f"act-{key}-tag-{tag}-r{r}c{c}",
                            on_click=on_action,
                            args=(t.action_field, text),
                            width="stretch",
                        )
                    else:
                        st.markdown(
                            f"<div class='csk-row-label'>{html.escape(text)}</div>",
                            unsafe_allow_html=True,
                        )
    if t.tags:
        chips = "".join(
            f"<span><i style='border-color:{colors[tag]}'></i>{html.escape(label)}</span>"
            for tag, label in t.tags.items()
        )
        st.markdown(f"<div class='csk-legend'>{chips}</div>", unsafe_allow_html=True)


def _table(t: Table, key: str, on_action: OnAction | None) -> None:
    if t.title:
        st.markdown(f"**{escape_markdown(t.title)}**")
    if t.action_field and on_action:
        _action_grid(t, key, on_action)
    elif len(t.rows) <= HTML_TABLE_MAX_ROWS:
        st.markdown(html_table(t), unsafe_allow_html=True)
    else:
        _data_grid(t)


# ---------------------------------------------------------------------------
# Highlights and files
# ---------------------------------------------------------------------------


def _highlights(items: list[Highlight]) -> None:
    cols = st.columns(len(items))
    for col, h in zip(cols, items, strict=True):
        with col:
            st.markdown(
                f"<div class='csk-hl' title='{html.escape(h.note, quote=True)}'>"
                f"<div class='label'>{html.escape(h.label)}</div>"
                f"<div class='value'>{html.escape(h.value)}</div></div>",
                unsafe_allow_html=True,
            )
    st.write("")


GALLERY_COLUMNS = 4


def _gallery(drawings: list[Artifact]) -> None:
    """Drawings as a grid of equal cards: the image, a title, and a small note."""
    for start in range(0, len(drawings), GALLERY_COLUMNS):
        cols = st.columns(GALLERY_COLUMNS)
        for col, a in zip(cols, drawings[start : start + GALLERY_COLUMNS], strict=False):
            with col, st.container(border=True):
                st.image(Path(a.path).read_text(encoding="utf-8"), width="stretch")
                st.markdown(
                    f"<div class='csk-card-title'>{html.escape(a.title)}</div>"
                    f"<div class='csk-card-note'>{html.escape(a.note)}</div>",
                    unsafe_allow_html=True,
                )


_MIME = {
    "svg": "image/svg+xml",
    "png": "image/png",
    "sdf": "chemical/x-mdl-sdfile",
    "xyz": "chemical/x-xyz",
    "html": "text/html",
    "json": "application/json",
}


def render_result(
    result: ToolResult, key: str = "result", on_action: OnAction | None = None
) -> None:
    """Draw a result. `on_action(field, value)` handles clicks on clickable tables."""
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(f"### {escape_markdown(result.answer)}")
    if result.highlights:
        _highlights(result.highlights)

    # Warnings are about this input or result, so they stay prominent.
    for w in result.warnings:
        st.warning(w)

    for f in result.formulas:
        st.latex(f.latex)

    # Drawings and 3D structures are the main content of a result, so they come
    # before the tables.
    _gallery([a for a in result.artifacts if a.kind == "svg" and Path(a.path).exists()])
    for s in result.structures:
        st.iframe(viewer_html(s), height=VIEWER_HEIGHT)

    # Short label/value tables are placed two per row; others take the full width.
    tables, i = result.tables, 0
    while i < len(tables):
        t = tables[i]
        nxt = tables[i + 1] if i + 1 < len(tables) else None
        if is_compact(t) and nxt is not None and is_compact(nxt):
            left, right = st.columns(2, gap="large")
            with left:
                _table(t, key, on_action)
            with right:
                _table(nxt, key, on_action)
            i += 2
        else:
            _table(t, key, on_action)
            i += 1
    # Drawings are shown in the gallery (and kept with the result); other files get a
    # download button.
    for i, a in enumerate(result.artifacts):
        path = Path(a.path)
        if a.kind != "svg" and path.exists():
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
