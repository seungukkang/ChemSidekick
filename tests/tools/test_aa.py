import re

import pytest
from rdkit import Chem
from rdkit.Chem.MolStandardize import rdMolStandardize

from chemsidekick.core.schemas import ToolError
from chemsidekick.tools.biochemistry.aa import (
    _BACKBONE,
    AaInput,
    _layout,
    aa,
    amino_acids,
    dataset,
    drawing_svg,
    find,
)

STANDARD = set("ACDEFGHIKLMNPQRSTVWY")


def rows(query: str) -> dict[str, object]:
    result = aa(AaInput(query=query))
    return {r[0]: r[1] for t in result.tables if t.columns[0] == "Property" for r in t.rows}


def test_all_22_present_with_unique_codes():
    data = amino_acids()
    assert {a["one"] for a in data} == STANDARD | {"U", "O"}
    assert len({a["three"] for a in data}) == 22


@pytest.mark.parametrize("query", ["W", "w", "Trp", "TRP", "tryptophan", "Tryptophan", " trp "])
def test_find_tryptophan(query):
    kind, a = find(query)
    assert (kind, a["one"]) == ("aa", "W")


@pytest.mark.parametrize(
    ("query", "one"),
    [("aspartic acid", "D"), ("glutamic acid", "E"), ("trypto", "W"), ("selenocysteine", "U")],
)
def test_find_aliases_and_prefixes(query, one):
    assert find(query)[1]["one"] == one


@pytest.mark.parametrize(
    ("query", "cls"),
    [("aromatic", "aromatic"), ("basic", "positive"), ("acidic", "negative"), ("polar", "polar")],
)
def test_find_classes(query, cls):
    assert find(query) == ("class", cls)


def test_ambiguity_codes():
    kind, b = find("B")
    assert kind == "ambiguous" and b["members"] == ["D", "N"]
    result = aa(AaInput(query="Asx"))
    assert [r[0] for r in result.tables[0].rows] == ["D", "N"]
    assert find("X")[1]["members"] == []


def test_errors():
    with pytest.raises(ToolError, match="peptide sequence"):
        find("ACDE")
    with pytest.raises(ToolError, match="Did you mean: Glu .*Gln"):
        find("glutam")
    with pytest.raises(ToolError, match="not an amino-acid one-letter code"):
        find("@")


def test_stereo_labels():
    labels = {a["one"]: a["stereo"]["text"] for a in amino_acids()}
    assert labels["G"] == "achiral"
    assert labels["C"] == "(2R)" and labels["U"] == "(2R)"  # S outranks the carboxyl
    assert labels["I"] == "(2S,3S)"
    assert labels["T"] == "(2S,3R)"
    assert all(labels[o] == "(2S)" for o in STANDARD - set("GCIT"))


def test_ph7_form_is_the_same_molecule():
    uncharger = rdMolStandardize.Uncharger()
    for a in amino_acids():
        ph7 = uncharger.uncharge(Chem.MolFromSmiles(a["smiles_ph7"]))
        assert Chem.MolToInchiKey(ph7) == a["inchikey"], a["one"]


def test_ph7_charges():
    charge = {a["one"]: Chem.GetFormalCharge(Chem.MolFromSmiles(a["smiles_ph7"]))
              for a in amino_acids()}  # fmt: skip
    assert charge["K"] == charge["R"] == 1
    assert charge["D"] == charge["E"] == -1
    assert charge["H"] == charge["G"] == 0


@pytest.mark.parametrize(
    ("one", "residue_mono"),
    # Residue masses (C2H3NO for Gly etc.), computed by hand from AME2020 isotope masses.
    [("G", 57.021464), ("A", 71.037114), ("W", 186.079313), ("K", 128.094963)],
)
def test_residue_masses(one, residue_mono):
    a = next(x for x in amino_acids() if x["one"] == one)
    assert a["mass"]["residue_mono"] == pytest.approx(residue_mono, abs=2e-6)
    assert a["mass"]["mono"] - a["mass"]["residue_mono"] == pytest.approx(18.010565, abs=2e-6)


def test_isoelectric_points():
    pi = {a["one"]: a["pi"] for a in amino_acids()}
    # Simple averages of the bracketing pKa values (Lehninger Table 3-1).
    assert pi["G"] == pytest.approx((2.34 + 9.60) / 2, abs=0.02)
    assert pi["D"] == pytest.approx((1.88 + 3.65) / 2, abs=0.02)
    assert pi["K"] == pytest.approx((8.95 + 10.53) / 2, abs=0.02)
    assert pi["U"] is None and pi["O"] is None


def test_codons_cover_the_standard_code():
    codons = [c for a in amino_acids() for c in a["codons"]]
    assert len(codons) == len(set(codons)) == 61
    assert sorted(codons + dataset()["meta"]["stop_codons"]) == sorted(
        a + b + c for a in "UCAG" for b in "UCAG" for c in "UCAG"
    )


def test_backbone_pinned_in_every_drawing():
    for a in amino_acids():
        mol, side = _layout(a["one"])
        pos = mol.GetConformer().GetPositions()
        alpha = mol.GetSubstructMatch(Chem.MolFromSmarts(_BACKBONE))[1]
        assert tuple(round(v, 3) for v in pos[alpha][:2]) == (0.0, 0.0), a["one"]


def test_drawings_are_svg():
    svg = drawing_svg("W")
    assert svg.startswith("<?xml") and "</svg>" in svg
    assert "csk-backdrop" in svg
    assert "stroke='#8c5cf5'" in svg  # aromatic: border in the class color


def test_drawings_are_centered():
    import re

    for one in "GWRO":
        svg = drawing_svg(one)
        xs = [float(x) for x in re.findall(r"M ([\d.]+),[\d.]+", svg)]
        ys = [float(y) for y in re.findall(r"M [\d.]+,([\d.]+)", svg)]
        # Bond paths span the card's middle: the center of the drawing is near 130 px.
        assert abs((min(xs) + max(xs)) / 2 - 130) < 20, one
        assert abs((min(ys) + max(ys)) / 2 - 130) < 20, one


def test_overview():
    result = aa(AaInput())
    assert len(result.artifacts) == 22
    assert set(result.data["drawings"]) == STANDARD | {"U", "O"}
    assert result.tables[0].rows[0][:3] == ["G", "Gly", "Glycine"]
    assert all("coords3d" not in a for a in result.data["amino_acids"])
    assert len(aa(AaInput(query="aromatic")).artifacts) == 3


def test_card():
    result = aa(AaInput(query="C"))
    assert result.answer == "Cysteine · Cys · C"
    r = rows("C")
    assert r["Stereochemistry"] == "L · (2R)"
    assert r["Formula"] == "C3H7NO2S"
    assert r["Codons (standard code)"] == "UGU, UGC"
    (structure,) = result.structures
    frame = structure.frames[0]
    assert "CA" in frame.numbers and frame.marks[0].label == "Cα R"
    assert any("provisional" in n for n in result.notes)


def test_3d_has_hydrogens_and_ccd_protonation():
    lys = aa(AaInput(query="K")).structures[0].frames[0]
    assert re.search(r"protonated", lys.comment)
    assert lys.symbols.count("H") == 15  # C6H15N2O2+ in CCD
