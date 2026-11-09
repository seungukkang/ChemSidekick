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
    assert find(symbol)["config"]["value"] == config


def test_full_configuration_is_sorted_by_n_then_l():
    assert find("Pd")["config"]["full"] == "1s2 2s2 2p6 3s2 3p6 3d10 4s2 4p6 4d10"
    assert find("Fe")["config"]["full"] == "1s2 2s2 2p6 3s2 3p6 3d6 4s2"


def test_full_configuration_electron_count_equals_z():
    for el in _dataset()["elements"]:
        electrons = sum(int(tok[2:]) for tok in el["config"]["full"].split())
        assert electrons == el["z"], el["symbol"]


def test_superscript_display():
    assert superscript_config("[Ar] 3d10 4s1") == "[Ar] 3d¹⁰ 4s¹"


@pytest.mark.parametrize(
    ("symbol", "weight", "en"),
    [("He", 4.002602, None), ("C", None, 2.55), ("Fe", 55.845, 1.83)],
)
def test_known_values(symbol, weight, en):
    el = find(symbol)
    assert el["atomic_weight"]["value"] == (pytest.approx(weight) if weight else None)
    assert el["en_pauling"]["value"] == en


def test_card_contents():
    fe = props("Fe")
    assert fe["Standard atomic weight"] == "55.845(2)"
    assert fe["Electron configuration"] == "[Ar] 3d⁶ 4s²"
    assert fe["Group / Period / Block"] == "8 / 4 / d"
    assert fe["Oxidation states (main)"] == "+2, +3"


def test_isotopes_sorted_by_abundance():
    result = element(ElementInput(query="C"))
    isotopes = result.tables[1]
    assert [row[0] for row in isotopes.rows] == ["12C", "13C"]


def test_no_standard_weight_uses_longest_lived_isotope():
    tc = props("Tc")
    assert tc["Standard atomic weight"] == "— (no standard atomic weight)"
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


# --- Verification -------------------------------------------------------------

STATUSES = {"verified", "partial", "definition", "unverified"}


def all_fields(el):
    yield el["atomic_weight"]
    yield el["config"]
    yield el["en_pauling"]
    yield el["covalent_radius_pm"]
    yield el["oxidation_states"]
    for i in el["isotopes"]:
        yield i["mass"]
        yield i["abundance"]
    if el["longest_lived_isotope"]:
        yield el["longest_lived_isotope"]


def test_every_value_has_a_status_and_known_references():
    known = set(_dataset()["meta"]["references"])
    for el in _dataset()["elements"]:
        for f in all_fields(el):
            assert f["status"] in STATUSES
            for key in f["refs"] + f.get("agree", []):
                assert key == "mendeleev" or key in known, key


def test_verified_means_primary_plus_two_compilations():
    refs = _dataset()["meta"]["references"]
    for el in _dataset()["elements"]:
        for f in all_fields(el):
            if f["status"] == "verified":
                assert len(f["refs"]) >= 3
                assert "mendeleev" not in f["refs"]
                assert any(k in refs for k in f["refs"])


def test_partial_needs_two_agreeing_refs_and_older_edition_evidence():
    known = set(_dataset()["meta"]["references"])
    seen = 0
    for el in _dataset()["elements"]:
        for f in all_fields(el):
            if f["status"] == "partial":
                seen += 1
                assert len(f["refs"]) == 2 and "mendeleev" not in f["refs"]
                assert f["older"]["source"] in known
                assert f["older"]["edition"] in known
                assert f["older"]["evidence"]
    assert seen > 0


def test_scandium_weight_shows_current_iupac_value():
    # NIST SRD 144 shows the CIAAW 2013 value 44.955908(5); CIAAW 2024 is 44.955907(4).
    w = find("Sc")["atomic_weight"]
    assert w["status"] == "partial"
    assert w["text"] == "44.955907(4)"
    assert w["refs"] == ["ciaaw-weights", "pubchem"]
    assert w["older"]["edition"] == "ciaaw-weights-2013"


def test_titanium_48_mass_is_ame2020_with_nist_on_ame2012():
    ti48 = next(i for i in find("Ti")["isotopes"] if i["mass_number"] == 48)
    assert ti48["mass"]["text"] == "47.947941"  # AME2020 47.947940677 -> 6 decimals
    assert ti48["mass"]["status"] == "partial"
    assert ti48["mass"]["older"]["edition"] == "ame2012"


def test_iron_weight_is_verified_by_ciaaw_nist_pubchem():
    w = find("Fe")["atomic_weight"]
    assert w["status"] == "verified"
    assert w["refs"] == ["ciaaw-weights", "nist-srd144", "pubchem"]


def test_interval_weight_for_hydrogen():
    w = find("H")["atomic_weight"]
    assert w["text"] == "[1.00784, 1.00811]"
    assert w["status"] == "verified"


def test_configurations_are_unverified_with_two_agreeing_sources():
    conf = find("Fe")["config"]
    assert conf["status"] == "unverified"
    assert conf["agree"] == ["nist-asd", "pubchem"]


def test_card_shows_check_column_and_numbered_references():
    result = element(ElementInput(query="Fe"))
    checks = {row[0]: row[2] for row in result.tables[0].rows}
    assert checks["Standard atomic weight"].startswith("✓ [")
    assert checks["Electron configuration"].startswith("unverified")
    assert result.sources[0].startswith("[1] ")
    assert any("Prohaska" in s for s in result.sources)
    assert result.warnings  # some values are unverified


def test_mendeleev_is_never_cited_as_a_reference():
    result = element(ElementInput(query="Fe"))
    assert not any(
        s.startswith("[") and "mendeleev" in s.split("]")[1][:20] for s in result.sources
    )


def test_lookup_is_fast():
    _dataset()  # first load
    start = time.perf_counter()
    for q in ["H", "iron", "26", "Og"]:
        element(ElementInput(query=q))
    assert time.perf_counter() - start < 0.1
