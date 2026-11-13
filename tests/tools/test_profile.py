import importlib.util
from pathlib import Path

import pytest

from chemsidekick.core.schemas import ToolError
from chemsidekick.core.solvents import load as load_solvents
from chemsidekick.tools.energetics.profile import ProfileInput, profile

ROOT = Path(__file__).resolve().parents[2]


def run(**kw):
    return profile(ProfileInput(**kw))


def path(result, label: str) -> dict:
    return next(p for p in result.data["paths"] if p["label"] == label)


def table(result, title: str):
    return next(t for t in result.tables if t.title.startswith(title))


# Expected values: plan 005 §4.8 (298.15 K, from the SI defining constants).
def test_two_paths_kinetic_and_equilibrium_ratios():
    r = run(paths="B 20.0 -3.0\nC 22.0 -5.0")
    assert r.answer == (
        "Kinetic B : C = 96.7 : 3.3 · Equilibrium B : C = 3.3 : 96.7 · "
        "kinetic product B, thermodynamic product C"
    )
    b = path(r, "B")
    assert b["k"] == pytest.approx(1.358815004787466e-2, rel=1e-9)
    assert b["half_life_s"] == pytest.approx(51.0, rel=2e-3)
    assert b["t90_s"] == pytest.approx(169.45537728693216, rel=1e-9)
    assert path(r, "B")["K"] == pytest.approx(158.1303601076713, rel=1e-9)  # ΔG = −3.0
    assert r.data["kinetic_percent"]["B"] == pytest.approx(96.69, abs=0.01)
    assert any("Curtin–Hammett" in a for a in r.assumptions)
    svg = r.artifacts[0].path.read_text()
    assert svg.startswith("<svg") and "TS→B" in svg and "csk-backdrop" in svg


def test_paths_with_the_same_product_add_up():
    r = run(paths="B 20.0 -3\nB 20.0 -3\nC 20.0 -5")
    assert r.data["kinetic_percent"]["B"] == pytest.approx(200 / 3)


def test_only_a_barrier():
    r = run(paths="B 22.0 -")
    assert r.answer == "k = 4.65 × 10⁻⁴ s⁻¹ · t½ = 24.9 min · 99 % done in 2.75 h"
    assert path(r, "B")["K"] is None


def test_only_a_product_energy():
    r = run(paths="B - -1.0")
    assert r.answer == "K = 5.41 (84.4 % B at equilibrium)"
    assert not any(t.title == "Rates" for t in r.tables)


def test_one_path_tells_what_follows_from_it():
    r = run(paths="B 20.0 -3.0")
    assert r.answer == (
        "k = 0.0136 s⁻¹ · t½ = 51.0 s · 99 % done in 5.65 min · K = 158 (99.4 % B at equilibrium)"
    )
    values = {h.label: h.value for h in r.highlights}
    assert values["90 % / 99 % done"] == "2.82 min / 5.65 min"
    assert values["10 °C warmer"] == "3.09× faster"
    eq = next(t for t in r.tables if t.title == "Equilibria")
    assert eq.rows[0][3:] == ["99.4", "23.0", "2.24 h"]  # % at eq., reverse ΔG‡, reverse t½
    practical = next(t for t in r.tables if t.title.startswith("Temperature for a half-life"))
    assert practical.rows[0] == ["B", "24 °C", "-8 °C", "-28 °C"]


def test_half_life_and_rate_constant_inputs_give_the_barrier():
    by_t = run(paths="B 1h -", ts_values="half-life")
    assert path(by_t, "B")["barrier"] == pytest.approx(22.521998015208244, rel=1e-9)
    assert path(by_t, "B")["barrier_entered"] is False
    by_k = run(paths="B 0.01358815004787466 -", ts_values="rate constant")
    assert path(by_k, "B")["barrier"] == pytest.approx(20.0, rel=1e-9)


def test_equilibrium_constant_input():
    r = run(paths="B - 158.1303601076713", product_values="equilibrium constant")
    assert path(r, "B")["energy"] == pytest.approx(-3.0, rel=1e-9)


def test_units():
    kcal = path(run(paths="B 20.0 -"), "B")["k"]
    kj = path(run(paths="B 83.68 -", unit="kJ/mol"), "B")["k"]
    assert kj == pytest.approx(kcal, rel=1e-9)


def test_temperature_with_unit():
    a = path(run(paths="B 20 -", temperature="25 C"), "B")["k"]
    assert a == pytest.approx(path(run(paths="B 20 -"), "B")["k"])


def test_targets():
    r = run(paths="B 23.0 -", target_half_life="1h", target_selectivity="90% ee")
    rows = table(r, "Targets").rows
    assert rows[0] == ["t½ = 1h via B", "304.3 K (31.2 °C)"]
    assert rows[1] == ["Selectivity 90% ee", "ΔΔG‡ = 1.74 kcal/mol"]
    r = run(paths="B 23.0 -", target_selectivity="99:1")
    assert table(r, "Targets").rows[0][1] == "ΔΔG‡ = 2.72 kcal/mol"


def test_wigner_tunneling():
    r = run(paths="B 20 - 1000")
    assert path(r, "B")["kappa"] == pytest.approx(1.9702999975616726, rel=1e-9)
    assert any("Wigner" in a for a in r.assumptions)


def test_diffusion_control_in_water():
    r = run(paths="B 5.0 -", molecularity="bimolecular", control="diffusion", solvent="water")
    b = path(r, "B")
    assert b["k_diff"] == pytest.approx(7.4276e9, rel=1e-4)
    assert b["k"] == pytest.approx(1.1377e9, rel=1e-4)
    assert r.data["diffusion_limit"] == pytest.approx(3.987, abs=1e-3)
    assert table(r, "Activation and diffusion").rows[0][3] == "activation"  # k_act/k_diff = 0.18
    assert r.data["k_unit"] == "M⁻¹ s⁻¹"
    r = run(paths="B 4.0 -", molecularity="bimolecular", control="diffusion")
    assert table(r, "Activation and diffusion").rows[0][3] == "both"  # 7.3 vs 7.4 × 10⁹
    r = run(paths="B 2.0 -", molecularity="bimolecular", control="diffusion")
    assert table(r, "Activation and diffusion").rows[0][3] == "diffusion"


def test_diffusion_needs_bimolecular_and_custom_needs_viscosity():
    with pytest.raises(ToolError, match="bimolecular"):
        run(paths="B 5 -", control="diffusion")
    with pytest.raises(ToolError, match="viscosity"):
        run(paths="B 5 -", molecularity="bimolecular", control="diffusion", solvent="custom")
    r = run(
        paths="B 5 -",
        molecularity="bimolecular",
        control="diffusion",
        solvent="custom",
        viscosity=0.89,
    )
    assert path(r, "B")["k_diff"] == pytest.approx(7.4276e9, rel=1e-3)


def test_one_atm_energies_are_shifted_for_bimolecular_steps():
    r = run(paths="B 20.0 -", molecularity="bimolecular", standard_state="1 atm")
    assert path(r, "B")["barrier"] == pytest.approx(20.0 - 1.8943284454941451, rel=1e-9)
    r = run(paths="B 20.0 -", standard_state="1 atm")  # unimolecular: no shift
    assert path(r, "B")["barrier"] == pytest.approx(20.0)


def test_pseudo_first_order_half_life():
    one = path(run(paths="B 15 -", molecularity="bimolecular"), "B")["half_life_s"]
    tenth = path(run(paths="B 15 -", molecularity="bimolecular", partner=0.1), "B")
    assert tenth["half_life_s"] == pytest.approx(10 * one)


def test_warnings():
    r = run(paths="B -1 -", molecularity="bimolecular")
    assert any("negative" in w for w in r.warnings)
    assert any("diffusion" in w for w in r.warnings)
    assert any("below the product" in w for w in run(paths="B 2 5").warnings)


@pytest.mark.parametrize(
    ("paths", "message"),
    [
        ("", "at least one path"),
        ("B - -", "TS value, a product value"),
        ("B abc -", "cannot read the barrier"),
        ("B 1 2 3 4", "expected"),
    ],
)
def test_bad_paths(paths, message):
    with pytest.raises(ToolError, match=message):
        run(paths=paths)


def test_hartree_only_for_populations():
    with pytest.raises(ToolError, match="populations"):
        run(paths="B 0.03 -", unit="Eh")


# ---------------------------------------------------------------------------
# Populations
# ---------------------------------------------------------------------------


def test_populations():
    r = run(mode="populations", states="conf1 0\nconf2 0.5\nconf3 1.0")
    assert r.answer == "conf1 61.9 % · 3 of 3 states cover 95 %"
    pct = [s["percent"] for s in r.data["states"]]
    assert pct == pytest.approx([61.92129092, 26.62793318, 11.45077590])
    assert table(r, "Populations").rows[-1][3] == "100.0"
    assert r.artifacts[0].path.name == "populations.svg"


def test_populations_from_absolute_hartree_with_degeneracy_and_properties():
    states = (
        "name  E      g  shift\n"
        "c1  -1234.000000  1  3.40\n"
        "c2  -1233.999203  2  3.60\n"  # +0.5 kcal/mol
    )
    r = run(mode="populations", states=states, unit="Eh")
    pct = [s["percent"] for s in r.data["states"]]
    assert pct == pytest.approx([53.76, 46.24], abs=0.02)
    assert r.data["unit"] == "kcal/mol"
    assert r.data["averages"]["shift"] == pytest.approx(0.5376 * 3.40 + 0.4624 * 3.60, abs=1e-3)


def test_populations_need_states_and_unique_labels():
    with pytest.raises(ToolError, match="Give the states"):
        run(mode="populations")
    with pytest.raises(ToolError, match="different"):
        run(mode="populations", states="a 0\na 1")


# ---------------------------------------------------------------------------
# Solvent data
# ---------------------------------------------------------------------------


def test_solvents_are_verified_and_report_is_current():
    data = load_solvents()
    assert set(data.solvents) == {"water", "methanol", "toluene", "benzene"}
    for s in data.solvents.values():
        assert data.agreeing(s) >= 3, s.id
    spec = importlib.util.spec_from_file_location(
        "build_solvents_report", ROOT / "scripts/build_solvents_report.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert (ROOT / "data/verification/solvents.md").read_text(encoding="utf-8") == mod.report()


def test_solvent_choices_match_the_data():
    from typing import get_args

    from chemsidekick.tools.energetics.profile import SolventChoice

    assert set(get_args(SolventChoice)) == set(load_solvents().solvents) | {"custom"}


def test_low_barrier_is_computed_but_flagged_as_qualitative():
    r = run(paths="B 20.0 -3.0\nP2 1.0 -14")
    assert path(r, "P2")["k"] is not None  # still computed
    (warning,) = [w for w in r.warnings if w.startswith("Low barrier")]
    assert "(P2)" in warning and "5RT = 3.0 kcal/mol" in warning and "qualitative" in warning
    assert not any(w.startswith("Low barrier") for w in run(paths="B 20.0 -3.0").warnings)


def test_formulas_are_drawn_under_the_diagram():
    for r in (run(paths="B 20.0 -3.0"), run(mode="populations", states="a 0\nb 1")):
        assert [a.kind for a in r.artifacts] == ["svg"]  # one card: diagram + formulas
        assert r.formulas and all(f.in_drawing for f in r.formulas)
        svg = r.artifacts[0].path.read_text()
        assert "#e5e7eb" in svg  # the divider
        assert "<use" not in svg  # glyphs as paths (macOS renderer)


def test_populations_mark_the_states_that_make_up_95_percent():
    r = run(mode="populations", states="conf1 0\nconf2 0.3\nconf3 0.8\nconf4 1.2\nconf5 2.5")
    states = {s["label"]: s for s in r.data["states"]}
    assert r.data["top_95_count"] == 4
    assert [label for label, s in states.items() if not s["in_top_95"]] == ["conf5"]
    assert states["conf1"]["percent_text"] == "49.8"
    assert r.answer == "conf1 49.8 % · 4 of 5 states cover 95 %"  # CLI answer unchanged
