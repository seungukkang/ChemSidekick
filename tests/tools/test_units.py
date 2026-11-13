import pytest

from chemsidekick.core.schemas import ToolError
from chemsidekick.tools.reference.units import UnitsInput, units


def run(query: str | None = None, **kw):
    return units(UnitsInput(query=query, **kw))


def table(result, title: str):
    return next(t for t in result.tables if t.title.startswith(title))


def test_conversion_answer_and_result_data():
    r = run("1 eV to kcal/mol")
    assert r.answer == "1 eV = 23.0605 kcal/mol"
    assert r.highlights[0].label == "kcal/mol" and r.highlights[0].value == "23.0605"
    assert r.data["result"]["value"] == pytest.approx(23.06054783061903, rel=1e-12)
    assert r.data["result"]["exact"] is True


def test_measured_constant_makes_answer_approximate():
    r = run("1 Eh to kcal/mol")
    assert r.answer == "1 Eh ≈ 627.509 kcal/mol"
    assert r.data["result"]["exact"] is False
    assert any("CODATA" in s for s in r.sources)


def test_overview_lists_group_and_equivalents():
    r = run("1 Hartree")
    assert r.answer.startswith("1 Eh ≈ 627.509 kcal/mol")
    energy = table(r, "Energy")
    assert ["kcal/mol", "627.509", "≈"] in energy.rows
    eq = table(r, "Energy equivalents")
    assert any(row[0] == "cm⁻¹" and row[1] == "219475" for row in eq.rows)
    assert table(r, "Thermal energy at 298.15 K")


def test_wavelength_input_shows_energy_and_length():
    r = run("300 nm")
    assert table(r, "Energy equivalents")
    assert table(r, "Energy")
    assert table(r, "Length")  # nm is also a length


def test_temperature_option_changes_rt():
    r = run("1 eV", temperature="25 C")
    assert r.highlights[0].label == "RT at 298.15 K"
    r = run("1 eV", temperature="373.15")
    # RT = 0.5924849497 kcal/mol × 373.15 / 298.15
    assert table(r, "Thermal energy at 373.15 K").rows[0][1] == "0.741525"


def test_uncommon_units_hidden_unless_asked_or_typed():
    shown = [row[0] for row in table(run("1 bar"), "Pressure").rows]
    assert "MPa" not in shown and "mTorr" not in shown
    shown = [row[0] for row in table(run("1 bar", show_all=True), "Pressure").rows]
    assert "MPa" in shown and "mTorr" in shown
    shown = [row[0] for row in table(run("5 mTorr"), "Pressure").rows]
    assert "mTorr" in shown


def test_unit_lists():
    everything = run()
    assert everything.answer.startswith("All units")
    assert len(everything.tables) == 10
    assert run("pressure").answer.startswith("Pressure ·")
    au = run("atomic units")
    assert au.answer.startswith("Atomic units")
    assert [t.title.split(" (")[0] for t in au.tables] == [
        "Length",
        "Dipole moment",
        "Polarizability",
    ]


def test_notes_explain_torr_and_calorie():
    assert any("Torr" in n for n in run("1 atm").notes)
    assert any("thermochemical calorie" in n for n in run("1 kcal/mol").notes)


def test_errors_are_user_errors():
    with pytest.raises(ToolError, match="Unknown unit"):
        run("5 foo")
    with pytest.raises(ToolError, match="Cannot convert"):
        run("1 eV to bar")
    with pytest.raises(ToolError, match="absolute zero"):
        run("1 eV", temperature="-300 C")


def test_case_warning():
    r = run("1 KCAL/MOL to kJ/mol")
    assert r.warnings and "kcal/mol" in r.warnings[0]
