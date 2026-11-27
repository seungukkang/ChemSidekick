"""Build the amino-acid data (BIO-01 `aa`) by cross-checking the sources.

    uv run python scripts/fetch_amino_acids.py   # once: download the sources
    uv run python scripts/build_amino_acids.py   # write the JSON and the report
    uv run python scripts/build_amino_acids.py --check   # exit 1 if out of date

Inputs (data/sources/aa/): curated.toml (hand-entered), ccd/*.cif, pubchem.json,
chebi.json, expasy_kd.txt, ncbi_gc.prt.

Outputs:
    src/chemsidekick/tools/biochemistry/data/amino_acids.json
    data/verification/amino_acids.md

Checks (any failed structure check stops the build):
    structure   curated SMILES, CCD (InChIKey and the molecule rebuilt from its
                ideal 3D coordinates), PubChem and ChEBI give one InChIKey;
                the 2D (pH 7) form is the same molecule once neutralized
    stereo      CIP labels of Calpha / Cbeta from RDKit match the curated label
    mass        computed from the verified element data; compared with PubChem,
                ChEBI and CCD (status only, not a stop)
    hydropathy  curated Kyte-Doolittle values = ExPASy copy
    codons      from NCBI table 1 (a definition)
    pKa         one textbook table: provisional (plan 006 Q4)
"""

import argparse
import json
import re
import shlex
import sys
import tomllib
from collections import Counter
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem import rdCIPLabeler
from rdkit.Chem.MolStandardize import rdMolStandardize
from rdkit.Chem.rdMolDescriptors import CalcMolFormula

RDLogger.DisableLog("rdApp.*")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "sources" / "aa"
OUT_JSON = ROOT / "src/chemsidekick/tools/biochemistry/data/amino_acids.json"
OUT_REPORT = ROOT / "data/verification/amino_acids.md"
ELEMENTS = ROOT / "src/chemsidekick/tools/reference/data/elements.json"

MONO_TOL = 1e-4  # u
AVG_TOL = 0.01  # g/mol

CLASSES = {
    "nonpolar": "Nonpolar, aliphatic",
    "aromatic": "Aromatic",
    "polar": "Polar, uncharged",
    "positive": "Positively charged",
    "negative": "Negatively charged",
    "other": "Other proteinogenic",
}

# Ionizable groups: which pKa entries are acids (lose H+ to become -1 or 0).
ACIDIC_SIDE_CHAINS = {"C", "Y", "D", "E"}


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


def cif_loops(text: str) -> dict[str, list[dict[str, str]]]:
    """The loop_ tables of a CCD mmCIF file: category -> rows (field -> value)."""
    loops: dict[str, list[dict[str, str]]] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip() != "loop_":
            i += 1
            continue
        i += 1
        fields = []
        while i < len(lines) and lines[i].startswith("_"):
            fields.append(lines[i].strip())
            i += 1
        category = fields[0].split(".")[0]
        names = [f.split(".", 1)[1] for f in fields]
        rows = []
        while i < len(lines) and not lines[i].startswith(("#", "loop_", "_")):
            values = shlex.split(lines[i], posix=True)
            if values:
                rows.append(dict(zip(names, values, strict=True)))
            i += 1
        loops[category] = rows
    return loops


def cif_value(text: str, key: str) -> str:
    m = re.search(rf"^{re.escape(key)}\s+(.+)$", text, re.M)
    return shlex.split(m.group(1))[0] if m else ""


def ccd_entry(ccd_id: str) -> dict:
    text = (SRC / "ccd" / f"{ccd_id}.cif").read_text(encoding="utf-8")
    loops = cif_loops(text)
    descriptors = {
        (d["type"], d["program"]): d["descriptor"] for d in loops["_pdbx_chem_comp_descriptor"]
    }
    atoms = [
        {
            "name": a["atom_id"],
            "symbol": a["type_symbol"].capitalize(),
            "charge": int(a["charge"]),
            "xyz": [
                float(a["pdbx_model_Cartn_x_ideal"]),
                float(a["pdbx_model_Cartn_y_ideal"]),
                float(a["pdbx_model_Cartn_z_ideal"]),
            ],
        }
        for a in loops["_chem_comp_atom"]
    ]
    bonds = [(b["atom_id_1"], b["atom_id_2"], b["value_order"]) for b in loops["_chem_comp_bond"]]
    return {
        "inchikey": descriptors.get(("InChIKey", "InChI"), ""),
        "formula": cif_value(text, "_chem_comp.formula").replace(" ", ""),
        "formula_weight": float(cif_value(text, "_chem_comp.formula_weight")),
        "charge": int(cif_value(text, "_chem_comp.pdbx_formal_charge") or 0),
        "atoms": atoms,
        "bonds": bonds,
    }


def mol_from_ccd(entry: dict) -> Chem.Mol:
    """The molecule rebuilt from the CCD atoms, bonds and ideal coordinates."""
    order = {"SING": Chem.BondType.SINGLE, "DOUB": Chem.BondType.DOUBLE,
             "TRIP": Chem.BondType.TRIPLE}  # fmt: skip
    rw = Chem.RWMol()
    index = {}
    for a in entry["atoms"]:
        atom = Chem.Atom(a["symbol"])
        atom.SetFormalCharge(a["charge"])
        atom.SetNoImplicit(True)
        index[a["name"]] = rw.AddAtom(atom)
    for a1, a2, o in entry["bonds"]:
        rw.AddBond(index[a1], index[a2], order[o])
    conf = Chem.Conformer(rw.GetNumAtoms())
    for a in entry["atoms"]:
        conf.SetAtomPosition(index[a["name"]], a["xyz"])
    rw.AddConformer(conf, assignId=True)
    mol = rw.GetMol()
    Chem.SanitizeMol(mol)
    Chem.AssignStereochemistryFrom3D(mol)
    return mol


def pubchem_records() -> dict[int, dict]:
    data = json.loads((SRC / "pubchem.json").read_text(encoding="utf-8"))
    return {p["CID"]: p for p in data["PropertyTable"]["Properties"]}


def expasy_kd() -> dict[str, float]:
    three_to_one = {aa["three"]: aa["one"] for aa in curated()["amino_acid"]}
    out = {}
    for line in (SRC / "expasy_kd.txt").read_text().splitlines():
        m = re.match(r"([A-Z][a-z]{2}):\s*(-?[\d.]+)", line)
        if m:
            out[three_to_one[m.group(1)]] = float(m.group(2))
    return out


def ncbi_codons() -> dict[str, list[str]]:
    """Standard code (NCBI table 1): one-letter code ('*' = stop) -> RNA codons."""
    text = (SRC / "ncbi_gc.prt").read_text(encoding="latin-1")
    block = re.search(r"id 1 ,(.*?)\}", text, re.S).group(1)
    aas = re.search(r'ncbieaa\s+"([^"]+)"', block).group(1)
    bases = [re.search(rf"Base{n}\s+([TCAG]+)", block).group(1) for n in (1, 2, 3)]
    out: dict[str, list[str]] = {}
    for i, aa in enumerate(aas):
        codon = (bases[0][i] + bases[1][i] + bases[2][i]).replace("T", "U")
        out.setdefault(aa, []).append(codon)
    return out


def curated() -> dict:
    return tomllib.loads((SRC / "curated.toml").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Derived values
# ---------------------------------------------------------------------------


def element_masses() -> tuple[dict[str, float], dict[str, float], dict[str, str]]:
    """Per element: mass of the most abundant isotope, abridged atomic weight, its status."""
    data = json.loads(ELEMENTS.read_text(encoding="utf-8"))
    mono, avg, status = {}, {}, {}
    for el in data["elements"]:
        if el["isotopes"]:
            top = max(el["isotopes"], key=lambda i: i["abundance"]["value"] or 0)
            mono[el["symbol"]] = top["mass"]["value"]
        if el["abridged_weight"]["value"] is not None:
            avg[el["symbol"]] = el["abridged_weight"]["value"]
            status[el["symbol"]] = el["abridged_weight"]["status"]
    return mono, avg, status


def formula_counts(formula: str) -> Counter:
    counts: Counter = Counter()
    for sym, n in re.findall(r"([A-Z][a-z]?)(\d*)", formula):
        counts[sym] += int(n) if n else 1
    return counts


def masses(formula: str) -> dict[str, float]:
    mono, avg, _ = element_masses()
    counts = formula_counts(formula)
    m = sum(mono[s] * n for s, n in counts.items())
    a = sum(avg[s] * n for s, n in counts.items())
    water_m = 2 * mono["H"] + mono["O"]
    water_a = 2 * avg["H"] + avg["O"]
    return {
        "mono": m,
        "avg": a,
        "residue_mono": m - water_m,
        "residue_avg": a - water_a,
    }


def backbone(mol: Chem.Mol) -> tuple[int, int, int] | None:
    """(N, Calpha, C') atom indexes of the alpha-amino acid backbone."""
    patt = Chem.MolFromSmarts("[NX3,NX4+;!$(NC=O)][CX4][CX3](=O)[OX2H1,OX1-]")
    m = mol.GetSubstructMatch(patt)
    return (m[0], m[1], m[2]) if m else None


def cip_labels(smiles: str) -> dict:
    """CIP labels: Calpha, Cbeta (if it is a stereocenter), and any others."""
    mol = Chem.MolFromSmiles(smiles)
    rdCIPLabeler.AssignCIPLabels(mol)
    n, ca, c = backbone(mol)
    cb = next(
        (x.GetIdx() for x in mol.GetAtomWithIdx(ca).GetNeighbors() if x.GetIdx() not in (n, c)),
        None,
    )
    labels = {"alpha": None, "beta": None, "other": []}
    for atom in mol.GetAtoms():
        if not atom.HasProp("_CIPCode"):
            continue
        code = atom.GetProp("_CIPCode")
        if atom.GetIdx() == ca:
            labels["alpha"] = code
        elif atom.GetIdx() == cb:
            labels["beta"] = code
        else:
            labels["other"].append(code)
    return labels


def stereo_text(labels: dict) -> str:
    if labels["alpha"] is None:
        return "achiral"
    text = f"(2{labels['alpha']}" + (f",3{labels['beta']}" if labels["beta"] else "") + ")"
    if labels["other"]:
        text += " + " + ",".join(sorted(labels["other"])) + " in the side chain"
    return text


def isoelectric_point(one: str, pka: list[float]) -> float | None:
    """pH of zero net charge (Henderson–Hasselbalch, bisection)."""
    if len(pka) < 2:
        return None
    groups = [(pka[0], "acid"), (pka[1], "base")]
    if len(pka) == 3:
        groups.append((pka[2], "acid" if one in ACIDIC_SIDE_CHAINS else "base"))

    def charge(ph: float) -> float:
        q = 0.0
        for pk, kind in groups:
            if kind == "acid":
                q -= 1 / (1 + 10 ** (pk - ph))
            else:
                q += 1 / (1 + 10 ** (ph - pk))
        return q

    lo, hi = 0.0, 14.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if charge(mid) > 0:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 2)


def neutral_key(smiles: str) -> str:
    mol = rdMolStandardize.Uncharger().uncharge(Chem.MolFromSmiles(smiles))
    return Chem.MolToInchiKey(mol)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


class BuildError(Exception):
    pass


def build() -> tuple[dict, list[str]]:
    cur = curated()
    pubchem = pubchem_records()
    chebi = json.loads((SRC / "chebi.json").read_text(encoding="utf-8"))
    kd_expasy = expasy_kd()
    codons = ncbi_codons()
    retrieved = json.loads((SRC / "retrieved.json").read_text())
    _, _, avg_status = element_masses()

    out_aas = []
    report_rows = []
    mass_rows = []
    errors = []
    for aa in cur["amino_acid"]:
        one = aa["one"]
        mol = Chem.MolFromSmiles(aa["smiles"])
        key = Chem.MolToInchiKey(mol)
        ccd = ccd_entry(aa["ccd"])
        ccd_mol = mol_from_ccd(ccd)
        pc = pubchem[aa["pubchem_cid"]]
        cb = chebi[str(aa["chebi"])]
        keys = {
            "CCD": ccd["inchikey"],
            "CCD 3D": Chem.MolToInchiKey(ccd_mol),
            "PubChem": pc["InChIKey"],
            "ChEBI": cb["inchikey"],
        }
        # The last InChIKey character is the protonation layer: CCD stores Lys, His
        # and Arg with a protonated side chain (+1), the other sources as neutral.
        bad = [src for src, k in keys.items() if k[:-1] != key[:-1]]
        if ccd["charge"] == 0 and ccd["inchikey"] != key:
            bad.append("CCD (protonation)")
        if bad:
            errors.append(f"{one}: InChIKey {key} differs from {', '.join(bad)}: {keys}")
        if neutral_key(aa["smiles_ph7"]) != key:
            errors.append(f"{one}: smiles_ph7 is not the same molecule as smiles")
        formula = CalcMolFormula(mol)
        formulas = {"CCD": ccd["formula"], "PubChem": pc["MolecularFormula"],
                    "ChEBI": cb["chemical_data"]["formula"]}  # fmt: skip
        ccd_neutral = formula_counts(ccd["formula"])
        ccd_neutral["H"] -= ccd["charge"]
        formulas["CCD"] = (
            CalcMolFormula(Chem.MolFromSmiles(aa["smiles"]))
            if (ccd_neutral == formula_counts(formula))
            else ccd["formula"]
        )
        if any(formula_counts(f) != formula_counts(formula) for f in formulas.values()):
            errors.append(f"{one}: formula {formula} differs: {formulas}")

        labels = cip_labels(aa["smiles"])
        labels_3d = cip_labels(Chem.MolToSmiles(Chem.RemoveHs(ccd_mol)))
        if labels != labels_3d:
            errors.append(f"{one}: CIP from SMILES {labels} != from CCD 3D {labels_3d}")
        if one != "G" and labels["alpha"] is None:
            errors.append(f"{one}: no stereocenter at Calpha")

        m = masses(formula)
        checks = {
            "PubChem": (float(pc["MonoisotopicMass"]), float(pc["MolecularWeight"])),
            "ChEBI": (
                float(cb["chemical_data"]["monoisotopic_mass"]),
                float(cb["chemical_data"]["mass"]),
            ),  # fmt: skip
            # CCD's weight is for its own protonation state; compared only when neutral.
            **({"CCD": (None, ccd["formula_weight"])} if ccd["charge"] == 0 else {}),
        }
        mono_ok = [s for s, (mo, _) in checks.items() if mo is not None
                   and abs(mo - m["mono"]) <= MONO_TOL]  # fmt: skip
        avg_ok = [s for s, (_, av) in checks.items() if abs(av - m["avg"]) <= AVG_TOL]
        mass_rows.append((one, aa["three"], m, checks, mono_ok, avg_ok))

        kd = cur["kd1982"].get(one)
        kd_status = None
        if kd is not None:
            if kd_expasy.get(one) != kd:
                errors.append(f"{one}: Kyte–Doolittle {kd} != ExPASy {kd_expasy.get(one)}")
            kd_status = "partial"  # paper (transcribed) + ExPASy: 2 references

        aa_codons = codons.get(one, [])
        pka = aa["pka"]
        pi = isoelectric_point(one, pka)

        atoms = ccd["atoms"]
        index = {a["name"]: i for i, a in enumerate(atoms)}
        ca_index = index.get("CA")
        out_aas.append(
            {
                "one": one,
                "three": aa["three"],
                "name": aa["name"],
                "class": aa["class"],
                "essential": aa["essential"],
                "ids": {
                    "ccd": aa["ccd"],
                    "pubchem_cid": aa["pubchem_cid"],
                    "chebi": f"CHEBI:{aa['chebi']}",
                },  # fmt: skip
                "smiles": aa["smiles"],
                "smiles_ph7": aa["smiles_ph7"],
                "inchikey": key,
                "formula": formula,
                "iupac_name": pc.get("IUPACName", ""),
                "stereo": {
                    "alpha": labels["alpha"],
                    "beta": labels["beta"],
                    "other": labels["other"],
                    "text": stereo_text(labels),
                },  # fmt: skip
                "mass": {k: round(v, 6) for k, v in m.items()},
                "mass_check": {
                    "mono": "verified" if len(mono_ok) >= 2 else "unverified",
                    "mono_refs": mono_ok,
                    "avg": "verified" if len(avg_ok) >= 2 else "unverified",
                    "avg_refs": avg_ok,
                },
                "pka": {
                    "alpha_cooh": pka[0] if pka else None,
                    "alpha_nh3": pka[1] if len(pka) > 1 else None,
                    "side_chain": pka[2] if len(pka) > 2 else None,
                    "status": "provisional" if pka else "none",
                    "refs": ["lehninger7"] if pka else [],
                },
                "pi": pi,
                "hydropathy_kd": kd,
                "hydropathy_status": kd_status,
                "codons": aa_codons,
                "codons_note": aa.get("codons_note", ""),
                "structure_refs": ["ccd", "pubchem", "chebi"],
                "coords3d": {
                    "names": [a["name"] for a in atoms],
                    "symbols": [a["symbol"] for a in atoms],
                    "coords": [[round(v, 3) for v in a["xyz"]] for a in atoms],
                    "alpha": ca_index,
                    "charge": ccd["charge"],
                },
            }
        )
        report_rows.append(
            f"| {one} | {aa['three']} | {formula} | `{key}` | "
            f"{'✓' if not bad else '✗ ' + ', '.join(bad)} | {stereo_text(labels)} | "
            f"{kd if kd is not None else '—'} | {len(aa_codons)} |"
        )

    covered = {aa["one"] for aa in cur["amino_acid"]}
    for aa_code, cods in codons.items():
        if aa_code != "*" and aa_code not in covered:
            errors.append(f"NCBI table 1 has {aa_code} ({cods}) not in curated.toml")
    if errors:
        raise BuildError("\n".join(errors))

    data = {
        "meta": {
            "retrieved": retrieved,
            "classes": CLASSES,
            "references": cur["references"],
            "stop_codons": codons.get("*", []),
            "element_weight_status": {s: avg_status[s] for s in ("H", "C", "N", "O", "S", "Se")},
        },
        "amino_acids": out_aas,
        "ambiguous": cur["ambiguous"],
    }
    report = render_report(data, report_rows, mass_rows)
    return data, report


def render_report(data: dict, rows: list[str], mass_rows: list) -> str:
    refs = data["meta"]["references"]
    lines = [
        "# Amino-acid data verification report",
        "",
        "Built by `scripts/build_amino_acids.py` from `data/sources/aa/`. Do not edit by hand.",
        "",
        "Sources retrieved: "
        + ", ".join(f"{k} {v}" for k, v in data["meta"]["retrieved"].items())
        + ".",
        "",
        "## Structures",
        "",
        "Each structure is the same molecule (standard InChIKey) in the curated SMILES, the "
        "CCD InChIKey, the molecule rebuilt from the CCD bonds and **ideal 3D coordinates** "
        "(stereo from 3D), PubChem and ChEBI. CIP labels are computed by RDKit from the "
        "SMILES and from the CCD 3D model and must agree. Any difference stops the build. "
        "CCD stores Lys, His and Arg with a protonated side chain (+1); for these the "
        "InChIKey protonation character (last letter) is ignored.",
        "",
        "| 1 | 3 | Formula | InChIKey | Structure | Stereo (CIP) | Kyte–Doolittle | Codons |",
        "|---|---|---|---|---|---|---|---|",
        *rows,
        "",
        "## Masses",
        "",
        "Computed from the formula with element data of the `element` tool: monoisotopic = "
        "most abundant isotope (AME2020, verified), average = CIAAW 2024 abridged atomic "
        "weights (verified). Residue mass = molecule − H₂O. Compared with PubChem, ChEBI and "
        f"CCD within {MONO_TOL} u (monoisotopic) and {AVG_TOL} g/mol (average). "
        "Verified = at least 2 databases agree with the computed value.",
        "",
        "| 1 | 3 | Mono (u) | Agreeing | Average (g/mol) | Agreeing | Residue mono | Residue avg |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for one, three, m, checks, mono_ok, avg_ok in mass_rows:
        found = "; ".join(
            f"{s} {mo if mo is not None else '—'} / {av}" for s, (mo, av) in checks.items()
        )
        lines.append(
            f"| {one} | {three} | {m['mono']:.6f} | {', '.join(mono_ok) or 'none'} | "
            f"{m['avg']:.3f} | {', '.join(avg_ok) or 'none'} | {m['residue_mono']:.6f} | "
            f"{m['residue_avg']:.3f} |"
        )
    lines += ["", "Values found (mono / average):", ""]
    for one, _three, _m, checks, _mo, _av in mass_rows:
        found = "; ".join(
            f"{s} {mo if mo is not None else '—'} / {av}" for s, (mo, av) in checks.items()
        )
        lines.append(f"- {one}: {found}")
    lines += [
        "",
        "## Hydropathy (Kyte–Doolittle)",
        "",
        "Transcribed from the original paper and equal to the ExPASy ProtScale copy for all 20. "
        "Shown as ≈ (2 references): the paper defines the scale; a third copy is still to add.",
        "",
        "## Codons",
        "",
        "From NCBI translation table 1 (the standard code, a definition). Every codon maps to "
        "one of the 20 amino acids or a stop; Sec (UGA) and Pyl (UAG) reuse stop codons in "
        "special contexts.",
        "",
        "## pKa and pI — provisional",
        "",
        "pKa values are from one textbook table (Lehninger, 7th ed., Table 3-1) and are **not** "
        "cross-checked yet; pKa values differ between sources by 0.1–0.5 units (plan 006 Q4). "
        "pI is computed from these pKa values (zero net charge, Henderson–Hasselbalch).",
        "",
        "## References",
        "",
        *[f"- **{k}**: {v['citation']}" for k, v in refs.items()],
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="exit 1 if outputs are out of date")
    args = parser.parse_args()
    try:
        data, report = build()
    except BuildError as e:
        print(f"Build failed:\n{e}", file=sys.stderr)
        sys.exit(1)
    text = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
    if args.check:
        stale = [p for p, t in ((OUT_JSON, text), (OUT_REPORT, report))
                 if not p.exists() or p.read_text(encoding="utf-8") != t]  # fmt: skip
        if stale:
            print("Out of date: " + ", ".join(str(p.relative_to(ROOT)) for p in stale))
            sys.exit(1)
        return
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(text, encoding="utf-8")
    OUT_REPORT.write_text(report, encoding="utf-8")
    print(f"Wrote {OUT_JSON.relative_to(ROOT)} and {OUT_REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
