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
    assert labels == {
        "(2R,3S)": "meso",
        "(2R,3R)": "enantiomer of #3",
        "(2S,3S)": "enantiomer of #2",
    }


def test_tartaric_acid():
    r = run("OC(=O)C(O)C(O)C(=O)O", skip_3d=True)
    assert r.answer == "3 stereoisomers (1 pair of enantiomers, 1 meso)"


def test_2_butene_e_and_z():
    r = run("CC=CC", skip_3d=True)
    assert len(r.data["isomers"]) == 2
    assert sorted(i["cip"] for i in r.data["isomers"]) == ["(2E)", "(2Z)"]
    assert relations(r) == ["achiral", "achiral"]
    assert r.answer == "2 stereoisomers (2 achiral)"


def test_specified_center_is_kept():
    r = run("C[C@H](Br)C(Br)C", skip_3d=True)
    assert len(r.data["isomers"]) == 2
    assert sorted(i["cip"] for i in r.data["isomers"]) == ["(2R,3S)", "(2S,3S)"]
    assert sorted(relations(r)) == ["chiral (enantiomer not shown)", "meso"]


def test_enumerate_all_ignores_given_stereo():
    assert len(run("C[C@H](Br)C(Br)C", enumerate_all=True, skip_3d=True).data["isomers"]) == 3


def test_pseudoasymmetric_center():
    r = run("CC(O)C(O)C(O)C", skip_3d=True)
    assert r.answer == "4 stereoisomers (1 pair of enantiomers, 2 meso)"
    assert sorted(i["cip"] for i in r.data["isomers"]) == [
        "(2R,3r,4S)",
        "(2R,3s,4S)",
        "(2R,4R)",
        "(2S,4S)",
    ]
    assert all(i["locants"] == "iupac" for i in r.data["isomers"])


def test_achiral_diastereomers_are_not_called_meso():
    # cis/trans-1,4-dimethylcyclohexane: no chiral member in the set (IUPAC meso).
    r = run("CC1CCC(C)CC1", skip_3d=True)
    assert relations(r) == ["achiral", "achiral"]
    assert sorted(i["cip"] for i in r.data["isomers"]) == ["(1r,4r)", "(1s,4s)"]
    assert r.answer == "2 stereoisomers (2 achiral)"


def test_unsupported_structures_use_atom_numbers_and_say_so():
    r = run("CCC(C)c1ccccc1", skip_3d=True)
    assert sorted(i["cip"] for i in r.data["isomers"]) == ["atom 3 R", "atom 3 S"]
    assert any("not IUPAC locants" in n and "substituent" in n for n in r.notes)


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
    s = r.structures[0]
    assert (s.navigation, s.page_name, s.numbers_name) == ("pages", "Isomer", "Locants")
    assert frames[1].coords[0][0] == pytest.approx(-frames[0].coords[0][0])


def test_files():
    r = run("CC(Br)C(Br)C")
    drawings = [a for a in r.artifacts if a.kind == "svg"]
    assert [a.title for a in drawings] == [
        "#1 · meso",
        "#2 · enantiomer of #3",
        "#3 · enantiomer of #2",
    ]
    assert drawings[0].note == "(2R,3S)"
    assert all("<svg" in a.path.read_text() for a in drawings)
    sdf = next(a.path for a in r.artifacts if a.kind == "sdf")
    assert sdf.read_text().count("$$$$") == 3
    assert len(list((sdf.parent / "isomers").glob("*.xyz"))) == 3


def _drawn(smiles: str):
    from rdkit import Chem

    from chemsidekick.tools.structure.stereo import _with_shared_layout, enumerate_isomers

    isomers, _, _ = enumerate_isomers(Chem.MolFromSmiles(smiles), 8, False)
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

    def has(iso, d):
        return any(label == d for _, label in iso.stereo)

    e = [p for i, p in zip(isomers, pos, strict=True) if has(i, "E")]
    z = [p for i, p in zip(isomers, pos, strict=True) if has(i, "Z")]
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


def test_3d_frames_carry_locants_and_stereo_marks():
    r = run("CC(O)C(O)C(O)C")
    frame = next(f for f in r.structures[0].frames if "3r" in f.comment)
    # C2, C3, C4 of pentane-2,3,4-triol carry locants; O and H atoms none.
    heavy = [n for n in frame.numbers if n]
    assert sorted(heavy, key=int) == ["1", "2", "3", "4", "5"]
    assert sorted(m.label for m in frame.marks) == ["R", "S", "r"]
    assert frame.comment == "#3 · meso · (2R,3r,4S)"
    for m in frame.marks:
        assert frame.symbols[m.atoms[0]] == "C"


# --- meso, achiral and chiral: checked against the known sets ------------------

GIVEN = "chiral (enantiomer not shown)"


def kinds(result) -> dict[str, int]:
    """Relation counts; enantiomer pairs counted once as 'pair'."""
    out: dict[str, int] = {}
    for i in result.data["isomers"]:
        key = "pair" if i["relation"].startswith("enantiomer of") else i["relation"]
        out[key] = out.get(key, 0) + 1
    if "pair" in out:
        out["pair"] //= 2
    return out


@pytest.mark.parametrize(
    ("smiles", "expected"),
    [
        # Fully specified: meso is decided by the whole set, not by the one isomer shown.
        ("C[C@H](Br)[C@@H](C)Br", {"meso": 1}),  # meso-2,3-dibromobutane
        ("C[C@@H](Br)[C@@H](C)Br", {GIVEN: 1}),  # (2R,3R)
        ("O=C(O)[C@@H](O)[C@@H](O)C(=O)O", {"meso": 1}),  # meso-tartaric acid
        ("O=C(O)[C@@H](O)[C@H](O)C(=O)O", {GIVEN: 1}),  # (R,R)- or (S,S)-tartaric acid
        ("C[C@H](O)C[C@@H](C)O", {"meso": 1}),  # (2R,4S)-pentane-2,4-diol
        ("C[C@H](O)[C@@H](O)[C@@H](C)O", {"meso": 1}),  # (2R,3r,4S)-pentane-2,3,4-triol
        ("O[C@@H]1CCCC[C@@H]1O", {"meso": 1}),  # cis-cyclohexane-1,2-diol
        ("O[C@H]1CCCC[C@@H]1O", {GIVEN: 1}),  # trans-cyclohexane-1,2-diol
        ("C[C@@H]1CCC[C@H](C)C1", {"meso": 1}),  # cis-1,3-dimethylcyclohexane
        ("C[C@H]1CCC[C@H](C)C1", {GIVEN: 1}),  # trans-1,3-dimethylcyclohexane
        # Achiral, and no chiral member in the set: not meso.
        ("C[C@H]1CC[C@@H](C)CC1", {"achiral": 1}),  # cis-1,4-dimethylcyclohexane
        ("CC1CC(C)C1", {"achiral": 2}),  # cis/trans-1,3-dimethylcyclobutane
        ("C1CCC2CCCCC2C1", {"achiral": 2}),  # cis/trans-decalin
        ("OC1CC(O)CC(O)C1", {"achiral": 2}),  # cyclohexane-1,3,5-triols
        ("CC=CC=CC", {"achiral": 3}),  # (2E,4E), (2E,4Z), (2Z,4Z)-hexa-2,4-diene
        # Full sets.
        ("CC1CC1C", {"meso": 1, "pair": 1}),  # 1,2-dimethylcyclopropane
        ("CC1CCC(C)N1", {"meso": 1, "pair": 1}),  # 2,5-dimethylpyrrolidine
        ("OCC(O)C(O)C(O)CO", {"meso": 2, "pair": 1}),  # pentitols
        ("CC(O)C=CC(O)C", {"meso": 2, "pair": 2}),  # hex-3-ene-2,5-diol
        ("CC=CC(O)C=CC", {"achiral": 2, "pair": 1}),  # EE, ZZ (C4 not stereogenic); EZ pair
    ],
)
def test_relations_match_the_known_sets(smiles, expected):
    assert kinds(run(smiles, skip_3d=True)) == expected


def test_hexitols_and_inositols():
    # Hexitols: allitol and galactitol are meso, plus 4 pairs (10 in all).
    assert kinds(run("OCC(O)C(O)C(O)C(O)CO", max_isomers=32, skip_3d=True)) == {
        "meso": 2,
        "pair": 4,
    }
    # Inositols: 9 stereoisomers, 7 meso (myo, scyllo, ...) and the chiro pair.
    assert kinds(run("OC1C(O)C(O)C(O)C(O)C1O", max_isomers=64, skip_3d=True)) == {
        "meso": 7,
        "pair": 1,
    }


def test_complete_lists_show_the_exact_count():
    r = run("CC(O)C(O)C(O)C", skip_3d=True)  # RDKit's upper bound is 8; there are 4
    assert r.data["complete"] and r.data["possible"] == 8
    labels = [h.label for h in r.highlights]
    assert "Stereoisomers" in labels and "Upper bound" not in labels
    assert next(h.value for h in r.highlights if h.label == "Stereoisomers") == "4"


def test_a_list_cut_at_the_maximum_says_so():
    r = run("CC(O)C(O)C(O)C", max_isomers=2, skip_3d=True)
    assert not r.data["complete"]
    assert r.answer.startswith("2 stereoisomers shown (more exist)")
    assert {h.label: h.value for h in r.highlights}["Upper bound"] == "8"
    # Exactly the maximum, and nothing more: complete, no warning.
    r = run("CC(O)C(O)C(O)C", max_isomers=4, skip_3d=True)
    assert r.data["complete"] and not any("first" in w for w in r.warnings)


def test_centers_without_a_cip_label_are_reported():
    # cis,cis,trans-cyclohexane-1,3,5-triol: RDKit labels one of its three centers.
    r = run("OC1CC(O)CC(O)C1", skip_3d=True)
    warnings = [w for w in r.warnings if "CIP labeler gave no" in w]
    assert len(warnings) == 1 and "incomplete" in warnings[0]
    assert not [w for w in run("CC(O)C(O)C(O)C", skip_3d=True).warnings if "CIP" in w]
