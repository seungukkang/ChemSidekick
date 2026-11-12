"""ChemSidekick Streamlit app. Start with `csk ui`.

Layout: search box and category tabs at the top, a grid of square tool
icons (name shown on hover), and the selected tool's form and result below.
Everything is generated from the tool registry.
"""

import html
import tempfile
from pathlib import Path

import streamlit as st
from pydantic import ValidationError

from chemsidekick import __version__
from chemsidekick.core.config import ConfigError, load_config
from chemsidekick.core.registry import CATEGORIES, Registry, ToolSpec, discover
from chemsidekick.core.results import RecentStore
from chemsidekick.core.runner import RunError, run_tool
from chemsidekick.core.schemas import ToolError, ToolResult
from chemsidekick.core.theme import THEME_COLOR
from chemsidekick.ui.forms import draw, widget_specs
from chemsidekick.ui.render import render_result
from chemsidekick.ui.views import VIEWS

ALL = "All"
GRID_COLUMNS = 8

# Square icon buttons. Streamlit puts a "st-key-<key>" class on keyed widgets.
_CSS = """
<style>
div[class*="st-key-tool-"] button, div[class*="st-key-selected-tool-"] button {
    width: 64px; height: 64px; min-height: 64px; padding: 0;
    border-radius: 14px; font-size: 1.4rem;
}
div[class*="st-key-tool-"] button p, div[class*="st-key-selected-tool-"] button p {
    font-size: 1.4rem; font-weight: 600; }
div[class*="st-key-selected-"] button { border: 2px solid __THEME__; }
.csk-tool-id { font-size: .68rem; letter-spacing: .08em; opacity: .45; margin-bottom: 2px; }
.csk-tool-title { font-size: 1.5rem; font-weight: 600; line-height: 1.25; }
</style>
""".replace("__THEME__", THEME_COLOR)


def visible_tools(registry: Registry, category: str, query: str) -> list[ToolSpec]:
    """Tools to show in the grid: search covers all categories, otherwise filter by tab."""
    if query.strip():
        return registry.search(query)
    tools = registry.all()
    if category == ALL:
        return tools
    key = next((k for k, c in CATEGORIES.items() if c.title == category), None)
    return [t for t in tools if t.category == key]


def first_tool(registry: Registry) -> ToolSpec:
    """The tool selected when the app opens: the first one with a start view (it has
    something to show before any input, e.g. the periodic table), else the first."""
    tools = registry.all()
    return next((t for t in tools if t.start_view), tools[0])


def _icon_button(spec: ToolSpec, selected: bool) -> bool:
    prefix = "selected-tool" if selected else "tool"
    tooltip = f"{spec.title} ({spec.id})\n\n{spec.summary}"
    if spec.icon:
        return st.button(
            "", icon=f":material/{spec.icon}:", help=tooltip, key=f"{prefix}-{spec.name}"
        )
    return st.button(spec.title[:1].upper(), help=tooltip, key=f"{prefix}-{spec.name}")


def _grid(tools: list[ToolSpec]) -> None:
    if not tools:
        st.info("No tool matches. Try another word, or clear the search.")
        return
    for start in range(0, len(tools), GRID_COLUMNS):
        cols = st.columns(GRID_COLUMNS, gap="small")
        for col, spec in zip(cols, tools[start : start + GRID_COLUMNS], strict=False):
            with col:
                if _icon_button(spec, st.session_state.get("tool") == spec.name):
                    st.session_state["tool"] = spec.name
                    st.session_state.pop("last", None)
                    st.session_state.pop("pending", None)
                    st.rerun()


def _run(spec: ToolSpec, values: dict) -> None:
    try:
        config = load_config()
    except ConfigError as e:
        st.error(str(e))
        return
    try:
        inp = spec.input_model(**values)
    except ValidationError as e:
        st.error("; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()))
        return
    store = RecentStore(limit=config.recent_limit)
    number, folder = store.new_folder(spec.name)
    try:
        with st.spinner(f"Running {spec.title}…"):
            outcome = run_tool(spec, inp, workdir=folder, config=config, confirmed=True)
    except (ToolError, RunError) as e:
        store.discard(folder)
        st.error(str(e))
        return
    store.record(number, folder, spec, inp, outcome.result,
                 elapsed_s=outcome.elapsed_s, peak_memory_mb=outcome.peak_memory_mb)  # fmt: skip
    st.session_state["last"] = (spec.name, number, outcome.result.model_dump_json())


def _start_view(spec: ToolSpec) -> None:
    """Run a light tool with its default input to show its start view (not kept as a result)."""
    try:
        outcome = run_tool(
            spec, spec.input_model(), workdir=Path(tempfile.mkdtemp(prefix="csk-start-"))
        )
    except (ToolError, RunError, ValidationError) as e:
        st.error(str(e))
        return
    st.session_state["last"] = (spec.name, None, outcome.result.model_dump_json())


def _defaults(spec: ToolSpec) -> dict:
    return {w.name: w.default for w in widget_specs(spec.input_model)}


def _on_action(spec: ToolSpec):
    """Click on a table cell: put the value into the input field and run the tool."""

    def handler(field: str, value: str) -> None:
        st.session_state[f"in-{spec.name}-{field}"] = value
        st.session_state["pending"] = (spec.name, {**_defaults(spec), field: value})

    return handler


def _back_to_start(spec: ToolSpec) -> None:
    for w in widget_specs(spec.input_model):
        st.session_state[f"in-{spec.name}-{w.name}"] = w.default if w.default is not None else ""
    st.session_state.pop("last", None)


def _tool_page(spec: ToolSpec) -> None:
    # The ID is for reference (CLI, notes); small and above, so the name stands out.
    st.markdown(
        f"<div class='csk-tool-id'>{html.escape(spec.id)}</div>"
        f"<div class='csk-tool-title'>{html.escape(spec.title)}</div>",
        unsafe_allow_html=True,
    )
    st.caption(spec.summary)
    if spec.name in VIEWS:
        VIEWS[spec.name](spec)
        return

    pending = st.session_state.pop("pending", None)
    if pending and pending[0] == spec.name:
        _run(spec, pending[1])
    with st.form(key=f"form-{spec.name}"):
        values = {
            w.name: draw(w, key=f"in-{spec.name}-{w.name}") for w in widget_specs(spec.input_model)
        }
        confirm = True
        if spec.resources == "heavy":
            confirm = st.checkbox(
                "This is a heavy tool. Run it anyway.", key=f"confirm-{spec.name}"
            )
        submitted = st.form_submit_button("Run", type="primary")
    if submitted:
        if not confirm:
            st.warning("Tick the confirmation box to run a heavy tool.")
        else:
            _run(spec, values)

    last = st.session_state.get("last")
    if spec.start_view and not (last and last[0] == spec.name):
        _start_view(spec)
        last = st.session_state.get("last")
    if last and last[0] == spec.name:
        _, number, payload = last
        result = ToolResult.model_validate_json(payload)
        if number is None:  # the start view: nothing to save
            render_result(result, key="start", on_action=_on_action(spec))
            return
        if spec.start_view:
            st.button(f"← {spec.start_view}", key="back", on_click=_back_to_start, args=(spec,))
        render_result(result, key=f"r{number}", on_action=_on_action(spec))
        left, right = st.columns([1, 4])
        with left:
            if st.button("Save", key=f"save-{number}"):
                config = load_config()
                dest = RecentStore(limit=config.recent_limit).save(number, config.save_dir)
                st.session_state["saved"] = (number, str(dest))
        with right:
            saved = st.session_state.get("saved")
            if saved and saved[0] == number:
                st.success(f"Saved to {saved[1]}")
            else:
                st.caption(f"Result #{number} · kept with the newest results until you save it")


def main() -> None:
    st.set_page_config(page_title="ChemSidekick", page_icon="⚗️", layout="wide")
    st.markdown(_CSS, unsafe_allow_html=True)
    registry = discover()

    st.markdown(f"**ChemSidekick** <span style='opacity:.5'>{__version__}</span>",
                unsafe_allow_html=True)  # fmt: skip
    query = st.text_input("Search tools", placeholder="Search tools…", label_visibility="collapsed")
    tabs = [ALL] + [CATEGORIES[k].title for k in registry.by_category()]
    category = st.segmented_control("Category", tabs, default=ALL, label_visibility="collapsed")

    tools = visible_tools(registry, category or ALL, query)
    if "tool" not in st.session_state and registry.all():
        st.session_state["tool"] = first_tool(registry).name
    _grid(tools)
    st.divider()

    name = st.session_state.get("tool")
    if name in registry:
        _tool_page(registry.get(name))


# `streamlit run` executes this file as __main__; importing it (e.g. in tests) must not.
if __name__ == "__main__":
    main()
