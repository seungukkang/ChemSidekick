"""Tool `aa`: the proteinogenic amino acids — codes, structures, properties.

Data comes from data/amino_acids.json, built by scripts/build_amino_acids.py by
cross-checking wwPDB CCD, PubChem and ChEBI (structures), the verified element
data (masses), ExPASy (Kyte–Doolittle) and NCBI (codons). pKa values are from
one textbook table and are shown as provisional (plan 006 Q4).

2D drawings show the dominant charge state near pH 7, with the backbone in the
same orientation in every drawing, each scaled to fill a white card with a border
in its class color. The 3D view uses the CCD ideal coordinates.
"""

import difflib
import json
from functools import cache
from importlib.resources import files
from typing import Any

from pydantic import BaseModel, Field

from chemsidekick.core.drawing import with_backdrop
from chemsidekick.core.registry import tool
from chemsidekick.core.runner import workdir
from chemsidekick.core.schemas import (
    Artifact,
    Frame,
    Highlight,
    Mark,
    Structure3D,
    Table,
    ToolError,
    ToolResult,
)

AminoAcid = dict[str, Any]


class AaInput(BaseModel):
    query: str | None = Field(
        default=None,
        description="One-letter or three-letter code, or name (W, Trp, tryptophan); "
        "or a class (aromatic, basic, acidic, polar, nonpolar). Leave empty for all.",
        json_schema_extra={"positional": True, "label": "Amino acid"},
    )


@tool(
    name="aa",
    number=1,
    title="Amino acids",
    summary="The 20 (+2) amino acids: codes, 2D and 3D structures, classes, masses, pKa, codons",
    category="biochemistry",
    keywords=[
        "amino acid",
        "residue",
        "protein",
        "one-letter code",
        "three-letter code",
        "side chain",
        "codon",
        "pI",
        "hydropathy",
    ],  # fmt: skip
    icon="biotech",
    start_view="All amino acids",
)
def aa(inp: AaInput) -> ToolResult:
    query = (inp.query or "").strip()
    if not query:
        return _overview(None)
    kind, value = find(query)
    if kind == "class":
        return _overview(value)
    if kind == "ambiguous":
        return _ambiguous(value)
    return _card(value)


# ---------------------------------------------------------------------------
# Data and lookup
# ---------------------------------------------------------------------------


@cache
def dataset() -> dict[str, Any]:
    path = files("chemsidekick.tools.biochemistry").joinpath("data/amino_acids.json")
    return json.loads(path.read_text(encoding="utf-8"))


def amino_acids() -> list[AminoAcid]:
    return dataset()["amino_acids"]


def by_one(one: str) -> AminoAcid:
    return next(a for a in amino_acids() if a["one"] == one)


CLASS_ALIASES = {
    "nonpolar": "nonpolar", "non-polar": "nonpolar", "aliphatic": "nonpolar",
    "aromatic": "aromatic",
    "polar": "polar", "uncharged": "polar",
    "positive": "positive", "basic": "positive", "positively charged": "positive",
    "negative": "negative", "acidic": "negative", "negatively charged": "negative",
    "other": "other",
}  # fmt: skip

NAME_ALIASES = {"aspartic acid": "D", "glutamic acid": "E", "sec": "U", "pyl": "O"}


@cache
def _index() -> dict[str, tuple[str, Any]]:
    """Lowercase key -> ("aa" | "ambiguous" | "class", record or class key)."""
    index: dict[str, tuple[str, Any]] = {}
    for key, cls in CLASS_ALIASES.items():
        index[key] = ("class", cls)
    for cls, title in dataset()["meta"]["classes"].items():
        index[title.lower()] = ("class", cls)
    for amb in dataset()["ambiguous"]:
        index[amb["three"].lower()] = ("ambiguous", amb)
    for a in amino_acids():
        index[a["three"].lower()] = ("aa", a)
        index[a["name"].lower()] = ("aa", a)
    for name, one in NAME_ALIASES.items():
        index[name] = ("aa", by_one(one))
    return index


def find(query: str) -> tuple[str, Any]:
    """Look up a code, name, or class. One letter is always read as a one-letter code."""
    q = query.strip()
    if len(q) == 1:
        letter = q.upper()
        for a in amino_acids():
            if a["one"] == letter:
                return "aa", a
        for amb in dataset()["ambiguous"]:
            if amb["one"] == letter:
                return "ambiguous", amb
        raise ToolError(f"{letter!r} is not an amino-acid one-letter code.")
    key = q.lower()
    if key in _index():
        return _index()[key]
    starts = sorted({a["one"] for k, (kind, a) in _index().items()
                     if kind == "aa" and k.startswith(key)})  # fmt: skip
    if len(starts) == 1:
        return "aa", by_one(starts[0])
    letters = {a["one"] for a in amino_acids()} | {b["one"] for b in dataset()["ambiguous"]}
    if q.isalpha() and q.isupper() and set(q) <= letters:
        raise ToolError(
            f"{q!r} looks like a peptide sequence. Sequences are not supported yet; "
            "type one amino acid (e.g. W, Trp, tryptophan)."
        )
    close = starts or [
        _index()[c][1]["one"]
        for c in difflib.get_close_matches(key, list(_index()), n=5, cutoff=0.6)
        if _index()[c][0] == "aa"
    ]
    hint = ""
    if close:
        unique = [by_one(o) for o in dict.fromkeys(close)]
        names = ", ".join(f"{a['three']} ({a['name']})" for a in unique)
        hint = f" Did you mean: {names}?"
    raise ToolError(f"Unknown amino acid {query!r}.{hint}")


# ---------------------------------------------------------------------------
# 2D drawings
# ---------------------------------------------------------------------------

# Backbone atoms N, Calpha, C', =O, O- at fixed 2D positions (bond length 1.5):
# N on the left, carboxylate on the right, side chain pointing up.
_BACKBONE = "[NX3,NX4+;!$(NC=O)][CX4][CX3](=O)[OX1-,OX2H1]"
_BACKBONE_XY = [(-1.299, -0.75), (0.0, 0.0), (1.299, -0.75), (1.299, -2.25), (2.598, 0.0)]

# Class colors (RGB 0-1), the same hues as the Raycast tags and the periodic-table blocks.
CLASS_COLORS = {
    "nonpolar": (0.96, 0.62, 0.04),
    "aromatic": (0.55, 0.36, 0.96),
    "polar": (0.06, 0.73, 0.51),
    "positive": (0.23, 0.51, 0.96),
    "negative": (0.96, 0.25, 0.37),
    "other": (0.42, 0.45, 0.50),
}
DRAWING_PX = 260
BANNER_PX = (520, 210)  # wide card for the side panel of a list (Raycast)
CARD_PX = 360
BORDER_PX = 3.5  # card border in the class color


def class_hex(cls: str) -> str:
    return "#" + "".join(f"{round(v * 255):02x}" for v in CLASS_COLORS[cls])


@cache
def _layout(one: str):
    """The pH-7 form with 2D coordinates, the backbone pinned; and the side-chain atoms."""
    from rdkit import Chem
    from rdkit.Chem import rdDepictor
    from rdkit.Geometry import Point2D

    mol = Chem.MolFromSmiles(by_one(one)["smiles_ph7"])
    match = mol.GetSubstructMatch(Chem.MolFromSmarts(_BACKBONE))
    coord_map = {i: Point2D(*xy) for i, xy in zip(match, _BACKBONE_XY, strict=True)}
    rdDepictor.SetPreferCoordGen(False)  # coordMap is honored by the RDKit depictor
    rdDepictor.Compute2DCoords(mol, coordMap=coord_map)
    Chem.WedgeMolBonds(mol, mol.GetConformer())
    side = [a.GetIdx() for a in mol.GetAtoms() if a.GetIdx() not in match]
    return mol, side


_PAD = 0.75  # drawing units around the molecule (room for atom labels such as H3N+)
_MIN_HALF = 2.4  # smallest half-height of the drawing area: Gly is not blown up


def _extent(one: str) -> tuple[float, float, float, float]:
    """Bounding box (x0, y0, x1, y1) of a molecule's 2D coordinates."""
    pos = _layout(one)[0].GetConformer().GetPositions()
    return pos[:, 0].min(), pos[:, 1].min(), pos[:, 0].max(), pos[:, 1].max()


def drawing_svg(one: str, px: int = DRAWING_PX, height: int | None = None) -> str:
    """The 2D drawing on a white card whose border has the class color: each molecule
    centered and scaled to fill the card. `px` is the width; `height` (default: the
    same, a square card) makes a wide banner, e.g. for a side panel."""
    from rdkit.Chem.Draw import rdMolDraw2D
    from rdkit.Geometry import Point2D

    record = by_one(one)
    mol, side = _layout(one)
    bonds = [
        b.GetIdx()
        for b in mol.GetBonds()
        if b.GetBeginAtomIdx() in side or b.GetEndAtomIdx() in side
    ]
    h = height or px
    d = rdMolDraw2D.MolDraw2DSVG(px, h)
    opts = d.drawOptions()
    opts.clearBackground = False  # the white card is added below
    opts.addStereoAnnotation = False
    opts.padding = 0.05
    x0, y0, x1, y1 = _extent(one)
    # A drawing area with the card's aspect ratio that just holds the molecule.
    half_w, half_h = (x1 - x0) / 2 + _PAD, max((y1 - y0) / 2 + _PAD, _MIN_HALF)
    half_w, half_h = max(half_w, half_h * px / h), max(half_h, half_w * h / px)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    d.SetScale(px, h, Point2D(cx - half_w, cy - half_h), Point2D(cx + half_w, cy + half_h))
    color = (*CLASS_COLORS[record["class"]], 0.3)
    d.DrawMolecule(
        mol,
        highlightAtoms=side,
        highlightBonds=bonds,
        highlightAtomColors={i: color for i in side},
        highlightBondColors={i: color for i in bonds},
    )
    d.FinishDrawing()
    return with_backdrop(d.GetDrawingText(), border=class_hex(record["class"]), stroke=BORDER_PX)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def class_title(cls: str) -> str:
    return dataset()["meta"]["classes"][cls]


def _num(value: float | None, digits: int) -> str:
    return "—" if value is None else f"{value:.{digits}f}".replace("-", "−")


def _signed(value: float | None) -> str:
    if value is None:
        return "—"
    return (f"+{value:.1f}" if value > 0 else f"{value:.1f}").replace("-", "−")


def stereo_text(a: AminoAcid) -> str:
    s = a["stereo"]["text"]
    return "achiral (no L/D)" if s == "achiral" else f"L · {s}"


SHORT = {"ccd": "CCD", "pubchem": "PubChem", "chebi": "ChEBI"}


def mass_check(a: AminoAcid, key: str) -> str:
    c = a["mass_check"]
    refs = ", ".join(c[f"{key}_refs"])
    return f"✓ {refs}" if c[key] == "verified" else f"? {refs}"


def _summary(a: AminoAcid) -> dict[str, Any]:
    """The fields screens need for a list or grid (no 3D coordinates)."""
    fields = {k: v for k, v in a.items() if k != "coords3d"}
    return {**fields, "class_title": class_title(a["class"])}


def _references(keys: list[str]) -> list[str]:
    refs = dataset()["meta"]["references"]
    return [refs[k]["citation"] for k in keys]


DRAWING_NOTE = (
    "2D drawings: the dominant charge state near pH 7 (zwitterion; Asp and Glu "
    "deprotonated, Lys and Arg protonated, His neutral), side chain highlighted in the "
    "color of its class, on a card with a border of the same color. The backbone has "
    "the same orientation in every drawing; each molecule is scaled to fill its card, "
    "so sizes are not comparable between drawings. Sec is drawn as the selenol, "
    "although at pH 7 it is largely deprotonated."
)
PKA_NOTE = (
    "pKa and pI are provisional: one textbook table (Lehninger, 7th ed.), not yet "
    "cross-checked; published values differ by 0.1–0.5 units, and side chains in proteins "
    "can differ by several units. pI is computed from these pKa values (zero net charge)."
)
MASS_NOTE = (
    "Residue mass = amino acid − H₂O (the unit inside a peptide chain). Monoisotopic: most "
    "abundant isotopes (AME2020); average: CIAAW 2024 abridged atomic weights."
)
CLASS_NOTE = (
    "Classes follow Lehninger's five side-chain groups. Borderline cases: His is only "
    "partly protonated at pH 7; Tyr and Trp are aromatic but also somewhat polar; Cys is "
    "sometimes listed as nonpolar; Gly has no side chain."
)


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


def _overview(cls: str | None) -> ToolResult:
    chosen = [a for a in amino_acids() if cls is None or a["class"] == cls]
    folder = workdir() / "drawings"
    folder.mkdir(exist_ok=True)
    artifacts = []
    for a in chosen:
        path = folder / f"{a['one']}-{a['three']}.svg"
        path.write_text(drawing_svg(a["one"]), encoding="utf-8")
        artifacts.append(
            Artifact(kind="svg", path=path, title=f"{a['three']} · {a['one']}", note=a["name"])
        )
    rows = [
        [a["one"], a["three"], a["name"], class_title(a["class"]),
         _num(a["mass"]["residue_mono"], 5), _num(a["pi"], 2), _signed(a["hydropathy_kd"])]
        for a in chosen
    ]  # fmt: skip
    if cls is None:
        answer = "22 amino acids · 20 standard + selenocysteine (U) and pyrrolysine (O)"
    else:
        answer = f"{class_title(cls)} · {len(chosen)} amino acids"
    meta = dataset()["meta"]
    return ToolResult(
        answer=answer,
        tables=[
            Table(
                title="Amino acids",
                columns=["1", "3", "Name", "Class", "Residue mass (mono)", "pI", "Hydropathy"],
                rows=rows,
            ),
            *(
                [
                    Table(
                        title="Ambiguity codes",
                        columns=["1", "3", "Meaning"],
                        rows=[[b["one"], b["three"], b["meaning"]] for b in dataset()["ambiguous"]],
                    )
                ]
                if cls is None
                else []
            ),
        ],
        artifacts=artifacts,
        notes=[DRAWING_NOTE, CLASS_NOTE, MASS_NOTE, PKA_NOTE],
        sources=_references(["jcbn1984", "lehninger7", "kd1982", "ccd", "pubchem", "chebi"]),
        data={
            "classes": meta["classes"],
            "amino_acids": [_summary(a) for a in chosen],
            "ambiguous": dataset()["ambiguous"],
            "drawings": {a["one"]: drawing_svg(a["one"]) for a in chosen},
            "banners": {a["one"]: drawing_svg(a["one"], *BANNER_PX) for a in chosen},
        },
    )


def structure3d(a: AminoAcid) -> Structure3D:
    c = a["coords3d"]
    marks = []
    if c["alpha"] is not None and a["stereo"]["alpha"]:
        marks.append(Mark(atoms=[c["alpha"]], label=f"Cα {a['stereo']['alpha']}"))
    form = "side chain protonated, as stored in CCD" if c["charge"] else "neutral form"
    return Structure3D(
        frames=[
            Frame(
                symbols=c["symbols"],
                coords=[tuple(p) for p in c["coords"]],
                comment=f"{a['name']} · CCD {a['ids']['ccd']} ideal coordinates · {form}",
                numbers=c["names"],
                marks=marks,
            )
        ],
        title=f"{a['name']} ({a['three']}, {a['one']})",
        numbers_name="Atom names",
    )


def _card(a: AminoAcid) -> ToolResult:
    path = workdir() / f"{a['one']}-{a['three']}.svg"
    svg = drawing_svg(a["one"], CARD_PX)
    path.write_text(svg, encoding="utf-8")
    m, pka = a["mass"], a["pka"]
    structure = "✓ CCD, PubChem, ChEBI"
    pka_check = "provisional" if pka["status"] == "provisional" else "—"
    kd_check = "≈ Kyte–Doolittle 1982, ExPASy" if a["hydropathy_kd"] is not None else "—"
    codons = ", ".join(a["codons"]) or "—"

    tables = [
        Table(
            title="Identity",
            columns=["Property", "Value", "Check"],
            minor_columns=[2],
            rows=[
                ["One-letter code", a["one"], "def JCBN 1984"],
                ["Three-letter code", a["three"], "def JCBN 1984"],
                ["Name", a["name"], "def JCBN 1984"],
                ["IUPAC name", a["iupac_name"] or "—", "PubChem"],
                ["Class", class_title(a["class"]), "Lehninger"],
                ["Essential (humans)", "yes" if a["essential"] else "no", "Lehninger"],
                ["Formula", a["formula"], structure],
                ["Stereochemistry", stereo_text(a), structure],
                ["SMILES (neutral)", a["smiles"], structure],
                ["SMILES (pH 7 form)", a["smiles_ph7"], "drawn form"],
                ["InChIKey", a["inchikey"], structure],
                [
                    "IDs",
                    f"CCD {a['ids']['ccd']} · PubChem CID {a['ids']['pubchem_cid']} · "
                    f"{a['ids']['chebi']}",
                    "",
                ],  # fmt: skip
            ],
        ),
        Table(
            title="Mass",
            columns=["Property", "Value", "Check"],
            minor_columns=[2],
            rows=[
                [
                    "Residue mass, monoisotopic (u)",
                    _num(m["residue_mono"], 5),
                    mass_check(a, "mono"),
                ],
                ["Residue mass, average (g/mol)", _num(m["residue_avg"], 2), mass_check(a, "avg")],
                ["Molecular mass, monoisotopic (u)", _num(m["mono"], 5), mass_check(a, "mono")],
                ["Molecular weight, average (g/mol)", _num(m["avg"], 2), mass_check(a, "avg")],
            ],  # fmt: skip
        ),
        Table(
            title="Acid–base",
            columns=["Property", "Value", "Check"],
            minor_columns=[2],
            rows=[
                ["pKa, α-COOH", _num(pka["alpha_cooh"], 2), pka_check],
                ["pKa, α-NH₃⁺", _num(pka["alpha_nh3"], 2), pka_check],
                [
                    "pKa, side chain",
                    _num(pka["side_chain"], 2),
                    pka_check if pka["side_chain"] is not None else "",
                ],
                ["pI (computed)", _num(a["pi"], 2), pka_check],
            ],
        ),
        Table(
            title="Hydropathy and genetics",
            columns=["Property", "Value", "Check"],
            minor_columns=[2],
            rows=[
                ["Hydropathy (Kyte–Doolittle)", _signed(a["hydropathy_kd"]), kd_check],
                ["Codons (standard code)", codons, "def NCBI table 1" if a["codons"] else ""],
                *([["Codon note", a["codons_note"], ""]] if a["codons_note"] else []),
            ],
        ),
    ]

    notes = [DRAWING_NOTE, MASS_NOTE, CLASS_NOTE]
    if pka["status"] == "provisional":
        notes.insert(0, PKA_NOTE)
    notes.append(
        "3D: wwPDB CCD ideal coordinates (a standard geometry, not an experimental "
        "structure), with all hydrogens. CCD stores Lys, Arg and His with a protonated side "
        "chain, the others as the neutral molecule. The number button shows PDB atom names."
    )
    if a["mass_check"]["avg"] != "verified":
        notes.append(
            "Average mass: the databases still use the older atomic weight of Se (78.96, "
            "before CIAAW 2013); this value uses 78.971."
        )
    return ToolResult(
        answer=f"{a['name']} · {a['three']} · {a['one']}",
        highlights=[
            Highlight(label="Class", value=class_title(a["class"])),
            Highlight(
                label="Residue mass (mono)",
                value=f"{_num(m['residue_mono'], 5)} u",
                note=f"Check {mass_check(a, 'mono')}",
            ),
            Highlight(label="pI", value=_num(a["pi"], 2), note="Provisional (pKa from one table)"),
            Highlight(label="Hydropathy (K–D)", value=_signed(a["hydropathy_kd"])),
            Highlight(label="Stereo", value=stereo_text(a)),
            Highlight(label="Codons", value=codons),
        ],
        tables=tables,
        structures=[structure3d(a)],
        artifacts=[
            Artifact(
                kind="svg",
                path=path,
                title=f"{a['three']} · {a['one']}",
                note=f"{a['name']} · pH 7 form",
            )
        ],  # fmt: skip
        notes=notes,
        sources=_references(
            ["jcbn1984", "ccd", "pubchem", "chebi", "lehninger7", "kd1982", "expasy", "ncbi_gc"]
        )
        + ["Masses: element data of the `element` tool (AME2020, CIAAW 2024)."],
        data={
            "amino_acid": _summary(a),
            "drawing": svg,
        },
    )


def _ambiguous(b: dict[str, Any]) -> ToolResult:
    members = [by_one(o) for o in b["members"]]
    return ToolResult(
        answer=f"{b['one']} · {b['three']} · {b['meaning']}",
        tables=[
            Table(
                title="Stands for",
                columns=["1", "3", "Name", "Class"],
                rows=[[a["one"], a["three"], a["name"], class_title(a["class"])] for a in members],
            )
        ]
        if members
        else [],
        notes=[
            "An ambiguity code has no single structure. Open one of the amino acids it "
            "stands for to see its structure and properties."
        ],  # fmt: skip
        sources=_references(["jcbn1984"]),
        data={"ambiguous": b},
    )
