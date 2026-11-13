import importlib.util
import math
from itertools import combinations
from pathlib import Path

import pytest

from chemsidekick.core import units as U

ROOT = Path(__file__).resolve().parents[2]


def conv(value: float, source: str, target: str) -> float:
    s, t = U.pair(U.find_unit(source), U.find_unit(target))
    return U.convert(value, s, t)


# Expected values: computed from the SI defining constants and CODATA 2022 (plan 005 §5A.10).
@pytest.mark.parametrize(
    ("value", "source", "target", "expected"),
    [
        (1, "Eh", "kcal/mol", 627.5094740628974),
        (1, "Eh", "kJ/mol", 2625.499639479163),
        (1, "Eh", "eV", 27.211386245981167),
        (1, "eV", "kcal/mol", 23.06054783061903),
        (1, "eV", "cm-1", 8065.543937349212),
        (1, "eV", "K", 11604.518121550082),
        (1, "kcal/mol", "cm-1", 349.75508806603676),
        (1, "eV", "nm", 1239.8419843320025),
        (1239.8419843320025, "nm", "eV", 1.0),
        (1, "M-1 s-1", "cm3 molecule-1 s-1", 1.6605390671738467e-21),
        (1, "D", "C m", 3.33564095198152e-30),
        (1, "D", "e Å", 0.20819433270935594),
        (1, "Torr", "Pa", 101325 / 760),
        (1, "atm", "Torr", 760),
        (1, "atm", "bar", 1.01325),
        (1, "mmHg", "Pa", 133.322387415),
        (1, "psi", "Pa", 6894.757293168361),
        (1, "mAh", "C", 3.6),
        (1, "Ah", "mol e-", 3600 / 96485.33212331001),
        (10, "cal/(mol K)", "J/(mol K)", 41.84),
        (1, "nm", "Å", 10),
        (1, "bohr", "Å", 0.529177210544),
        (1, "au", "C m", 8.4783536198e-30),
        (1, "bohr3", "C m2/V", 1.64877727212e-41),
        (1, "M", "molecule/cm3", 6.02214076e20),
    ],
)
def test_reference_conversions(value, source, target, expected):
    assert conv(value, source, target) == pytest.approx(expected, rel=1e-9)


def test_every_pair_in_a_group_round_trips():
    data = U.load()
    for group in data.groups:
        for a, b in combinations(data.in_group(group), 2):
            back = U.convert(U.convert(2.5, a, b), b, a)
            assert back == pytest.approx(2.5, rel=1e-12), (a.symbol, b.symbol)


def test_energy_and_equivalents_round_trip():
    data = U.load()
    for a in data.in_group("energy"):
        for b in data.in_group("equivalents"):
            assert U.convert(U.convert(3.0, a, b), b, a) == pytest.approx(3.0, rel=1e-12)


def test_exactness_follows_the_constants():
    data = U.load()
    assert data.unit("energy", "eV").exact
    assert data.unit("energy", "kcal/mol").exact
    assert not data.unit("energy", "Eh").exact
    assert not data.unit("length", "bohr").exact
    assert data.unit("pressure", "psi").exact
    assert data.unit("equivalents", "nm").exact  # E = hc/λ uses only h and c


@pytest.mark.parametrize(
    "spelling", ["M-1 s-1", "M^-1 s^-1", "M⁻¹s⁻¹", "M⁻¹ s⁻¹", "M-1s-1", "/M/s", "L mol-1 s-1"]
)
def test_spellings_of_one_unit(spelling):
    assert U.find_unit(spelling).units[0].symbol == "M⁻¹ s⁻¹"


@pytest.mark.parametrize(
    ("spelling", "symbol"),
    [
        ("Å", "Å"),
        ("Å", "Å"),
        ("angstrom", "Å"),
        ("µM", "μM"),
        ("uM", "μM"),
        ("e.u.", "cal/(mol K)"),
    ],
)
def test_aliases_and_look_alike_characters(spelling, symbol):
    assert U.find_unit(spelling).units[0].symbol == symbol


def test_case_mistake_is_corrected_and_reported():
    lk = U.find_unit("KCAL/MOL")
    assert lk.units[0].symbol == "kcal/mol" and lk.corrected == "kcal/mol"
    assert U.find_unit("kcal/mol").corrected == ""


def test_unknown_unit_suggests():
    with pytest.raises(U.UnitError, match="Did you mean: kcal/mol"):
        U.find_unit("kcal/mo")


def test_nm_has_two_meanings_resolved_by_target():
    assert {u.group for u in U.find_unit("nm").units} == {"equivalents", "length"}
    s, t = U.pair(U.find_unit("nm"), U.find_unit("eV"))
    assert s.group == "equivalents"
    s, t = U.pair(U.find_unit("nm"), U.find_unit("pm"))
    assert s.group == "length"


def test_cannot_convert_between_groups():
    with pytest.raises(U.UnitError, match="Cannot convert eV"):
        U.pair(U.find_unit("eV"), U.find_unit("bar"))


def test_wavelength_needs_positive_values():
    with pytest.raises(U.UnitError, match="positive"):
        conv(-3, "nm", "eV")
    with pytest.raises(U.UnitError, match="positive energy"):
        conv(-1, "eV", "nm")


@pytest.mark.parametrize(
    ("text", "value", "rest"),
    [
        ("1.2e-3 M", 1.2e-3, "M"),
        ("1.2×10⁻³ M", 1.2e-3, "M"),
        ("1.2*10^-3 M", 1.2e-3, "M"),
        ("1.2 x 10^-3 M", 1.2e-3, "M"),
        ("−5 kcal/mol", -5, "kcal/mol"),
        ("1 eV", 1, "eV"),  # the e of eV is not an exponent
        ("2 e", 2, "e"),
        (".5 bar", 0.5, "bar"),
        ("kcal/mol", None, "kcal/mol"),
    ],
)
def test_parse_number(text, value, rest):
    v, r = U.parse_number(text)
    assert r == rest
    assert v == (pytest.approx(value) if value is not None else None)


@pytest.mark.parametrize("sep", [" to ", " in ", " -> ", "→", " TO "])
def test_query_separators(sep):
    q = U.parse_query(f"2 eV{sep}kcal/mol")
    assert q.value == 2 and q.target is not None and q.target.units[0].symbol == "kcal/mol"


def test_query_without_number_means_one():
    q = U.parse_query("kcal/mol")
    assert q.value == 1 and q.target is None


@pytest.mark.parametrize(
    ("text", "kelvin"),
    [
        ("298.15", 298.15),
        ("25 C", 298.15),
        ("25 °C", 298.15),
        ("25C", 298.15),
        ("-78 °C", 195.15),
        ("77 F", 298.15),
        ("300 K", 300),
        (310.0, 310.0),
    ],
)
def test_parse_temperature(text, kelvin):
    assert U.parse_temperature(text) == pytest.approx(kelvin)


@pytest.mark.parametrize("text", ["-300 C", "0", "-5", "hot", "25 X"])
def test_bad_temperature(text):
    with pytest.raises(U.UnitError):
        U.parse_temperature(text)


@pytest.mark.parametrize(
    ("x", "text"),
    [
        (627.5094740628974, "627.509"),
        (760.0, "760"),
        (1.0, "1"),
        (0.0367493, "0.0367493"),
        (4.3597447222060e-18, "4.35974 × 10⁻¹⁸"),
        (2.0e9, "2 × 10⁹"),
        (999999.7, "1 × 10⁶"),
        (0, "0"),
        (-23.06054783, "-23.0605"),
    ],
)
def test_format_number(x, text):
    assert U.format_number(x) == text


@pytest.mark.parametrize("expr", ["__import__('os')", "a.b", "f(1)", "[1]"])
def test_expressions_are_restricted(expr):
    with pytest.raises(ValueError):
        U.evaluate(expr, {})


def test_every_group_has_units_and_valid_headline():
    data = U.load()
    for gid, group in data.groups.items():
        assert data.in_group(gid), gid
        for symbol in group.headline:
            assert any(U.family(u) == group.family for u in U.find_unit(symbol).units), (
                gid,
                symbol,
            )
    for u in data.units:
        assert math.isfinite(u.factor) and u.factor > 0, u.symbol


def test_measured_constants_are_verified_and_report_is_current():
    spec = importlib.util.spec_from_file_location(
        "build_units_report", ROOT / "scripts/build_units_report.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for c in U.load().constants.values():
        assert mod.status(c) in ("verified", "definition"), c.key
    assert (ROOT / "data/verification/units.md").read_text(encoding="utf-8") == mod.report(), (
        "run: uv run python scripts/build_units_report.py"
    )
