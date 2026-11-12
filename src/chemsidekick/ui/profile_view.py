"""Streamlit view for the energy profile (ENE-01).

Inputs sit above the drawing, in the same columns as the states they belong
to (reactant | transition states | products), and every change redraws the
profile at once: Streamlit reruns this script on each input change, and the
calculation takes milliseconds.
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
DEFAULT_PATHS = [("B", "20.0", "-3.0"), ("C", "22.0", "-5.0")]
DEFAULT_STATES = "conf1  0.0\nconf2  0.5\nconf3  1.0\n"
MAX_PATHS = 6


def _segmented(label: str, options: list[str], key: str, default: str) -> str:
    value = st.segmented_control(label, options, default=default, key=K + key)
    return value or default


def _paths_editor() -> str:
    n = st.session_state.setdefault(K + "n", len(DEFAULT_PATHS))
    head = st.columns([1, 1, 1])
    head[0].markdown("**A** · reactant, 0")
    head[1].markdown("**Transition state**")
    head[2].markdown("**Product**")
    lines = []
    for i in range(n):
        label0, ts0, p0 = DEFAULT_PATHS[i] if i < len(DEFAULT_PATHS) else (f"P{i + 1}", "", "")
        c = st.columns([1, 1, 1])
        label = c[0].text_input("Product name", label0, key=f"{K}label-{i}",
                                label_visibility="collapsed", placeholder="name")  # fmt: skip
        ts = c[1].text_input("TS", ts0, key=f"{K}ts-{i}", label_visibility="collapsed",
                             placeholder="TS (leave empty if unknown)")  # fmt: skip
        product = c[2].text_input("Product", p0, key=f"{K}p-{i}", label_visibility="collapsed",
                                  placeholder="product (leave empty if unknown)")  # fmt: skip
        if ts.strip() or product.strip():
            name = (label.strip() or f"P{i + 1}").replace(" ", "_")
            lines.append(f"{name}\t{ts.strip() or '-'}\t{product.strip() or '-'}")
    b = st.columns([1, 1, 4])
    if b[0].button("Add path", key=K + "add", disabled=n >= MAX_PATHS):
        st.session_state[K + "n"] = n + 1
        st.rerun()
    if b[1].button("Remove last", key=K + "remove", disabled=n <= 1):
        st.session_state[K + "n"] = n - 1
        st.rerun()
    return "\n".join(lines)


def render(spec: ToolSpec) -> None:
    mode = _segmented("Mode", ["reaction", "populations"], "mode", "reaction")
    values: dict = {"mode": mode}

    top = st.columns([1, 1, 1])
    with top[0]:
        units = ["kcal/mol", "kJ/mol", "eV"] + (["Eh"] if mode == "populations" else [])
        values["unit"] = _segmented("Energy unit", units, "unit", "kcal/mol")
    with top[1]:
        values["temperature"] = st.text_input(
            "Temperature", "298.15", key=K + "T", help="A number in K, or 25 C, -78 °C."
        )
    if mode == "reaction":
        with top[2]:
            values["molecularity"] = _segmented(
                "Molecularity", ["unimolecular", "bimolecular"], "mol", "unimolecular"
            )
        row = st.columns([1, 1, 1])
        with row[0]:
            values["ts_values"] = _segmented(
                "TS values are", ["barrier", "rate constant", "half-life"], "tsv", "barrier"
            )
        with row[1]:
            values["product_values"] = _segmented(
                "Product values are", ["free energy", "equilibrium constant"], "pv", "free energy"
            )
        with row[2]:
            values["standard_state"] = _segmented("Energies are for", ["1 M", "1 atm"], "ss", "1 M")
        if values["molecularity"] == "bimolecular":
            row = st.columns([1, 1, 1])
            with row[0]:
                values["control"] = _segmented(
                    "Control", ["activation", "diffusion"], "ctl", "activation"
                )
            with row[1]:
                values["partner"] = st.number_input(
                    "Partner concentration (M)", min_value=0.001, value=1.0, key=K + "conc",
                    help="The other reactant, for pseudo-first-order half-lives.",
                )  # fmt: skip
            if values["control"] == "diffusion":
                names = {s.id: s.name for s in load_solvents().solvents.values()}
                row = st.columns([1, 1, 1])
                with row[0]:
                    values["solvent"] = st.selectbox(
                        "Solvent (25 °C)", list(get_args(SolventChoice)), key=K + "solv",
                        format_func=lambda c: names.get(c, "Other (type its viscosity)"),
                    )  # fmt: skip
                if values["solvent"] == "custom":
                    with row[1]:
                        values["viscosity"] = st.number_input(
                            "Viscosity (mPa s)", min_value=0.001, value=0.5, key=K + "visc"
                        )
        st.divider()
        values["paths"] = _paths_editor()
        with st.expander("Targets"):
            t = st.columns(2)
            values["target_half_life"] = (
                t[0].text_input(
                    "Temperature for a half-life of", "", key=K + "th", placeholder="e.g. 1h, 30min"
                )
                or None
            )
            values["target_selectivity"] = (
                t[1].text_input(
                    "ΔΔG‡ for a selectivity of", "", key=K + "sel", placeholder="e.g. 95:5, 90% ee"
                )
                or None
            )
    else:
        values["states"] = st.text_area(
            "States: label, energy, optional degeneracy and properties (paste from a spreadsheet)",
            DEFAULT_STATES, key=K + "states", height=160,
        )  # fmt: skip

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
    # The drawing is the main content: full width, right under the inputs.
    drawings = [a for a in result.artifacts if a.kind == "svg" and Path(a.path).exists()]
    for a in drawings:
        st.image(Path(a.path).read_text(encoding="utf-8"), width="stretch")
    rest = [a for a in result.artifacts if a not in drawings]
    render_result(result.model_copy(update={"artifacts": rest}), key="profile-live")
