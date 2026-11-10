import pytest

from chemsidekick.chem.condensed import looks_condensed, to_smiles


@pytest.mark.parametrize(
    ("formula", "smiles"),
    [
        ("CH3–CH(OH)–CH=CH–CH(OH)–CH3", "CC(O)C=CC(O)C"),
        ("HO-CH2-CH2-OH", "OCCO"),
        ("CH3CH(OH)CH2CH3", "CC(O)CC"),
        ("CH3-CH(CH3)-CH2-COOH", "CC(C)CC(=O)O"),
        ("CH3CH2CHO", "CCC=O"),
        ("CH2=CH-CH=CH2", "C=CC=C"),
        ("CH3-C≡C-CH3", "CC#CC"),
        ("CH3-CH(CH3)2", "CC(C)(C)"),
        ("H2N-CH2-COOH", "NCC(=O)O"),
        ("CH3 - CH(Br) - CH3", "CC(Br)C"),
    ],
)
def test_condensed_formulas(formula, smiles):
    assert to_smiles(formula) == smiles


@pytest.mark.parametrize(
    "formula",
    [
        "CH3-CO-CH3",  # ketone written as CO: would be misread as an ether, so rejected
        "CH4-CH3",  # too many hydrogens on carbon
        "CH3-CH(OH",  # unclosed branch
        "(CH3)2CH-OH",  # leading branch: not supported
        "C6H5-CH3",  # aromatic rings: not supported
    ],
)
def test_unsupported_or_inconsistent_formulas_are_rejected(formula):
    assert to_smiles(formula) is None


def test_looks_condensed():
    assert looks_condensed("CH3-CH3")
    assert looks_condensed("C–C")
    assert not looks_condensed("CC(O)C=CC(O)C")
    assert not looks_condensed("C[C@H](Br)C")
