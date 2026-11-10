import pytest

from chemsidekick.core.schemas import ToolError
from chemsidekick.tools.structure.xyz import XyzInput, hill_formula, parse_xyz, xyz

WATER = """3
water, E = -76.0 Eh
O   0.000000   0.000000   0.117300
H   0.000000   0.757200  -0.469200
H   0.000000  -0.757200  -0.469200
"""

BENZENE_BARE = """
C        0.00000        1.39700        0.00000
C        1.20984        0.69850        0.00000
C        1.20984       -0.69850        0.00000
C        0.00000       -1.39700        0.00000
C       -1.20984       -0.69850        0.00000
C       -1.20984        0.69850        0.00000
H        0.00000        2.48100        0.00000
H        2.14862        1.24050        0.00000
H        2.14862       -1.24050        0.00000
H        0.00000       -2.48100        0.00000
H       -2.14862       -1.24050        0.00000
H       -2.14862        1.24050        0.00000
"""


def run(text: str, **kw):
    return xyz(XyzInput(text=text, **kw))


def summary(result) -> dict[str, object]:
    return {row[0]: row[1] for row in result.tables[0].rows}


def three_frames() -> str:
    out = []
    for k in range(3):
        out += ["3", f"scan {k + 1} E = {-76.0 - 0.01 * k:.4f}", "O 0 0 0", "H 0 0.96 0.1",
                f"H 0 -0.96 {0.1 * k:.2f}"]  # fmt: skip
    return "\n".join(out) + "\n"


def test_water_standard_xyz():
    r = run(WATER)
    assert r.answer == "H2O · 3 atoms · 1 frame"
    s = summary(r)
    assert s["Formula"] == "H2O"
    assert s["Molecular weight"] == "18.015 ± 0.001 g/mol"
    assert s["Comment line"] == "water, E = -76.0 Eh"
    assert s["Closest atoms"].startswith("0.958 Å (O1–H2)")
    assert r.data["molecular_weight"] == pytest.approx(18.015)
    assert not r.warnings


def test_molecular_weight_uses_verified_abridged_weights():
    r = run(WATER)
    composition = {row[0]: row for row in r.tables[1].rows}
    assert composition["H"][1:3] == [2, "1.0080 ± 0.0002"]
    assert composition["O"][3].startswith("✓")
    assert any("Abridged Standard Atomic Weights 2024" in s for s in r.sources)


def test_benzene_without_header():
    r = run(BENZENE_BARE)
    assert r.answer == "C6H6 · 12 atoms · 1 frame"
    assert summary(r)["Molecular weight"] == "78.11 ± 0.01 g/mol"


def test_atomic_numbers_give_the_same_result():
    numbered = WATER.replace("O  ", "8  ").replace("H  ", "1  ")
    assert run(numbered).model_dump(exclude={"artifacts"}) == run(WATER).model_dump(
        exclude={"artifacts"}
    )


def test_three_frames():
    r = run(three_frames(), frame=2)
    assert r.answer == "H2O · 3 atoms · 3 frames"
    frames = next(t for t in r.tables if t.title == "Frames")
    assert [row[2] for row in frames.rows] == [
        "scan 1 E = -76.0000",
        "scan 2 E = -76.0100",
        "scan 3 E = -76.0200",
    ]
    assert r.structures[0].start_frame == 1
    assert len(r.structures[0].frames) == 3


def test_frame_out_of_range():
    with pytest.raises(ToolError, match="Frame 4 does not exist"):
        run(three_frames(), frame=4)


def test_atom_count_larger_than_lines():
    text = WATER.replace("3\n", "4\n", 1)
    with pytest.raises(ToolError, match=r"Line 1: frame 1 says 4 atoms, but 3 atom line"):
        run(text)


def test_atom_count_smaller_than_lines():
    text = WATER.replace("3\n", "2\n", 1)
    with pytest.raises(ToolError, match=r"Line 5: expected the atom count of frame 2"):
        run(text)


def test_too_small_count_in_multi_frame_points_at_next_frame():
    text = three_frames().replace("3\n", "4\n", 1)
    with pytest.raises(ToolError, match="frame 1 says 4 atoms, but 3"):
        run(text)


def test_unknown_element_with_line_number():
    with pytest.raises(ToolError, match=r"Line 4: unknown element 'Xx'"):
        run(WATER.replace("H   0.000000   0.757200", "Xx  0.000000   0.757200"))


def test_non_numeric_coordinate_with_line_number():
    with pytest.raises(ToolError, match=r"Line 3: coordinate 'abc' is not a number"):
        run(WATER.replace("0.117300", "abc"))


def test_smiles_like_input_is_a_clear_error():
    with pytest.raises(ToolError, match=r"Line 1: expected 'element x y z', found 'C1CC'"):
        run("C1CC")


def test_empty_input():
    with pytest.raises(ToolError, match="No coordinates"):
        run("   \n")


def test_overlapping_atoms_warn():
    r = run("C 0 0 0\nC 0 0 0.1\n")
    assert any("overlap" in w and "0.10 Å" in w for w in r.warnings)


def test_extra_columns_and_case_and_numbered_labels():
    r = run("CL1 0 0 0 -0.12\nc2 0 0 1.76 0.12\n")
    assert r.answer.startswith("CCl ·")
    assert any("Columns after x y z were ignored on line(s) 1–2" in w for w in r.warnings)
    assert any("Atom labels with numbers" in w for w in r.warnings)


def test_charge_and_multiplicity_line_is_skipped():
    r = run("0 1\nO 0 0 0\nH 0 0.76 0.59\nH 0 -0.76 0.59\n")
    assert r.answer == "H2O · 3 atoms · 1 frame"
    assert any("charge and multiplicity" in n for n in r.notes)


def test_fortran_exponents():
    assert parse_xyz("H 0 0 0\nH 0 0 7.4D-01\n").frames[0].coords[1][2] == pytest.approx(0.74)


def test_radioactive_element_has_no_molecular_weight():
    r = run("Tc 0 0 0\nO 0 0 1.7\n")
    assert summary(r)["Molecular weight"] == "not defined"
    assert r.data["molecular_weight"] is None


def test_hill_formula():
    assert hill_formula(["H", "O", "H"]) == "H2O"
    assert hill_formula(["Cl", "C", "H", "H", "H"]) == "CH3Cl"
    assert hill_formula(["Na", "Cl"]) == "ClNa"


def test_standard_xyz_file_is_written():
    r = run(BENZENE_BARE)
    text = r.artifacts[0].path.read_text()
    assert text.splitlines()[0] == "12"
    assert parse_xyz(text).frames[0].n_atoms == 12
