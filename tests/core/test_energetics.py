import math

import pytest

from chemsidekick.core import energetics as E
from chemsidekick.core.schemas import ToolError
from chemsidekick.core.tabular import parse_table
from chemsidekick.core.units import (
    UnitError,
    format_duration,
    from_molar_energy,
    molar_energy,
    parse_duration,
)

T = 298.15
KCAL = 4184.0  # J/mol per kcal/mol


def kcal(x: float) -> float:
    return x * KCAL


# Expected values: plan 005 §4.8, computed from the SI defining constants.
def test_eyring_rate_and_times():
    k = E.eyring_k(kcal(20.0), T)
    assert k == pytest.approx(1.358815004787466e-2, rel=1e-9)
    assert E.half_life(k) == pytest.approx(51.0, rel=2e-3)
    assert E.time_to_conversion(k, 90) == pytest.approx(169.45537728693216, rel=1e-9)
    assert E.time_to_conversion(k, 99) == pytest.approx(338.9107545738643, rel=1e-9)
    assert E.eyring_k(kcal(22.0), T) == pytest.approx(4.647e-4, rel=1e-3)


def test_barrier_from_half_life():
    k = E.k_from_half_life(3600)
    assert E.dg_act_from_k(k, T) / KCAL == pytest.approx(22.521998015208244, rel=1e-9)


@pytest.mark.parametrize(("dg", "kelvin"), [(23.0, 304.3140486221854), (25.0, 330.0710329337486)])
def test_temperature_for_one_hour_half_life(dg, kelvin):
    assert E.temperature_for_half_life(kcal(dg), 3600) == pytest.approx(kelvin, abs=1e-6)


def test_temperature_out_of_range():
    with pytest.raises(ValueError):
        E.temperature_for_half_life(kcal(1000.0), 1.0)  # too slow even at 5000 K


def test_round_trips():
    assert E.dg_act_from_k(E.eyring_k(kcal(17.3), 310.0), 310.0) == pytest.approx(kcal(17.3))
    assert E.dg_from_k_eq(E.k_eq(kcal(-2.2), T), T) == pytest.approx(kcal(-2.2))
    assert E.ddg_from_ratio(E.ratio_from_ddg(kcal(1.4), T), T) == pytest.approx(kcal(1.4))


def test_selectivity():
    r = E.ratio_from_ddg(kcal(2.0), T)
    assert r == pytest.approx(29.24, rel=1e-3)
    assert r / (1 + r) * 100 == pytest.approx(96.69, abs=0.01)
    assert E.ratio_from_ddg(kcal(2.0), 195.15) == pytest.approx(173.7, rel=1e-3)
    assert E.ddg_from_ratio(E.ee_to_ratio(90), T) / KCAL == pytest.approx(1.7445357805066746)
    assert E.ddg_from_ratio(99, T) / KCAL == pytest.approx(2.723, rel=1e-3)
    assert E.ratio_to_ee(19) == pytest.approx(90)


def test_equilibrium_constants():
    assert E.k_eq(kcal(-1.0), T) == pytest.approx(5.40760656536583, rel=1e-9)
    assert E.k_eq(kcal(-3.0), T) == pytest.approx(158.1303601076713, rel=1e-9)


def test_populations():
    p = E.populations([0, kcal(0.5), kcal(1.0)], T)
    assert [x * 100 for x in p] == pytest.approx([61.92129092, 26.62793318, 11.45077590])
    p = E.populations([0, kcal(0.5)], T, degeneracy=[1, 2])
    assert [x * 100 for x in p] == pytest.approx([53.76178088, 46.23821912])


def test_populations_ignore_a_common_offset():
    # Absolute energies (e.g. hartree in J/mol, about -3e9) give the same result.
    offset = -1234.5 * 2625499.639
    shifted = E.populations([offset, offset + kcal(0.5)], T)
    assert shifted == pytest.approx(E.populations([0, kcal(0.5)], T))


def test_wigner_kappa():
    assert E.wigner_kappa(1000, T) == pytest.approx(1.9702999975616726, rel=1e-9)
    assert E.wigner_kappa(-1000, T) == E.wigner_kappa(1000, T)


def test_diffusion_in_water():
    kd = E.k_diffusion(T, 0.8900e-3)
    assert kd == pytest.approx(7427586605.550228, rel=1e-9)
    ka = E.eyring_k(kcal(5.0), T)
    assert E.k_observed(ka, kd) == pytest.approx(1137708800.9529667, rel=1e-9)
    assert E.dg_act_from_k(kd, T) / KCAL == pytest.approx(3.986895037679041, rel=1e-9)


def test_standard_state_shift():
    assert E.standard_state_shift(T) / KCAL == pytest.approx(1.8943284454941451, rel=1e-9)
    assert E.standard_state_shift(T, 2) == pytest.approx(2 * E.standard_state_shift(T))


def test_bad_inputs():
    for call in (
        lambda: E.dg_act_from_k(0, T),
        lambda: E.k_from_half_life(-1),
        lambda: E.time_to_conversion(1, 100),
        lambda: E.populations([0, 1], T, degeneracy=[1, 0]),
        lambda: E.k_diffusion(T, 0),
        lambda: E.ee_to_ratio(100),
    ):
        with pytest.raises(ValueError):
            call()


# ---------------------------------------------------------------------------
# Inputs: energies, durations, pasted tables
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "unit", "joule_per_mol"),
    [
        (1, "kcal/mol", 4184.0),
        (1, "kJ/mol", 1000.0),
        (1, "eV", 96485.33212331001),
        (1, "Eh", 2625499.639479163),
    ],
)
def test_molar_energy(value, unit, joule_per_mol):
    assert molar_energy(value, unit) == pytest.approx(joule_per_mol, rel=1e-12)
    assert from_molar_energy(joule_per_mol, unit) == pytest.approx(value, rel=1e-12)


def test_molar_energy_rejects_other_units():
    with pytest.raises(UnitError, match="not an energy unit"):
        molar_energy(1, "bar")


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("51", 51), ("30 s", 30), ("5 min", 300), ("1 h", 3600), ("2 d", 172800), ("1.5 hours", 5400)],
)
def test_parse_duration(text, seconds):
    assert parse_duration(text) == pytest.approx(seconds)


@pytest.mark.parametrize("text", ["0", "-5 s", "soon", "5 parsecs"])
def test_bad_duration(text):
    with pytest.raises(UnitError):
        parse_duration(text)


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (51.0, "51 s"),
        (1492, "24.9 min"),
        (3600 * 5, "5 h"),
        (86400 * 4.6, "4.6 d"),
        (3.2e8, "10.1 yr"),
    ],
)
def test_format_duration(seconds, text):
    assert format_duration(seconds) == text


def test_parse_table_with_header_labels_and_tabs():
    text = (
        "name\tE(Hartree)\tshift\n"
        "conf1\t-1234.567890\t3.42\n"
        "\n"
        "# a comment\n"
        "conf2\t−1234.567012\t3.61\n"  # Unicode minus
    )
    t = parse_table(text, min_values=1, max_values=2)
    assert t.header == ("name", "E(Hartree)", "shift")
    assert [(r.line, r.label, r.values) for r in t.rows] == [
        (2, "conf1", (-1234.56789, 3.42)),
        (5, "conf2", (-1234.567012, 3.61)),
    ]
    assert t.labeled


@pytest.mark.parametrize("sep", [" ", "  ", ",", ";", "\t"])
def test_parse_table_separators(sep):
    t = parse_table(f"0{sep}1\n0.5{sep}2\n", min_values=2, max_values=2)
    assert [r.values for r in t.rows] == [(0, 1), (0.5, 2)]
    assert not t.labeled


def test_parse_table_scientific_numbers():
    t = parse_table("1.2e-3\n1.2×10⁻³\n")
    assert [r.values[0] for r in t.rows] == pytest.approx([1.2e-3, 1.2e-3])


def test_parse_table_errors_name_the_line():
    with pytest.raises(ToolError, match="Line 2: 'abc' is not a number"):
        parse_table("1\n2 abc\n")
    with pytest.raises(ToolError, match="Line 1: at most 1 numbers"):
        parse_table("1 2\n", max_values=1)
    with pytest.raises(ToolError, match="No rows"):
        parse_table("# only a comment\n\n")


def test_gas_constant():
    assert E.gas_constant() == pytest.approx(8.314462618, rel=1e-9)
    assert math.isclose(E.rt(T) / KCAL, 0.5924849497137639, rel_tol=1e-12)
