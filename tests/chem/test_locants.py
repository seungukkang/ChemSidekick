"""IUPAC locants for stereodescriptors.

Expected values are checked against PubChem IUPAC names (computed by OpenEye
Lexichem, retrieved 2026-11-10). PubChem omits pseudoasymmetric r/s, so those
come from RDKit's CIP labeler. Where the numbering is symmetric and only the
stereodescriptors decide, IUPAC 2013 P-31.1.4.3.4 gives R the lower locant;
PubChem does not apply this consistently (it names meso-2,3-dibromobutane
(2R,3S) but cis-cyclohexane-1,2-diol (1S,2R)), so those cases follow the rule.
"""

import pytest
from rdkit import Chem

from chemsidekick.chem.locants import (
    Unsupported,
    descriptor_text,
    iupac_numbering,
    stereo_elements,
)


def label(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    st = stereo_elements(mol)
    return descriptor_text(st, iupac_numbering(mol, st).locants)


@pytest.mark.parametrize(
    ("smiles", "expected", "pubchem_name"),
    [
        # chains, principal characteristic groups
        ("CC[C@@H](C)O", "(2R)", "(2R)-butan-2-ol"),
        ("CCC[C@H](C)CC", "(3R)", "(3R)-3-methylhexane"),
        ("CC[C@H](C)[C@@H](C)Cl", "(2R,3S)", "(2R,3S)-2-chloro-3-methylpentane"),
        ("C[C@@H](O)[C@@H](N)C(=O)O", "(2R,3R)", "(2R,3R)-2-amino-3-hydroxybutanoic acid"),
        ("CC(=O)[C@H](C)O", "(3S)", "(3S)-3-hydroxybutan-2-one"),
        ("CC[C@@H](C)C=O", "(2R)", "(2R)-2-methylbutanal"),
        ("CCOC(=O)[C@H](C)O", "(2S)", "ethyl (2S)-2-hydroxypropanoate"),
        ("C[C@H](O)C#N", "(2S)", "(2S)-2-hydroxypropanenitrile"),
        ("C[C@@H](O)C(N)=O", "(2R)", "(2R)-2-hydroxypropanamide"),
        ("CCC(=O)[C@H](C)Cl", "(2S)", "(2S)-2-chloropentan-3-one"),
        ("O=C[C@H](O)CO", "(2R)", "(2R)-2,3-dihydroxypropanal"),
        ("CC[C@@H](C)N", "(2R)", "(2R)-butan-2-amine"),
        ("CC(C)C[C@@H](C)CC(=O)O", "(3R)", "(3R)-3,5-dimethylhexanoic acid"),
        ("CC(C)=CCC[C@@H](C)CCO", "(3R)", "(3R)-3,7-dimethyloct-6-en-1-ol"),
        ("C[C@@H](Cl)C[C@@H](C)Br", "(2R,4R)", "(2R,4R)-2-bromo-4-chloropentane"),
        ("CN[C@@H](C)[C@H](O)c1ccccc1", "(1R,2S)", "(1R,2S)-2-(methylamino)-1-phenylpropan-1-ol"),
        ("C[C@@H](O)c1ccccc1", "(1R)", "(1R)-1-phenylethanol"),
        ("CC(C)Cc1ccc([C@H](C)C(=O)O)cc1", "(2S)",
         "(2S)-2-[4-(2-methylpropyl)phenyl]propanoic acid"),
        # double bonds: Z gets the lower locant
        ("C/C=C/[C@@H](C)O", "(2R,3E)", "(E,2R)-pent-3-en-2-ol"),
        ("C/C=C\\[C@H](C)CC", "(2Z,4R)", "(Z,4R)-4-methylhex-2-ene"),
        ("C/C=C\\[C@H](O)/C=C/C", "(2Z,4R,5E)", "(2Z,5E)-hepta-2,5-dien-4-ol (4R omitted)"),
        # rings
        ("C[C@H]1CCCC[C@@H]1O", "(1S,2S)", "trans-(1S,2S)-2-methylcyclohexan-1-ol"),
        ("C[C@H]1C=CCCC1", "(3R)", "(3R)-3-methylcyclohexene"),
        ("CC(C)[C@@H]1CC[C@@H](C)C[C@H]1O", "(1R,2S,5R)",
         "(1R,2S,5R)-5-methyl-2-propan-2-ylcyclohexan-1-ol"),
        ("C=C(C)[C@@H]1CC=C(C)C(=O)C1", "(5R)",
         "(5R)-2-methyl-5-prop-1-en-2-ylcyclohex-2-en-1-one"),
        ("C=C(C)[C@H]1CC=C(C)CC1", "(4R)", "(4R)-1-methyl-4-prop-1-en-2-ylcyclohexene"),
        ("C[C@@H]1CCC[C@H](C)C1", "(1R,3S)", "cis-(1R,3S)-1,3-dimethylcyclohexane"),
        # symmetric numbering: R gets the lower locant (P-31.1.4.3.4)
        ("C[C@H](O)C[C@@H](C)O", "(2R,4S)", "(2R,4S)-pentane-2,4-diol"),
        ("C[C@H](Br)[C@@H](C)Br", "(2R,3S)", "(2R,3S)-2,3-dibromobutane"),
        ("O[C@@H]1CCCC[C@@H]1O", "(1R,2S)", "cis-(1S,2R)-cyclohexane-1,2-diol (rule not applied)"),
        # pseudoasymmetric centers (lowercase; not in PubChem names)
        ("C[C@H](O)[C@H](O)[C@@H](C)O", "(2R,3s,4S)", "(2S,4R)-pentane-2,3,4-triol"),
        ("C[C@H](O)[C@@H](O)[C@@H](C)O", "(2R,3r,4S)", "(2S,4R)-pentane-2,3,4-triol"),
        ("OC[C@@H](O)[C@H](O)[C@@H](O)CO", "(2R,3r,4S)", "(2R,4S)-pentane-1,2,3,4,5-pentol"),
        ("C[C@H]1CC[C@H](C)CC1", "(1r,4r)", "1,4-dimethylcyclohexane"),
    ],
)  # fmt: skip
def test_locants(smiles, expected, pubchem_name):
    assert label(smiles) == expected


def test_parent_is_reported():
    mol = Chem.MolFromSmiles("C[C@H](O)C[C@@H](C)O")
    assert iupac_numbering(mol).parent == "5-carbon chain"
    assert iupac_numbering(Chem.MolFromSmiles("C[C@H]1C=CCCC1")).parent == "6-membered ring"


@pytest.mark.parametrize(
    ("smiles", "reason"),
    [
        ("CC[C@H](C)c1ccccc1", "substituent"),  # [(2S)-butan-2-yl]benzene
        ("C[C@H]1CCC2CCCCC2C1", "fused"),
        ("C[C@H]1CCCCN1", "heteroatoms"),
    ],
)
def test_unsupported_structures_say_why(smiles, reason):
    with pytest.raises(Unsupported, match=reason):
        label(smiles)


def test_atom_numbers_cannot_be_mistaken_for_locants():
    mol = Chem.MolFromSmiles("CC[C@H](C)c1ccccc1")
    assert descriptor_text(stereo_elements(mol), None) == "atom 3 S"
