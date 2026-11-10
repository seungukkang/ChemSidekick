import pytest

from chemsidekick.core.registry import REGISTRY, discover
from chemsidekick.core.schemas import ToolError
from chemsidekick.tools.structure.stereo import StereoInput, stereo

CHOLESTEROL = "CC(CCCC(C)C)C1CCC2C1(CCC3C2CC=C4C3(CCC(C4)O)C)C"


def run(smiles: str, **kw):
    return stereo(StereoInput(smiles=smiles, **kw))


def relations(result) -> list[str]:
    return [i["relation"] for i in result.data["isomers"]]


def test_2_bromobutane():
    r = run("CCC(Br)C")
    assert r.answer == "2 stereoisomers (1 pair of enantiomers)"
    assert sorted(relations(r)) == ["enantiomer of #1", "enantiomer of #2"]


def test_2_3_dibromobutane_has_a_meso_form():
    r = run("CC(Br)C(Br)C")
    assert r.answer == "3 stereoisomers (1 pair of enantiomers, 1 meso)"
    labels = {i["cip"]: i["relation"] for i in r.data["isomers"]}
    assert labels["C2 S, C4 R"] == "meso"


def test_tartaric_acid():
    r = run("OC(=O)C(O)C(O)C(=O)O", skip_3d=True)
    assert r.answer == "3 stereoisomers (1 pair of enantiomers, 1 meso)"


def test_2_butene_e_and_z():
    r = run("CC=CC", skip_3d=True)
    assert len(r.data["isomers"]) == 2
    assert sorted(i["cip"][-1] for i in r.data["isomers"]) == ["E", "Z"]
    assert relations(r) == ["achiral", "achiral"]


def test_specified_center_is_kept():
    r = run("C[C@H](Br)C(Br)C", skip_3d=True)
    assert len(r.data["isomers"]) == 2
    assert all(i["cip"].startswith("C2 S") for i in r.data["isomers"])
    assert sorted(relations(r)) == ["chiral (enantiomer not shown)", "meso"]


def test_enumerate_all_ignores_given_stereo():
    assert len(run("C[C@H](Br)C(Br)C", enumerate_all=True, skip_3d=True).data["isomers"]) == 3


def test_pseudoasymmetric_center():
    r = run("CC(O)C(O)C(O)C", skip_3d=True)
    assert r.answer == "4 stereoisomers (1 pair of enantiomers, 2 meso)"
    assert any(" r" in i["cip"] for i in r.data["isomers"])


def test_cholesterol_is_limited_to_8_with_warning():
    r = run(CHOLESTEROL, skip_3d=True)
    assert len(r.data["isomers"]) == 8
    assert r.data["possible"] == 256
    assert any("first 8 of up to 256" in w for w in r.warnings)


def test_raising_the_maximum_raises_the_time_limit():
    discover()
    spec = REGISTRY.get("stereo")
    assert spec.resources == "medium"
    assert spec.timeout(StereoInput(smiles="C")) == 60
    assert spec.timeout(StereoInput(smiles="C", max_isomers=64)) == 128
    assert spec.timeout(StereoInput(smiles="C", max_isomers=256, skip_3d=True)) == 128
    assert len(run(CHOLESTEROL, max_isomers=32, skip_3d=True).data["isomers"]) == 32


def test_no_stereo_elements():
    r = run("CCO", skip_3d=True)
    assert r.answer == "1 stereoisomer (no stereocenters or stereo double bonds)"


@pytest.mark.parametrize(
    ("smiles", "message"),
    [
        ("C1CC", "ring is opened but never closed"),
        ("CC(C)(C)(C)(C)C", r"Atom 2 \(C\) has too many bonds"),
        ("CC(", "Syntax error around character 3"),
        ("c1cccc1", "aromatic ring"),
    ],
)
def test_bad_smiles_are_plain_errors(smiles, message, capfd):
    with pytest.raises(ToolError, match=message):
        run(smiles)
    assert "SMILES Parse Error" not in capfd.readouterr().err  # RDKit noise is hidden


def test_3d_enantiomers_are_mirror_images_with_equal_energy():
    r = run("CCC(Br)C")
    a, b = r.data["isomers"]
    assert a["status_3d"] == "ok" and b["status_3d"].startswith("ok (mirror image of #1")
    assert a["energy_kcal_mol"] == pytest.approx(b["energy_kcal_mol"])
    frames = r.structures[0].frames
    assert len(frames) == 2
    assert frames[1].coords[0][0] == pytest.approx(-frames[0].coords[0][0])


def test_files():
    r = run("CC(Br)C(Br)C")
    drawings = [a for a in r.artifacts if a.kind == "svg"]
    assert [a.title for a in drawings] == [
        "#1 · meso",
        "#2 · enantiomer of #3",
        "#3 · enantiomer of #2",
    ]
    assert drawings[0].note == "C2 S, C4 R"
    assert all("<svg" in a.path.read_text() for a in drawings)
    sdf = next(a.path for a in r.artifacts if a.kind == "sdf")
    assert sdf.read_text().count("$$$$") == 3
    assert len(list((sdf.parent / "isomers").glob("*.xyz"))) == 3


def _drawn(smiles: str):
    from rdkit import Chem

    from chemsidekick.tools.structure.stereo import _with_shared_layout, enumerate_isomers

    isomers, _ = enumerate_isomers(Chem.MolFromSmiles(smiles), 8, False)
    return isomers, _with_shared_layout(isomers)


@pytest.mark.parametrize("smiles", ["CC(Br)C(Br)C", "CC(O)C=CC(O)C", "CC=CC"])
def test_each_drawing_shows_its_own_stereochemistry(smiles):
    from rdkit import Chem

    isomers, drawn = _drawn(smiles)
    for iso, m in zip(isomers, drawn, strict=True):
        # Read the drawing back (2D coordinates + wedges) and compare.
        back = Chem.MolFromMolBlock(Chem.MolToMolBlock(m))
        assert Chem.MolToSmiles(back) == iso.smiles


def test_same_e_z_isomers_share_a_layout():
    isomers, drawn = _drawn("CC(O)C=CC(O)C")
    pos = [m.GetConformer().GetPositions().tolist() for m in drawn]
    e = [p for i, p in zip(isomers, pos, strict=True) if i.labels.endswith("E")]
    z = [p for i, p in zip(isomers, pos, strict=True) if i.labels.endswith("Z")]
    assert all(p == e[0] for p in e) and all(p == z[0] for p in z)
    assert e[0] != z[0]


def test_3d_is_reproducible():
    a = run("CC(Br)C(Br)C").structures[0].frames[0].coords
    b = run("CC(Br)C(Br)C").structures[0].frames[0].coords
    assert a == b


def test_condensed_formula_input_is_converted_and_reported():
    r = run("CH3–CH(OH)–CH=CH–CH(OH)–CH3", skip_3d=True)
    assert r.answer == "6 stereoisomers (2 pairs of enantiomers, 2 meso)"
    assert any("SMILES CC(O)C=CC(O)C" in w for w in r.warnings)


def test_unconvertible_condensed_formula_explains_smiles():
    with pytest.raises(ToolError, match="SMILES leaves hydrogens out"):
        run("CH3-CO-CH3")
