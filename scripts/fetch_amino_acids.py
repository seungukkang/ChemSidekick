"""Download reference data for the amino-acid tool (BIO-01) into data/sources/aa/.

    uv run python scripts/fetch_amino_acids.py

Saved as published, so scripts/build_amino_acids.py can compare the sources:

    ccd/<ID>.cif        wwPDB Chemical Component Dictionary entry (SMILES, formula,
                        InChIKey, ideal 3D coordinates)
    pubchem.json        PubChem properties per CID (SMILES, formula, InChIKey, masses)
    chebi.json          ChEBI entries (InChIKey, formula, masses)
    expasy_kd.txt       ExPASy ProtScale copy of the Kyte-Doolittle hydropathy scale
    ncbi_gc.prt         NCBI genetic code tables (table 1 = standard code)
    retrieved.json      retrieval date of each file
"""

import json
import re
import ssl
import time
import tomllib
import urllib.request
from datetime import date
from pathlib import Path

import certifi

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sources" / "aa"
CURATED = OUT / "curated.toml"
USER_AGENT = "ChemSidekick-data-fetch/0.1 (personal research tool)"
CONTEXT = ssl.create_default_context(cafile=certifi.where())

CCD_URL = "https://files.rcsb.org/ligands/view/{id}.cif"
PUBCHEM_URL = (
    "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cids}/property/"
    "SMILES,MolecularFormula,InChIKey,MonoisotopicMass,MolecularWeight,IUPACName/JSON"
)
CHEBI_URL = "https://www.ebi.ac.uk/chebi/backend/api/public/compound/CHEBI:{id}/"
EXPASY_URL = "https://web.expasy.org/protscale/pscale/Hphob.Doolittle.html"
NCBI_GC_URL = "https://ftp.ncbi.nih.gov/entrez/misc/data/gc.prt"


def get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=120, context=CONTEXT) as r:
                return r.read()
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 + 3 * attempt)
    raise AssertionError("unreachable")


def main() -> None:
    curated = tomllib.loads(CURATED.read_text(encoding="utf-8"))["amino_acid"]
    today = date.today().isoformat()
    retrieved: dict[str, str] = {}

    (OUT / "ccd").mkdir(parents=True, exist_ok=True)
    for aa in curated:
        (OUT / "ccd" / f"{aa['ccd']}.cif").write_bytes(get(CCD_URL.format(id=aa["ccd"])))
        print("ccd", aa["ccd"])
    retrieved["ccd"] = today

    cids = ",".join(str(aa["pubchem_cid"]) for aa in curated)
    pubchem = json.loads(get(PUBCHEM_URL.format(cids=cids)))
    (OUT / "pubchem.json").write_text(json.dumps(pubchem, indent=1), encoding="utf-8")
    retrieved["pubchem"] = today
    print("pubchem", len(pubchem["PropertyTable"]["Properties"]))

    chebi = {}
    for aa in curated:
        entry = json.loads(get(CHEBI_URL.format(id=aa["chebi"])))
        chebi[str(aa["chebi"])] = {
            "accession": entry["chebi_accession"],
            "name": entry["ascii_name"],
            "stars": entry["stars"],
            "smiles": (entry.get("default_structure") or {}).get("smiles"),
            "inchikey": (entry.get("default_structure") or {}).get("standard_inchi_key"),
            "chemical_data": entry.get("chemical_data"),
        }
        print("chebi", aa["chebi"], entry["ascii_name"])
    (OUT / "chebi.json").write_text(json.dumps(chebi, indent=1), encoding="utf-8")
    retrieved["chebi"] = today

    page = get(EXPASY_URL).decode("latin-1")
    text = re.sub(r"<[^>]+>", "", page)
    lines = [ln.strip() for ln in text.splitlines() if re.match(r"\s*[A-Z][a-z]{2}:\s*-?\d", ln)]
    head = [
        ln.strip() for ln in text.splitlines() if ln.strip().startswith(("Author", "Reference"))
    ]
    (OUT / "expasy_kd.txt").write_text("\n".join([EXPASY_URL, *head, *lines]) + "\n")
    retrieved["expasy_kd"] = today
    print("expasy", len(lines), "values")

    (OUT / "ncbi_gc.prt").write_bytes(get(NCBI_GC_URL))
    retrieved["ncbi_gc"] = today
    print("ncbi gc")

    (OUT / "retrieved.json").write_text(json.dumps(retrieved, indent=1) + "\n")


if __name__ == "__main__":
    main()
