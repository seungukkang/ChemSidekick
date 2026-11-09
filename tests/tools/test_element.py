import time

import pytest

from chemsidekick.core.schemas import ToolError
from chemsidekick.tools.reference.element import (
    ElementInput,
    _dataset,
    element,
    find,
    superscript_config,
)


def props(query: str) -> dict[str, object]:
    """The 'Properties' table of an element card, as {property: value}."""
    result = element(ElementInput(query=query))
    return {row[0]: row[1] for row in result.tables[0].rows}


def test_all_118_elements_present_in_order():
    elements = _dataset()["elements"]
    assert len(elements) == 118
    assert [e["z"] for e in elements] == list(range(1, 119))


@pytest.mark.parametrize("query", ["Fe", "fe", "FE", "iron", "Iron", "26", " 26 "])
def test_same_element_from_symbol_name_or_number(query):
    assert find(query)["symbol"] == "Fe"


@pytest.mark.parametrize(
    ("query", "symbol"), [("aluminium", "Al"), ("sulphur", "S"), ("cesium", "Cs")]
)
def test_alternative_spellings(query, symbol):
    assert find(query)["symbol"] == symbol


@pytest.mark.parametrize(
    ("symbol", "config"),
    [
        ("H", "1s1"),
        ("He", "1s2"),
        ("Na", "[Ne] 3s1"),
        ("Ar", "[Ne] 3s2 3p6"),
        ("Fe", "[Ar] 3d6 4s2"),
        # Exceptions to the Aufbau rule must come out right:
        ("Cr", "[Ar] 3d5 4s1"),
        ("Cu", "[Ar] 3d10 4s1"),
        ("Pd", "[Kr] 4d10"),
    ],
)
def test_noble_gas_core_configuration(symbol, config):
    assert find(symbol)["config"] == config


def test_full_configuration_is_sorted_by_n_then_l():
    assert find("Pd")["config_full"] == "1s2 2s2 2p6 3s2 3p6 3d10 4s2 4p6 4d10"
    assert find("Fe")["config_full"] == "1s2 2s2 2p6 3s2 3p6 3d6 4s2"


def test_full_configuration_electron_count_equals_z():
    for el in _dataset()["elements"]:
        electrons = sum(int(tok[2:]) for tok in el["config_full"].split())
        assert electrons == el["z"], el["symbol"]


def test_superscript_display():
    assert superscript_config("[Ar] 3d10 4s1") == "[Ar] 3d¹⁰ 4s¹"


@pytest.mark.parametrize(
    ("symbol", "weight", "en"),
    [("H", 1.008, 2.2), ("C", 12.011, 2.55), ("Fe", 55.845, 1.83), ("Og", 294.0, None)],
)
def test_known_values(symbol, weight, en):
    el = find(symbol)
    assert el["atomic_weight"] == pytest.approx(weight, abs=1e-3)
    assert el["en_pauling"] == en


def test_card_contents():
    fe = props("Fe")
    assert fe["Standard atomic weight"] == "55.845 ± 0.002"
    assert fe["Electron configuration"] == "[Ar] 3d⁶ 4s²"
    assert fe["Group / Period / Block"] == "8 / 4 / d"
    assert fe["Oxidation states (main)"] == "+2, +3"


def test_isotopes_sorted_by_abundance():
    result = element(ElementInput(query="C"))
    isotopes = result.tables[1]
    assert [row[0] for row in isotopes.rows] == ["12C", "13C"]


def test_no_standard_weight_uses_longest_lived_isotope():
    tc = props("Tc")
    assert tc["Standard atomic weight"] == "[97] (no standard atomic weight)"
    result = element(ElementInput(query="Tc"))
    assert result.tables[1].title.startswith("Longest-lived isotope")


def test_typo_suggests_close_match():
    with pytest.raises(ToolError, match=r"Did you mean: Fe \(Iron\)"):
        find("Iorn")


@pytest.mark.parametrize("query", ["0", "119"])
def test_atomic_number_out_of_range(query):
    with pytest.raises(ToolError, match="between 1 and 118"):
        find(query)


def test_periodic_table_layout():
    result = element(ElementInput())
    rows = result.tables[0].rows
    assert len(result.tables[0].columns) == 19
    assert rows[0][1] == "H" and rows[0][18] == "He"
    assert rows[3][8] == "Fe"  # period 4, group 8
    lanthanides = rows[8]
    assert lanthanides[0] == "Ln" and lanthanides[4] == "Ce" and lanthanides[17] == "Lu"


def test_sources_are_reported():
    assert any("mendeleev" in s for s in element(ElementInput(query="H")).sources)


def test_lookup_is_fast():
    _dataset()  # first load
    start = time.perf_counter()
    for q in ["H", "iron", "26", "Og"]:
        element(ElementInput(query=q))
    assert time.perf_counter() - start < 0.1
