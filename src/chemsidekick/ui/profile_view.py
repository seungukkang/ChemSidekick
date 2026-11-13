"""Streamlit view for the energy profile (ENE-01).

Two columns: the input on the left (reaction or populations, unit,
temperature, and one table of paths that takes a paste from a spreadsheet), the
drawing and the results on the right. Everything else is under "More options".
Every change redraws at once: Streamlit reruns this script on each input
change, and the calculation takes milliseconds.
"""

import tempfile
from pathlib import Path
from typing import get_args

import streamlit as st
from pydantic import ValidationError

from chemsidekick.core.registry import ToolSpec
from chemsidekick.core.runner import RunError, run_tool
from chemsidekick.core.schemas import ToolError
from chemsidekick.core.solvents import load as load_solvents
from chemsidekick.tools.energetics.profile import ProfileInput, SolventChoice
from chemsidekick.ui.render import render_result

K = "pf-"  # session-state key prefix
DEFAULT_PATHS = [
    {"name": "B", "ts": "20.0", "product": "-3.0"},
    {"name": "C", "ts": "22.0", "product": "-5.0"},
]
DEFAULT_STATES = "conf1  0.0\nconf2  0.5\nconf3  1.0\n"


def paths_text(rows: list[dict]) -> str:
    """Table rows -> the tool's paths text: 'name<TAB>ts<TAB>product', '-' for empty."""
    lines = []
    for i, row in enumerate(rows):
        ts, product = (str(row.get(k) or "").strip() for k in ("ts", "product"))
        if not (ts or product):
            continue
        name = str(row.get("name") or "").strip() or f"P{i + 1}"
        lines.append(f"{name.replace(' ', '_')}\t{ts.replace(' ', '') or '-'}\t{product or '-'}")
    return "\n".join(lines)


def _segmented(label: str, options: list[str], key: str, default: str) -> str:
    value = st.segmented_control(label, options, default=default, key=K + key)
    return value or default


def _value_titles(values: dict) -> tuple[str, str]:
    unit = values["unit"]
    ts = {"rate constant": "k", "half-life": "t½"}.get(values.get("ts_values", ""), f"ΔG‡ ({unit})")
    product = "K" if values.get("product_values") == "equilibrium constant" else f"ΔG ({unit})"
    return ts, product


def _more_options(values: dict) -> None:
    """Everything besides unit, temperature and the energies."""
    with st.expander("More options"):
        c = st.columns(2)
        with c[0]:
            values["ts_values"] = st.selectbox(
                "TS values are", ["barrier", "rate constant", "half-life"], key=K + "tsv"
            )
        with c[1]:
            values["product_values"] = st.selectbox(
                "Product values are", ["free energy", "equilibrium constant"], key=K + "pv"
            )
        values["molecularity"] = _segmented(
            "Molecularity", ["unimolecular", "bimolecular"], "mol", "unimolecular"
        )
        if values["molecularity"] == "bimolecular":
            c = st.columns(2)
            with c[0]:
                values["control"] = _segmented(
                    "Control", ["activation", "diffusion"], "ctl", "activation"
                )
            with c[1]:
                values["standard_state"] = _segmented(
                    "Energies are for", ["1 M", "1 atm"], "ss", "1 M"
                )
            c = st.columns(2)
            with c[0]:
                values["partner"] = st.number_input(
                    "Partner concentration (M)", min_value=0.001, value=1.0, key=K + "conc",
                    help="The other reactant, for pseudo-first-order half-lives.",
                )  # fmt: skip
            if values["control"] == "diffusion":
                names = {s.id: s.name for s in load_solvents().solvents.values()}
                with c[1]:
                    values["solvent"] = st.selectbox(
                        "Solvent (25 °C)", list(get_args(SolventChoice)), key=K + "solv",
                        format_func=lambda c: names.get(c, "Other (type its viscosity)"),
                    )  # fmt: skip
                if values["solvent"] == "custom":
                    values["viscosity"] = st.number_input(
                        "Viscosity (mPa s)", min_value=0.001, value=0.5, key=K + "visc"
                    )
        c = st.columns(2)
        values["target_half_life"] = (
            c[0].text_input(
                "Temperature for a half-life of", "", key=K + "th", placeholder="e.g. 1h, 30min"
            )
            or None
        )
        values["target_selectivity"] = (
            c[1].text_input(
                "ΔΔG‡ for a selectivity of", "", key=K + "sel", placeholder="e.g. 95:5, 90% ee"
            )
            or None
        )


def _inputs() -> dict:
    mode = st.segmented_control(
        "Mode", ["reaction", "populations"], default="reaction", key=K + "mode",
        format_func={"reaction": "Reaction (kinetics)",
                     "populations": "Populations (Boltzmann)"}.get,
        label_visibility="collapsed",
    )  # fmt: skip
    values: dict = {"mode": mode or "reaction"}
    populations = values["mode"] == "populations"
    c = st.columns(2)
    with c[0]:
        units = ["kcal/mol", "kJ/mol", "eV"] + (["Eh"] if populations else [])
        values["unit"] = st.selectbox("Energy unit", units, key=K + "unit")
    with c[1]:
        t = st.text_input(
            "Temperature (K)", "298.15", key=K + "T",
            help="A number is in kelvin. With a unit: 40 C, -78 °C.",
        )  # fmt: skip
        values["temperature"] = t.strip() or "298.15"

    if populations:
        values["states"] = st.text_area(
            "States: label, energy, optional degeneracy and properties",
            DEFAULT_STATES, key=K + "states", height=200,
            help="One state per line; paste columns from a spreadsheet. A header line is fine.",
        )  # fmt: skip
    else:
        ts_title, product_title = _value_titles(
            {**values, **{k: st.session_state.get(K + k2) for k, k2 in
                          (("ts_values", "tsv"), ("product_values", "pv"))}}
        )  # fmt: skip
        st.caption("A → TS → product, energies relative to A (0). Paste rows from a spreadsheet.")
        rows = st.data_editor(
            DEFAULT_PATHS, key=K + "paths", num_rows="dynamic", width="stretch",
            column_config={
                "name": st.column_config.TextColumn("Product"),
                "ts": st.column_config.TextColumn(ts_title),
                "product": st.column_config.TextColumn(product_title),
            },
        )  # fmt: skip
        values["paths"] = paths_text(rows)
    if not populations:
        _more_options(values)
    return values


def _results(spec: ToolSpec, values: dict) -> None:
    try:
        inp = ProfileInput(**values)
        outcome = run_tool(spec, inp, workdir=Path(tempfile.mkdtemp(prefix="csk-profile-")))
    except ValidationError as e:
        st.error("; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()))
        return
    except (ToolError, RunError) as e:
        st.info(str(e))
        return
    result = outcome.result
    # The drawing (with its formulas) first, then the answer and the tables.
    drawings = [a for a in result.artifacts if a.kind == "svg" and Path(a.path).exists()]
    for a in drawings:
        st.image(Path(a.path).read_text(encoding="utf-8"), width="stretch")
    rest = [a for a in result.artifacts if a not in drawings]
    render_result(result.model_copy(update={"artifacts": rest}), key="profile-live")


def render(spec: ToolSpec) -> None:
    left, right = st.columns([2, 3], gap="large")
    with left:
        values = _inputs()
    with right:
        _results(spec, values)
