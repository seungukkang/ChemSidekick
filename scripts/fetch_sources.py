"""Download reference data and save it as normalized CSV files in data/sources/.

    uv run python scripts/fetch_sources.py

Each source is parsed into a small CSV with plain columns, so that
scripts/build_elements.py can compare the sources value by value.
Citations for every source are kept in data/sources/sources.toml.

Values are copied as published (as strings), including uncertainty notation
like "55.845(2)" or intervals like "[1.00784,1.00811]". Interpretation happens
in build_elements.py, not here.
"""

import csv
import html
import json
import re
import ssl
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
    "ame2020": "https://www-nds.iaea.org/amdc/ame2020/mass_1.mas20.txt",
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
}


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    # certifi: python.org builds of Python on macOS ship without root certificates.
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req, timeout=180, context=context) as resp:
        return resp.read().decode("utf-8", errors="replace")


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


def ciaaw_weights(page: str) -> None:
    rows = []
    for cells in html_rows(page):
        if len(cells) >= 4 and cells[0].isdigit():
            rows.append([int(cells[0]), cells[1], cells[2], cells[3]])
    write_csv("ciaaw_weights", ["z", "symbol", "name", "standard_atomic_weight"], rows)


def ciaaw_abundances(page: str) -> None:
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
    write_csv("ciaaw_abundances", ["z", "symbol", "mass_number", "isotopic_composition"], rows)


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


PARSERS = {
    "ciaaw_weights": ciaaw_weights,
    "ciaaw_abundances": ciaaw_abundances,
    "ame2020": ame2020,
    "nubase2020": nubase2020,
    "nist_asd": nist_asd,
    "nist_srd144": nist_srd144,
    "iaea_livechart": iaea_livechart,
    "pubchem": pubchem,
}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    retrieved = {}
    for name, url in URLS.items():
        print(f"{name}: {url}")
        PARSERS[name](get(url))
        retrieved[name] = date.today().isoformat()
    (OUT / "retrieved.json").write_text(json.dumps(retrieved, indent=1) + "\n")
