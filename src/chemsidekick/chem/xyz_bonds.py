"""Bonds inferred from 3D coordinates, for a 2D drawing of an XYZ structure.

XYZ files have no bonds. RDKit's DetermineBonds (Kim & Kim's xyz2mol method)
assigns connectivity from distances and then bond orders, assuming a neutral
molecule. It can fail or guess wrong for metals, radicals, charged species, and
transition states; then only the connectivity (all single bonds) is drawn and
the result says so. Stereochemistry is not assigned: the drawing has no wedges.
"""

from dataclasses import dataclass

from chemsidekick.core.drawing import with_backdrop
from chemsidekick.core.schemas import Frame

DRAWING_SIZE = (300, 240)  # same as the stereo drawings
MAX_ATOMS_FOR_ORDERS = 150  # bond-order search grows quickly with size


@dataclass(frozen=True)
class Inferred:
    svg: str
    orders: bool  # bond orders determined (else connectivity only)
    smiles: str  # canonical SMILES without stereo; "" when orders are unknown
    reason: str  # why bond orders are unknown ("" if determined)


def _mol_from_frame(frame: Frame):
    from rdkit import Chem
    from rdkit.Geometry import Point3D

    rw = Chem.RWMol()
    conf = Chem.Conformer(len(frame.symbols))
    for i, (symbol, (x, y, z)) in enumerate(zip(frame.symbols, frame.coords, strict=True)):
        rw.AddAtom(Chem.Atom(symbol))
        conf.SetAtomPosition(i, Point3D(x, y, z))
    rw.AddConformer(conf, assignId=True)
    return rw


def _draw(mol) -> str:
    from rdkit.Chem import rdDepictor
    from rdkit.Chem.Draw import rdMolDraw2D

    rdDepictor.SetPreferCoordGen(True)
    rdDepictor.Compute2DCoords(mol)
    d = rdMolDraw2D.MolDraw2DSVG(*DRAWING_SIZE)
    opts = d.drawOptions()
    opts.clearBackground = False  # transparent; the white backdrop is added below
    opts.padding = 0.08
    opts.prepareMolsBeforeDrawing = False  # do not re-kekulize or re-sanitize
    d.DrawMolecule(mol)
    d.FinishDrawing()
    return with_backdrop(d.GetDrawingText())


def infer(frame: Frame) -> Inferred:
    """Bonds from the coordinates, and a 2D drawing (hydrogens on carbon hidden)."""
    from rdkit import Chem
    from rdkit.Chem import rdDetermineBonds

    mol = _mol_from_frame(frame)
    reason = ""
    if len(frame.symbols) > MAX_ATOMS_FOR_ORDERS:
        reason = f"more than {MAX_ATOMS_FOR_ORDERS} atoms"
    else:
        try:
            rdDetermineBonds.DetermineBonds(mol, charge=0)
            Chem.SanitizeMol(mol)
            heavy = Chem.RemoveHs(mol)
            smiles = Chem.MolToSmiles(heavy, isomericSmiles=False)
            drawn = Chem.Mol(heavy)
            Chem.Kekulize(drawn, clearAromaticFlags=True)  # alternating double bonds, as usual
            return Inferred(svg=_draw(drawn), orders=True, smiles=smiles, reason="")
        except Exception as e:  # RDKit raises plain errors (ValueError, RuntimeError, ...)
            reason = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
            mol = _mol_from_frame(frame)
    rdDetermineBonds.DetermineConnectivity(mol)
    mol.UpdatePropertyCache(strict=False)
    try:
        drawn = Chem.RemoveHs(mol, sanitize=False)
    except Exception:
        drawn = mol
    return Inferred(svg=_draw(Chem.Mol(drawn)), orders=False, smiles="", reason=reason)
