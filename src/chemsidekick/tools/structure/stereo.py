"""Tool `stereo`: enumerate the stereoisomers of a SMILES, with 2D and 3D structures.

Steps (plan 003 §6.3):
    1. read the SMILES (RDKit errors are turned into plain sentences)
    2. enumerate stereoisomers (centers already given in the SMILES are kept,
       unless enumerate_all is set), at most `max_isomers`
    3. CIP labels (R/S, r/s, E/Z) with RDKit's new CIP labeler
    4. relations: the mirror image of each isomer (all tetrahedral centers
       inverted) is compared with the others by canonical SMILES
    5. one 2D drawing per isomer with CIP labels, all on the same layout
    6. optional 3D: ETKDGv3 embedding with a fixed seed, then MMFF94 (UFF if
       MMFF94 has no parameters), and a check that the 3D structure has the
       intended stereochemistry

Axial and planar chirality and helicity are not handled in v0.1.
"""

import logging
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from chemsidekick.chem.condensed import looks_condensed, to_smiles
from chemsidekick.core.registry import tool
from chemsidekick.core.runner import workdir
from chemsidekick.core.schemas import (
    Artifact,
    Frame,
    Highlight,
    Smiles,
    Structure3D,
    Table,
    ToolError,
    ToolResult,
)

SEED = 0xC5  # fixed embedding seed: the same input gives the same 3D structures
# Time limit per isomer. Measured (M6, 2026-11-10): cholesterol, 64 isomers with 3D
# in 13 s (about 0.2 s per isomer), 93 MB. The limits leave a 10x margin.
SECONDS_PER_ISOMER_3D = 2.0
SECONDS_PER_ISOMER_2D = 0.5

LIMITATIONS = "Not handled in v0.1: axial chirality (atropisomers), planar chirality, and helicity."


class StereoInput(BaseModel):
    smiles: Smiles = Field(
        description="SMILES of the molecule, e.g. CC(Br)C(Br)C. Stereo marks (@, /, \\) "
        "already in the SMILES are kept unless --enumerate-all is given. Simple condensed "
        "formulas such as CH3-CH(OH)-CH3 are also accepted.",
        json_schema_extra={"positional": True, "label": "SMILES"},
    )
    max_isomers: int = Field(
        default=8,
        ge=1,
        le=1024,
        description="Largest number of stereoisomers to make. More takes longer.",
        json_schema_extra={"flag": "--max", "label": "Max isomers"},
    )
    enumerate_all: bool = Field(
        default=False,
        description="Also enumerate the stereo centers already given in the SMILES.",
        json_schema_extra={"label": "Enumerate specified centers too"},
    )
    skip_3d: bool = Field(
        default=False,
        description="Skip the 3D structures (much faster).",
        json_schema_extra={"flag": "--no-3d", "label": "Skip 3D (faster)"},
    )


def _timeout(inp: StereoInput) -> float:
    per = SECONDS_PER_ISOMER_2D if inp.skip_3d else SECONDS_PER_ISOMER_3D
    return max(60.0, per * inp.max_isomers)


@tool(
    name="stereo",
    number=2,
    title="Stereoisomers",
    summary="All stereoisomers of a SMILES: R/S and E/Z labels, relations, 2D and 3D",
    category="structure",
    keywords=["stereoisomer", "chirality", "enantiomer", "diastereomer", "meso", "R/S", "E/Z"],
    resources="medium",
    timeout=_timeout,
    icon="flip",
)
def stereo(inp: StereoInput) -> ToolResult:
    mol, reading = read_structure(inp.smiles)
    isomers, possible = enumerate_isomers(mol, inp.max_isomers, inp.enumerate_all)
    for iso in isomers:
        iso.relation = relation_of(iso, isomers)
    warnings = [reading] if reading else []
    if possible > len(isomers) and len(isomers) == inp.max_isomers:
        warnings.append(
            f"Showing the first {len(isomers)} of up to {possible} stereoisomers. "
            "Raise the maximum (--max) to see more; this takes longer."
        )
    if not inp.skip_3d:
        warnings += embed_all(isomers)
    return _result(inp, mol, isomers, possible, warnings)


# ---------------------------------------------------------------------------
# Reading SMILES
# ---------------------------------------------------------------------------


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage().strip())


def _plain(messages: list[str], smiles: str) -> str:
    """RDKit log lines -> one sentence for the user."""
    text = " ".join(messages)
    if "unclosed ring" in text:
        return "A ring is opened but never closed (check the ring-closure digits)."
    if "valence" in text.lower():
        # "Explicit valence for atom # 1 C, 6, is greater than permitted"
        for m in messages:
            if "atom #" in m:
                parts = m.split("atom #")[1].replace(",", " ").split()
                return f"Atom {int(parts[0]) + 1} ({parts[1]}) has too many bonds ({parts[2]})."
        return "An atom has too many bonds."
    if "kekulize" in text:
        return "The aromatic ring cannot be given alternating double bonds (check lowercase atoms)."
    for m in messages:
        if "check for mistakes around position" in m:
            pos = m.rsplit("position", 1)[1].strip(" :")
            return f"Syntax error around character {pos}."
    return messages[0] if messages else "RDKit could not read it."


def read_smiles(smiles: str):
    from rdkit import Chem, rdBase

    # Send RDKit's messages to a Python logger and collect them, instead of
    # letting RDKit print them to the terminal.
    rdBase.LogToPythonLogger()
    logger = logging.getLogger("rdkit")
    capture = _Capture()
    saved = logger.handlers[:]
    logger.handlers = [capture]
    try:
        mol = Chem.MolFromSmiles(smiles)
    finally:
        logger.handlers = saved
    if mol is None:
        message = f"Could not read the SMILES {smiles!r}: {_plain(capture.messages, smiles)}"
        if looks_condensed(smiles):
            message += (
                " It looks like a condensed formula, which could not be converted. "
                "SMILES leaves hydrogens out: CH3–CH(OH)–CH3 is written CC(O)C."
            )
        raise ToolError(message)
    if mol.GetNumAtoms() == 0:
        raise ToolError("The SMILES has no atoms.")
    return mol


def read_structure(text: str):
    """SMILES, or a simple condensed formula (e.g. CH3–CH(OH)–CH3).

    Returns the molecule and, if the text was read as a condensed formula, a
    sentence saying so (shown to the user, since it is an interpretation).
    """
    from rdkit import Chem

    if looks_condensed(text) and (smiles := to_smiles(text)):
        return Chem.MolFromSmiles(smiles), (
            f"Read as a condensed formula, not SMILES: {text.strip()} → SMILES {smiles} "
            "(hydrogen count of every atom checked)."
        )
    return read_smiles(text), None


# ---------------------------------------------------------------------------
# Enumeration, labels, relations
# ---------------------------------------------------------------------------


@dataclass
class Isomer:
    number: int
    mol: object  # rdkit Mol (no hydrogens)
    smiles: str
    labels: str
    has_tetrahedral: bool
    mirror_smiles: str
    relation: str = ""
    mol3d: object | None = None
    energy: float | None = None
    force_field: str = ""
    status_3d: str = "skipped"
    notes: list[str] = field(default_factory=list)


def cip_labels(mol) -> str:
    """'C2 R, C3 S, C1=C2 E' with atom numbers counted from 1 (as in the 3D view)."""
    from rdkit.Chem import rdCIPLabeler

    rdCIPLabeler.AssignCIPLabels(mol)
    parts = [
        f"{a.GetSymbol()}{a.GetIdx() + 1} {a.GetProp('_CIPCode')}"
        for a in mol.GetAtoms()
        if a.HasProp("_CIPCode")
    ]
    for b in mol.GetBonds():
        if b.HasProp("_CIPCode"):
            a1, a2 = b.GetBeginAtom(), b.GetEndAtom()
            parts.append(
                f"{a1.GetSymbol()}{a1.GetIdx() + 1}={a2.GetSymbol()}{a2.GetIdx() + 1} "
                f"{b.GetProp('_CIPCode')}"
            )
    return ", ".join(parts) or "—"


def mirror_image(mol):
    """The mirror image: every tetrahedral center inverted (E/Z does not change)."""
    from rdkit import Chem

    m = Chem.Mol(mol)
    swap = {
        Chem.ChiralType.CHI_TETRAHEDRAL_CW: Chem.ChiralType.CHI_TETRAHEDRAL_CCW,
        Chem.ChiralType.CHI_TETRAHEDRAL_CCW: Chem.ChiralType.CHI_TETRAHEDRAL_CW,
    }
    for a in m.GetAtoms():
        if a.GetChiralTag() in swap:
            a.SetChiralTag(swap[a.GetChiralTag()])
    return m


def enumerate_isomers(mol, max_isomers: int, enumerate_all: bool) -> tuple[list[Isomer], int]:
    from rdkit import Chem
    from rdkit.Chem.EnumerateStereoisomers import (
        EnumerateStereoisomers,
        GetStereoisomerCount,
        StereoEnumerationOptions,
    )

    if enumerate_all:
        mol = Chem.Mol(mol)
        Chem.RemoveStereochemistry(mol)
    options = StereoEnumerationOptions(
        onlyUnassigned=True, unique=True, maxIsomers=max_isomers, tryEmbedding=False
    )
    possible = GetStereoisomerCount(mol, options=options)
    isomers = []
    for k, m in enumerate(EnumerateStereoisomers(mol, options=options), start=1):
        Chem.AssignStereochemistry(m, cleanIt=True, force=True)
        has_tet = any(
            a.GetChiralTag()
            in (Chem.ChiralType.CHI_TETRAHEDRAL_CW, Chem.ChiralType.CHI_TETRAHEDRAL_CCW)
            for a in m.GetAtoms()
        )
        isomers.append(
            Isomer(
                number=k,
                mol=m,
                smiles=Chem.MolToSmiles(m),
                labels=cip_labels(m),
                has_tetrahedral=has_tet,
                mirror_smiles=Chem.MolToSmiles(mirror_image(m)),
            )
        )
    return isomers, possible


def relation_of(iso: Isomer, isomers: list[Isomer]) -> str:
    """How an isomer relates to its own mirror image."""
    if iso.mirror_smiles == iso.smiles:
        return "meso" if iso.has_tetrahedral else "achiral"
    partner = next((o for o in isomers if o.smiles == iso.mirror_smiles), None)
    if partner:
        return f"enantiomer of #{partner.number}"
    return "chiral (enantiomer not shown)"


def pair_relation(a: Isomer, b: Isomer) -> str:
    if a is b:
        return "="
    return "enantiomers" if a.mirror_smiles == b.smiles else "diastereomers"


# ---------------------------------------------------------------------------
# 3D
# ---------------------------------------------------------------------------


def _optimize(iso: Isomer, m) -> None:
    from rdkit.Chem import AllChem

    if AllChem.MMFFHasAllMoleculeParams(m):
        ff = AllChem.MMFFGetMoleculeForceField(m, AllChem.MMFFGetMoleculeProperties(m))
        iso.force_field = "MMFF94"
    else:
        ff = AllChem.UFFGetMoleculeForceField(m)
        iso.force_field = "UFF"
    ff.Minimize(maxIts=2000)
    iso.energy = ff.CalcEnergy()


def _mirrored(m):
    """The same conformer reflected through the yz plane (x -> -x)."""
    from rdkit import Chem

    out = Chem.Mol(m)
    conf = out.GetConformer()
    for i in range(out.GetNumAtoms()):
        p = conf.GetAtomPosition(i)
        conf.SetAtomPosition(i, (-p.x, p.y, p.z))
    return out


def embed_all(isomers: list[Isomer]) -> list[str]:
    """One 3D structure per isomer. The second isomer of an enantiomer pair is the
    exact mirror image of the first, so the pair has the same geometry and energy."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    warnings = []
    done: dict[str, Isomer] = {}
    for iso in isomers:
        partner = done.get(iso.mirror_smiles)
        if partner is not None and iso.mirror_smiles != iso.smiles:
            m = _mirrored(partner.mol3d)
            iso.force_field, iso.energy = partner.force_field, partner.energy
            iso.notes.append(f"mirror image of #{partner.number}")
        else:
            m = Chem.AddHs(iso.mol)
            params = AllChem.ETKDGv3()
            params.randomSeed = SEED
            if AllChem.EmbedMolecule(m, params) != 0:
                iso.status_3d = "embedding failed"
                continue
            _optimize(iso, m)
        # Check that the 3D structure has the stereochemistry it should have.
        check = Chem.Mol(m)
        Chem.AssignStereochemistryFrom3D(check)
        if Chem.MolToSmiles(Chem.RemoveHs(check)) != iso.smiles:
            iso.status_3d = "stereo mismatch"
            warnings.append(
                f"Isomer #{iso.number}: the 3D structure does not reproduce its "
                "stereochemistry; it is left out of the 3D view."
            )
            continue
        iso.mol3d = m
        iso.status_3d = "ok" if not iso.notes else f"ok ({iso.notes[-1]})"
        done[iso.smiles] = iso
    uff = [i.number for i in isomers if i.force_field == "UFF"]
    if uff:
        warnings.append(
            "MMFF94 has no parameters for some atoms; UFF was used instead for isomer(s) "
            + ", ".join(f"#{n}" for n in uff)
            + ". UFF geometries and energies are rougher."
        )
    return warnings


def _frame(iso: Isomer) -> Frame:
    m = iso.mol3d
    pos = m.GetConformer().GetPositions()
    return Frame(
        symbols=[a.GetSymbol() for a in m.GetAtoms()],
        coords=[tuple(float(v) for v in p) for p in pos],
        comment=f"#{iso.number} · {iso.labels} · {iso.relation}",
    )


# ---------------------------------------------------------------------------
# Files and result
# ---------------------------------------------------------------------------


DRAWING_SIZE = (300, 240)


def _draw_options():
    from rdkit.Chem.Draw import rdMolDraw2D

    opts = rdMolDraw2D.MolDrawOptions()
    opts.addStereoAnnotation = True  # CIP labels next to the stereo centers
    opts.annotationFontScale = 0.75  # R/S labels readable at card size
    opts.clearBackground = False  # transparent: fits light and dark themes
    opts.padding = 0.08
    return opts


def _double_bond_key(mol) -> tuple:
    """The E/Z configuration of every stereo double bond (empty if none)."""
    return tuple(
        (b.GetIdx(), str(b.GetStereo()))
        for b in mol.GetBonds()
        if b.GetStereo() != b.GetStereo().STEREONONE
    )


def _with_shared_layout(isomers: list[Isomer]) -> list:
    """Copies of the isomers for drawing. Isomers with the same E/Z configuration
    share one 2D layout, so their drawings differ only in the wedges. (A layout
    cannot be shared across E/Z: it fixes the double-bond geometry.) All isomers
    come from the same molecule and keep its atom order."""
    from rdkit import Chem
    from rdkit.Chem import rdDepictor

    rdDepictor.SetPreferCoordGen(True)
    layouts: dict[tuple, object] = {}
    out = []
    for iso in isomers:
        key = _double_bond_key(iso.mol)
        if key not in layouts:
            base = Chem.Mol(iso.mol)
            rdDepictor.Compute2DCoords(base)
            layouts[key] = base.GetConformer()
        m = Chem.Mol(iso.mol)
        m.RemoveAllConformers()
        m.AddConformer(Chem.Conformer(layouts[key]), assignId=True)
        Chem.WedgeMolBonds(m, m.GetConformer())
        out.append(m)
    return out


def _svg(mol) -> str:
    from rdkit.Chem.Draw import rdMolDraw2D

    d = rdMolDraw2D.MolDraw2DSVG(*DRAWING_SIZE)
    d.SetDrawOptions(_draw_options())
    d.DrawMolecule(mol)
    d.FinishDrawing()
    return d.GetDrawingText()


def _write_files(isomers: list[Isomer]) -> list[Artifact]:
    from rdkit import Chem

    wd = workdir()
    each = wd / "isomers"
    each.mkdir(exist_ok=True)
    artifacts = []
    for iso, drawn in zip(isomers, _with_shared_layout(isomers), strict=True):
        path = each / f"isomer-{iso.number:02d}.svg"
        path.write_text(_svg(drawn), encoding="utf-8")
        artifacts.append(
            Artifact(
                kind="svg", path=path, title=f"#{iso.number} · {iso.relation}", note=iso.labels
            )
        )
        if iso.mol3d is not None:
            (each / f"isomer-{iso.number:02d}.xyz").write_text(
                Chem.MolToXYZBlock(iso.mol3d), encoding="utf-8"
            )
    with_3d = [i for i in isomers if i.mol3d is not None]
    if with_3d:
        sdf = wd / "isomers.sdf"
        writer = Chem.SDWriter(str(sdf))
        for iso in with_3d:
            m = Chem.Mol(iso.mol3d)
            m.SetProp("_Name", f"isomer {iso.number}")
            m.SetProp("SMILES", iso.smiles)
            m.SetProp("CIP", iso.labels)
            m.SetProp("relation", iso.relation)
            m.SetProp("energy_kcal_mol", f"{iso.energy:.2f}")
            m.SetProp("force_field", iso.force_field)
            writer.write(m)
        writer.close()
        artifacts.append(Artifact(kind="sdf", path=sdf, title="3D structures (SDF)"))
    return artifacts


def _summary(isomers: list[Isomer]) -> str:
    n = len(isomers)
    pairs = sum(1 for i in isomers if i.relation.startswith("enantiomer of")) // 2
    meso = sum(1 for i in isomers if i.relation == "meso")
    parts = []
    if pairs:
        parts.append(f"{pairs} pair{'s' if pairs > 1 else ''} of enantiomers")
    if meso:
        parts.append(f"{meso} meso")
    head = f"{n} stereoisomer{'s' if n > 1 else ''}"
    return f"{head} ({', '.join(parts)})" if parts else head


def _result(inp, mol, isomers, possible, warnings) -> ToolResult:
    from rdkit import Chem

    if not isomers:
        raise ToolError("No stereoisomers could be made.")
    no_stereo = len(isomers) == 1 and isomers[0].labels == "—"
    artifacts = _write_files(isomers)

    rows = []
    for iso in isomers:
        row = [iso.number, iso.smiles, iso.labels, iso.relation]
        if not inp.skip_3d:
            energy = f"{iso.energy:.2f}" if iso.energy is not None else "—"
            row += [iso.status_3d, f"{energy} ({iso.force_field})" if iso.force_field else energy]
        rows.append(row)
    columns = ["#", "SMILES", "CIP labels", "Relation"]
    if not inp.skip_3d:
        columns += ["3D", "Energy (kcal/mol)"]
    tables = [Table(title="Stereoisomers", columns=columns, rows=rows)]
    if 1 < len(isomers) <= 16:
        short = {"=": "—", "enantiomers": "E", "diastereomers": "D"}
        tables.append(
            Table(
                title="Relations",
                columns=[""] + [f"#{i.number}" for i in isomers],
                rows=[
                    [f"#{a.number}"] + [short[pair_relation(a, b)] for b in isomers]
                    for a in isomers
                ],
            )
        )

    structures = []
    with_3d = [i for i in isomers if i.mol3d is not None]
    if with_3d:
        structures.append(
            Structure3D(
                frames=[_frame(i) for i in with_3d],
                title=f"Stereoisomers of {Chem.MolToSmiles(mol, isomericSmiles=False)}",
            )
        )

    pairs = sum(1 for i in isomers if i.relation.startswith("enantiomer of")) // 2
    answer = _summary(isomers)
    if no_stereo:
        answer = "1 stereoisomer (no stereocenters or stereo double bonds)"
    assumptions = [
        "Stereo elements: tetrahedral centers (R/S, pseudoasymmetric r/s) and double "
        "bonds (E/Z), as perceived by RDKit.",
        "Relations: an isomer's mirror image has every tetrahedral center inverted; "
        "isomers are compared by canonical SMILES.",
    ]
    if not inp.skip_3d:
        assumptions.append(
            "3D: one conformer per isomer (ETKDGv3, fixed seed), optimized with MMFF94. "
            "Energies belong to that conformer, not to the lowest-energy conformer, so "
            "they are not reliable for comparing diastereomers. The second isomer of an "
            "enantiomer pair is the mirror image of the first (same energy)."
        )
    from rdkit import __version__ as rdkit_version

    return ToolResult(
        answer=answer,
        highlights=[
            Highlight(label="Stereoisomers shown", value=str(len(isomers))),
            Highlight(label="Possible (upper bound)", value=str(possible)),
            Highlight(label="Pairs of enantiomers", value=str(pairs)),
            Highlight(label="Meso", value=str(sum(1 for i in isomers if i.relation == "meso"))),
        ],
        tables=tables,
        structures=structures,
        artifacts=artifacts,
        warnings=warnings,
        assumptions=assumptions,
        notes=[
            "Relations: E = enantiomers, D = diastereomers.",
            "Atom numbers in CIP labels count from 1 in the order of the SMILES; "
            "they match the atom numbers in the 3D view.",
            f"Each isomer is saved as SVG{'' if inp.skip_3d else ' and XYZ'} in the "
            "isomers folder. 2D drawings with the same E/Z configuration share one "
            "layout, so only the wedges differ.",
            LIMITATIONS,
        ],
        sources=[
            f"RDKit {rdkit_version}: stereoisomer enumeration, new CIP labeler "
            "(R. M. Hanson et al., J. Chem. Inf. Model. 2018, 58, 1755–1765), ETKDGv3 "
            "(S. Wang, J. Witek, G. A. Landrum, S. Riniker, J. Chem. Inf. Model. 2020, "
            "60, 2044–2058), MMFF94 (T. A. Halgren, J. Comput. Chem. 1996, 17, 490–519)."
        ],
        data={
            "possible": possible,
            "isomers": [
                {
                    "number": i.number,
                    "smiles": i.smiles,
                    "cip": i.labels,
                    "relation": i.relation,
                    "status_3d": i.status_3d,
                    "energy_kcal_mol": i.energy,
                    "force_field": i.force_field or None,
                }
                for i in isomers
            ],
        },
    )
