"""Download reference data and save it as normalized CSV files in data/sources/.

    uv run python scripts/fetch_sources.py              # all sources
    uv run python scripts/fetch_sources.py pubchem      # only the named sources

Each source is parsed into a small CSV with plain columns, so that
scripts/build_elements.py can compare the sources value by value.
Citations for every source are kept in data/sources/sources.toml.

Values are copied as published (as strings), including uncertainty notation
like "55.845(2)" or intervals like "[1.00784,1.00811]". Interpretation happens
in build_elements.py, not here.
"""

import csv
import html
import io
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import certifi

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sources"
USER_AGENT = "ChemSidekick-data-fetch/0.1 (personal research tool)"

URLS = {
    "ciaaw_weights": "https://www.ciaaw.org/atomic-weights.htm",
    "ciaaw_abundances": "https://www.ciaaw.org/isotopic-abundances.htm",
    # Earlier CIAAW tables (Internet Archive snapshots), the editions NIST SRD 144 v4.1
    # is based on. Used only as evidence that a compilation shows an older edition.
    "ciaaw_weights_2013": "https://web.archive.org/web/2014id_/http://www.ciaaw.org/atomic-weights.htm",
    "ciaaw_abundances_2009": (
        "https://web.archive.org/web/2014id_/http://www.ciaaw.org/isotopic-abundances.htm"
    ),
    "ame2020": "https://www-nds.iaea.org/amdc/ame2020/mass_1.mas20.txt",
    # AME2012 is the edition NIST SRD 144 v4.1 is based on (see its version history).
    "ame2012": "https://amdc.impcas.ac.cn/masstables/Ame2012/mass.mas12",
    "nubase2020": "https://www-nds.iaea.org/amdc/ame2020/nubase_4.mas20.txt",
    "nist_asd": (
        "https://physics.nist.gov/cgi-bin/ASD/ie.pl?spectra=H-Og+I&units=1&format=2"
        "&order=0&at_num_out=on&sp_name_out=on&ion_charge_out=on&el_name_out=on"
        "&shells_out=on&conf_out=on&level_out=on&e_out=0&biblio=on"
    ),
    "nist_srd144": (
        "https://physics.nist.gov/cgi-bin/Compositions/stand_alone.pl"
        "?ele=&all=all&ascii=ascii2&isotype=all"
    ),
    "iaea_livechart": "https://www-nds.iaea.org/relnsd/v1/data?fields=ground_states&nuclides=all",
    "pubchem": "https://pubchem.ncbi.nlm.nih.gov/rest/pug/periodictable/JSON",
    # Abridged standard atomic weights (one value per element, used for molecular weights).
    "ciaaw_abridged": "https://www.ciaaw.org/abridged-atomic-weights.htm",
    # The 2021 abridged table (Internet Archive), the edition the IUPAC Periodic Table
    # of 4 May 2022 shows. Used only as evidence that the IUPAC table shows an older edition.
    "ciaaw_abridged_2021": (
        "https://web.archive.org/web/2023id_/https://www.ciaaw.org/abridged-atomic-weights.htm"
    ),
    "iupac_periodic_table": (
        "https://iupac.org/wp-content/uploads/2022/07/IUPAC_Periodic_Table-04May22_CRA.pdf"
    ),
    # NIST SP 966, Periodic Table: Atomic Properties of the Elements (June 2024).
    "nist_periodic_table": (
        "https://www.nist.gov/system/files/documents/2024/06/25/NIST_periodictable_June24_iupac.pdf"
    ),
}

# Sources that are binary files (PDF); their parsers receive bytes.
BINARY = {"iupac_periodic_table", "nist_periodic_table"}


def get_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    # certifi: python.org builds of Python on macOS ship without root certificates.
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req, timeout=180, context=context) as resp:
        return resp.read()


def get(url: str) -> str:
    return get_bytes(url).decode("utf-8", errors="replace")


def clean(cell: str) -> str:
    """HTML cell -> text; non-breaking spaces (digit grouping) removed."""
    text = html.unescape(re.sub(r"<[^>]+>", "", cell))
    return text.replace("\xa0", "").replace(" ", "").strip()


def html_rows(page: str) -> list[list[str]]:
    page = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    rows = []
    # Split on </tr> rather than matching <tr>...</tr>: the CIAAW pages omit some
    # opening <tr> tags, which would otherwise merge two elements into one row.
    for row in page.split("</tr>"):
        rows.append([clean(c) for c in re.findall(r"<t[dh][^>]*>.*?</t[dh]>", row, flags=re.S)])
    return rows


def write_csv(name: str, header: list[str], rows: list[list[object]]) -> None:
    path = OUT / f"{name}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  {path.relative_to(ROOT)}: {len(rows)} rows")


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def ciaaw_weights(page: str, name: str = "ciaaw_weights") -> None:
    rows = []
    for cells in html_rows(page):
        if len(cells) >= 4 and cells[0].isdigit():
            rows.append([int(cells[0]), cells[1], cells[2], cells[3]])
    write_csv(name, ["z", "symbol", "name", "standard_atomic_weight"], rows)


def ciaaw_abundances(page: str, name: str = "ciaaw_abundances") -> None:
    rows = []
    z = symbol = None
    for cells in html_rows(page):
        if len(cells) >= 5 and cells[0].isdigit() and not cells[1].isdigit():
            z, symbol, a, comp = int(cells[0]), cells[1], cells[3], cells[4]
        elif len(cells) >= 2 and cells[0].isdigit() and z is not None:
            a, comp = cells[0], cells[1]
        else:
            continue
        # Radioactive elements are listed as "[97]" with composition "-": no natural abundance.
        if comp and comp != "-" and a.isdigit():
            rows.append([z, symbol, int(a), comp])
    write_csv(name, ["z", "symbol", "mass_number", "isotopic_composition"], rows)


def ame2020(text: str) -> None:
    """Fixed-width AME2020 mass table; atomic mass is given in micro-u."""
    rows = []
    for line in text.splitlines():
        if len(line) < 123 or not line[15:19].strip().isdigit():
            continue
        try:
            z, a = int(line[9:14]), int(line[14:19])
        except ValueError:
            continue
        symbol = line[20:23].strip()
        whole, frac = line[106:109].strip(), line[110:123].strip()
        unc = line[123:135].strip()
        if not whole.isdigit():
            continue
        estimated = "#" in frac
        micro = frac.replace("#", ".")
        # micro-u value like "007825.031898" -> mass = whole + micro*1e-6, as exact string
        int_part, _, dec_part = micro.partition(".")
        digits = int_part.zfill(6) + dec_part
        mass = f"{int(whole)}.{digits}"
        rows.append([z, symbol, a, mass, unc.replace("#", ""), int(estimated)])
    write_csv(
        "ame2020_masses",
        ["z", "symbol", "mass_number", "atomic_mass_u", "uncertainty_micro_u", "estimated"],
        rows,
    )


def ame2012(text: str) -> None:
    """An earlier AME edition, used only as evidence that a compilation is outdated.

    The pre-2020 format has one digit less than AME2020 in the mass columns.
    """
    rows = []
    for line in text.splitlines():
        if len(line) < 112 or not line[15:19].strip().isdigit():
            continue
        try:
            z, a = int(line[9:14]), int(line[14:19])
        except ValueError:
            continue
        whole, frac = line[96:99].strip(), line[100:112].strip()
        if not whole.isdigit() or "#" in frac:
            continue
        int_part, _, dec_part = frac.partition(".")
        rows.append([z, line[20:23].strip(), a, f"{int(whole)}.{int_part.zfill(6)}{dec_part}"])
    write_csv("ame2012_masses", ["z", "symbol", "mass_number", "atomic_mass_u"], rows)


def ciaaw_history(names: list[tuple[int, str, str]]) -> None:
    """Text of each element's CIAAW page, which describes past standard atomic weights.

    Used only as evidence that a compilation shows a former CIAAW value.
    """
    rows = []
    for z, symbol, name in names:
        try:
            page = get(f"https://www.ciaaw.org/{name}.htm")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            page = ""  # CIAAW has no page for this element
        page = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
        text = html.unescape(re.sub(r"<[^>]+>", " ", page))
        text = re.sub(r"\s+", " ", text.replace("\xa0", "")).strip()
        rows.append([z, symbol, text])
        time.sleep(0.5)  # be polite to the CIAAW server
    write_csv("ciaaw_history", ["z", "symbol", "page_text"], rows)


def nubase2020(text: str) -> None:
    """Ground states only: half-life and isotopic abundance (IS=...)."""
    rows = []
    for line in text.splitlines():
        if line.startswith("#") or len(line) < 80:
            continue
        a, zi = line[0:3].strip(), line[4:8].strip()
        if not (a.isdigit() and zi.isdigit()) or zi[-1] != "0":
            continue  # skip isomers and levels
        z = int(zi[:-1])
        symbol = re.sub(r"^\d+", "", line[11:16].strip())
        half_life = line[69:78].strip()
        unit = line[78:80].strip()
        unc = line[81:88].strip()
        m = re.search(r"IS=([\d.]+)(?:\s+([\d.]+))?", line[119:])
        abundance, abundance_unc = (m.group(1), m.group(2) or "") if m else ("", "")
        rows.append([z, symbol, int(a), half_life, unit, unc, abundance, abundance_unc])
    write_csv(
        "nubase2020",
        [
            "z",
            "symbol",
            "mass_number",
            "half_life",
            "unit",
            "half_life_unc",
            "abundance_percent",
            "abundance_unc",
        ],
        rows,
    )


def nist_asd(text: str) -> None:
    rows = []
    reader = csv.reader(text.splitlines())
    header = [h.strip() for h in next(reader)]
    idx = {h: i for i, h in enumerate(header)}
    for raw in reader:
        if not raw or len(raw) < len(header) - 1:
            continue
        cells = [c.strip().removeprefix('="').removesuffix('"') for c in raw]
        if cells[idx["Ion Charge"]] != "0":
            continue
        rows.append(
            [
                int(cells[idx["At. num"]]),
                cells[idx["Sp. Name"]].split()[0],
                cells[idx["Ground Shells (a)"]],
                cells[idx["Ground Level"]],
                cells[idx["References"]],
            ]
        )
    write_csv(
        "nist_asd_ground", ["z", "symbol", "ground_shells", "ground_level", "reference"], rows
    )


def nist_srd144(page: str) -> None:
    text = html.unescape(re.sub(r"<[^>]+>", "", page)).replace("\xa0", " ")
    rows = []
    for block in re.split(r"\n\s*\n", text):
        fields = dict(
            (k.strip(), v.strip())
            for k, _, v in (ln.partition("=") for ln in block.splitlines() if "=" in ln)
        )
        if "Atomic Number" not in fields or "Mass Number" not in fields:
            continue
        rows.append(
            [
                int(fields["Atomic Number"]),
                fields["Atomic Symbol"],
                int(fields["Mass Number"]),
                fields.get("Relative Atomic Mass", ""),
                fields.get("Isotopic Composition", ""),
                fields.get("Standard Atomic Weight", ""),
            ]
        )
    write_csv(
        "nist_srd144",
        [
            "z",
            "symbol",
            "mass_number",
            "relative_atomic_mass",
            "isotopic_composition",
            "standard_atomic_weight",
        ],
        rows,
    )


def iaea_livechart(text: str) -> None:
    reader = csv.DictReader(text.splitlines())
    rows = []
    for r in reader:
        if not r.get("z", "").isdigit() or int(r["z"]) == 0:
            continue
        z, n = int(r["z"]), int(r["n"])
        rows.append(
            [
                z,
                r["symbol"],
                z + n,
                r["atomic_mass"],
                r["unc_am"],
                r["abundance"],
                r["unc_a"],
                r["half_life"],
                r["unit_hl"],
                r["half_life_sec"],
            ]
        )
    write_csv(
        "iaea_livechart",
        [
            "z",
            "symbol",
            "mass_number",
            "atomic_mass_micro_u",
            "atomic_mass_unc",
            "abundance_percent",
            "abundance_unc",
            "half_life",
            "unit",
            "half_life_sec",
        ],
        rows,
    )


def pubchem(text: str) -> None:
    table = json.loads(text)["Table"]
    cols = table["Columns"]["Column"]
    rows = []
    for row in table["Row"]:
        r = dict(zip(cols, row["Cell"], strict=False))
        rows.append(
            [
                int(r["AtomicNumber"]),
                r["Symbol"],
                r["Name"],
                r["AtomicMass"],
                r["ElectronConfiguration"],
                r["Electronegativity"],
                r["OxidationStates"],
            ]
        )
    write_csv(
        "pubchem",
        [
            "z",
            "symbol",
            "name",
            "atomic_mass",
            "electron_configuration",
            "electronegativity",
            "oxidation_states",
        ],
        rows,
    )


def ciaaw_abridged(page: str, name: str = "ciaaw_abridged") -> None:
    """Abridged table: '1.0080 ± 0.0002' -> value 1.0080, uncertainty 0.0002; '—' for none."""
    rows = []
    for cells in html_rows(page):
        if len(cells) >= 4 and cells[0].isdigit():
            value, _, unc = cells[3].partition("±")
            rows.append([int(cells[0]), cells[1], value, unc])
    write_csv(name, ["z", "symbol", "abridged_atomic_weight", "uncertainty"], rows)


_PT_ENTRY = re.compile(
    r"^(\d{1,3})\n([A-Z][a-z]?)\n([a-z]+)\s*(?:([\d.]+)\s*±\s*([\d.]+)|\[(\d+)\])", re.M
)


def pdf_text(pdf: bytes) -> str:
    import logging

    from pypdf import PdfReader  # dev dependency, needed only here

    logging.getLogger("pypdf").setLevel(logging.ERROR)  # font-encoding notices only
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)


def iupac_periodic_table(pdf: bytes) -> None:
    """IUPAC Periodic Table PDF: each element is printed as Z, symbol, name, value, ± unc.

    Radioactive elements show a mass number in brackets (e.g. [97]) instead of a value.
    Some elements are printed twice in the PDF text; the first entry is kept.
    """
    text = pdf_text(pdf)
    seen: dict[int, list[object]] = {}
    for m in _PT_ENTRY.finditer(text):
        z = int(m.group(1))
        value, unc = (m.group(4), m.group(5)) if m.group(4) else ("—", "")
        seen.setdefault(z, [z, m.group(2), value, unc])
    write_csv(
        "iupac_periodic_table",
        ["z", "symbol", "abridged_atomic_weight", "uncertainty"],
        [seen[z] for z in sorted(seen)],
    )


# NIST prints each element as: symbol, name, atomic weight, first ionization energy (eV).
_NIST_PT_ENTRY = re.compile(r"\n([A-Z][a-z]+)\n\s*([\d.]+|\(\d+\))\n\s*(\d+\.\d+)\n")


def nist_periodic_table(pdf: bytes) -> None:
    """NIST periodic table PDF, matched by element name.

    The atomic numbers in the PDF text are not reliably next to their element
    (text order follows the drawing order), so entries are keyed by name. An entry
    is accepted only if the weight is followed by an ionization energy, which
    skips the few places where the text order is broken (they are reported missing).
    """
    names = {}
    with (OUT / "ciaaw_weights.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            names[r["name"].lower()] = (int(r["z"]), r["symbol"])
    names |= {"aluminum": names["aluminium"], "cesium": names["caesium"]}
    rows = {}
    for m in _NIST_PT_ENTRY.finditer(pdf_text(pdf)):
        hit = names.get(m.group(1).lower())
        if hit:
            weight = m.group(2)
            rows.setdefault(hit[0], [hit[0], hit[1], "—" if weight.startswith("(") else weight])
    write_csv(
        "nist_periodic_table",
        ["z", "symbol", "abridged_atomic_weight"],
        [rows[z] for z in sorted(rows)],
    )


PARSERS = {
    "ciaaw_weights": ciaaw_weights,
    "ciaaw_abundances": ciaaw_abundances,
    "ciaaw_weights_2013": lambda page: ciaaw_weights(page, "ciaaw_weights_2013"),
    "ciaaw_abundances_2009": lambda page: ciaaw_abundances(page, "ciaaw_abundances_2009"),
    "ame2020": ame2020,
    "ame2012": ame2012,
    "nubase2020": nubase2020,
    "nist_asd": nist_asd,
    "nist_srd144": nist_srd144,
    "iaea_livechart": iaea_livechart,
    "pubchem": pubchem,
    "ciaaw_abridged": ciaaw_abridged,
    "ciaaw_abridged_2021": lambda page: ciaaw_abridged(page, "ciaaw_abridged_2021"),
    "iupac_periodic_table": iupac_periodic_table,
    "nist_periodic_table": nist_periodic_table,
}


if __name__ == "__main__":
    # `fetch_sources.py name ...` refreshes only the named sources; no names = all.
    only = set(sys.argv[1:])
    unknown = only - set(URLS) - {"ciaaw_history"}
    if unknown:
        sys.exit(f"unknown source(s): {', '.join(sorted(unknown))}")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "retrieved.json"
    retrieved = json.loads(path.read_text()) if only and path.exists() else {}
    for name, url in URLS.items():
        if only and name not in only:
            continue
        print(f"{name}: {url}")
        PARSERS[name](get_bytes(url) if name in BINARY else get(url))
        retrieved[name] = date.today().isoformat()
    if only and "ciaaw_history" not in only:
        path.write_text(json.dumps(retrieved, indent=1) + "\n")
        sys.exit(0)
    # Per-element CIAAW pages (needs the element list from ciaaw_weights.csv).
    with (OUT / "ciaaw_weights.csv").open(encoding="utf-8") as f:
        names = [(int(r["z"]), r["symbol"], r["name"]) for r in csv.DictReader(f)]
    print(f"ciaaw_history: {len(names)} element pages")
    ciaaw_history(names)
    retrieved["ciaaw_history"] = date.today().isoformat()
    path.write_text(json.dumps(retrieved, indent=1) + "\n")
