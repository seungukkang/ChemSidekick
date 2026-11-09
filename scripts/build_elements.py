"""Build the element data by cross-checking reference sources.

    uv run python scripts/fetch_sources.py   # 1. download sources (data/sources/*.csv)
    uv run python scripts/build_elements.py  # 2. compare and build

Output:
    src/chemsidekick/tools/reference/data/elements.json   used by the `element` tool
    data/verification/elements.md                        what was verified, and what not

Verification rule (project policy):
    A value is "verified" when one primary source and at least two authoritative
    secondary compilations give the same value (see data/sources/sources.toml).
    Otherwise the mendeleev value is used and marked "unverified", with the
    original reference that mendeleev cites. Atomic number, group, period, and
    block are definitions (IUPAC periodic table), marked "definition".

"Same value":
    numbers   the difference is at most half a unit in the last digit of the
              less precise value (i.e. one is a correct rounding of the other)
    intervals identical, or the other value lies inside the interval
    configs   identical after expanding the noble-gas core

mendeleev takes ~10 s to import, so the result is saved as JSON and the tool
never imports mendeleev at run time.
"""

import csv
import json
import re
import tomllib
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

import mendeleev
from mendeleev import element as mendeleev_element

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "data" / "sources"
OUT = ROOT / "src/chemsidekick/tools/reference/data/elements.json"
REPORT = ROOT / "data" / "verification" / "elements.md"

NOBLE = {2: "He", 10: "Ne", 18: "Ar", 36: "Kr", 54: "Xe", 86: "Rn", 118: "Og"}
ALIASES = {"Al": ["aluminum"], "Cs": ["cesium"], "S": ["sulphur"]}
L_ORDER = "spdfg"

VERIFIED, DEFINITION, UNVERIFIED = "verified", "definition", "unverified"


# ---------------------------------------------------------------------------
# Reading sources
# ---------------------------------------------------------------------------


def read(name: str) -> list[dict[str, str]]:
    with (SOURCES / f"{name}.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def by_z(rows):
    return {int(r["z"]): r for r in rows}


def by_za(rows):
    return {(int(r["z"]), int(r["mass_number"])): r for r in rows}


# ---------------------------------------------------------------------------
# Numbers with uncertainty and intervals
# ---------------------------------------------------------------------------

_UNC = re.compile(r"^([\d.]+)(?:\(\d+#?\))?#?$")
_INTERVAL = re.compile(r"^\[([\d.]+),([\d.]+)\]$")


def decimals(s: str) -> int:
    return len(s.split(".")[1]) if "." in s else 0


def number(s: str) -> tuple[Decimal, int] | None:
    """'55.845(2)' -> (Decimal('55.845'), 3). None if not a plain number."""
    m = _UNC.match(s.strip().replace(" ", ""))
    if not m:
        return None
    return Decimal(m.group(1)), decimals(m.group(1))


def interval(s: str) -> tuple[Decimal, Decimal, int] | None:
    m = _INTERVAL.match(s.strip().replace(" ", ""))
    if not m:
        return None
    return Decimal(m.group(1)), Decimal(m.group(2)), decimals(m.group(1))


def consistent(a: tuple[Decimal, int], b: tuple[Decimal, int]) -> bool:
    """One value is a correct rounding of the other."""
    places = min(a[1], b[1])
    return abs(a[0] - b[0]) <= Decimal(5) * Decimal(10) ** -(places + 1)


def same_at(places: int, a: Decimal, b: Decimal) -> bool:
    """Same value when both are shown with `places` decimals (or within half a unit)."""
    q = Decimal(10) ** -places
    return a.quantize(q) == b.quantize(q) or abs(a - b) <= q / 2


def in_interval(value: tuple[Decimal, int], low: Decimal, high: Decimal) -> bool:
    """Inside the interval, also after rounding the interval to the value's precision.

    IUPAC's "conventional" values (e.g. O = 15.999 for [15.99903, 15.99977]) are
    rounded and may sit just outside the unrounded interval.
    """
    if low <= value[0] <= high:
        return True
    q = Decimal(10) ** -value[1]
    return low.quantize(q) <= value[0] <= high.quantize(q)


def scaled(value: tuple[Decimal, int], power: int) -> tuple[Decimal, int]:
    """Multiply by 10**power, keeping track of decimal places."""
    return value[0].scaleb(power), max(0, value[1] - power)


# ---------------------------------------------------------------------------
# Electron configurations
# ---------------------------------------------------------------------------

_TOKEN = re.compile(r"\[([A-Z][a-z]?)\]|(\d)([spdfg])(\d*)")


def config_tokens(conf: str) -> list[str]:
    """Any notation ('[Ar].3d6.4s2', '[Ar]4s2 3d6', '[Ar] 3d6 4s') -> ['[Ar]', '3d6', '4s2']."""
    out = []
    for core, n, shell, count in _TOKEN.findall(conf):
        out.append(f"[{core}]" if core else f"{n}{shell}{count or 1}")
    return out


def expand(conf: str, cores: dict[str, str]) -> str:
    """Full configuration sorted by (n, l)."""
    tokens: list[str] = []
    for tok in config_tokens(conf):
        if tok.startswith("["):
            tokens += expand(cores[tok.strip("[]")], cores).split()
        else:
            tokens.append(tok)
    tokens.sort(key=lambda t: (int(t[0]), L_ORDER.index(t[1])))
    return " ".join(tokens)


def condensed(full: str, z: int, cores_full: dict[str, str]) -> str:
    """Full configuration -> '[Ar] 3d6 4s2' using the preceding noble gas."""
    previous = [n for n in NOBLE if n < z]
    if not previous:
        return full
    core = NOBLE[max(previous)]
    core_tokens = set(cores_full[core].split())
    rest = [t for t in full.split() if t not in core_tokens]
    return " ".join([f"[{core}]", *rest])


# ---------------------------------------------------------------------------
# Periodic-table position (definitions)
# ---------------------------------------------------------------------------

PERIOD_ENDS = [2, 10, 18, 36, 54, 86, 118]


def position(z: int) -> tuple[int | None, int, str]:
    """(group, period, block) in the 18-column layout with La/Ac in group 3."""
    period = next(i + 1 for i, end in enumerate(PERIOD_ENDS) if z <= end)
    start = ([0] + PERIOD_ENDS)[period - 1]
    i = z - start  # 1-based index within the period
    if period == 1:
        group = 1 if i == 1 else 18
    elif period in (2, 3):
        group = i if i <= 2 else i + 10
    elif period in (4, 5):
        group = i
    else:
        group = i if i <= 3 else (None if i <= 17 else i - 14)
    if group is None:
        block = "f"
    elif group in (1, 2) or z == 2:
        block = "s"
    elif group >= 13:
        block = "p"
    else:
        block = "d"
    return group, period, block


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


def field(value, status, refs, text=None, agree=None, note=""):
    out = {"value": value, "status": status, "refs": refs}
    if text is not None:
        out["text"] = text
    if agree:
        out["agree"] = agree
    if note:
        out["note"] = note
    return out


HALF_LIFE_UNITS_S = {
    "ysec": 1e-24, "zsec": 1e-21, "asec": 1e-18, "psec": 1e-12, "nsec": 1e-9, "usec": 1e-6,
    "msec": 1e-3, "sec": 1.0, "minute": 60.0, "hour": 3600.0, "day": 86400.0,
    "year": 3.15576e7, "kyear": 3.15576e10, "Myear": 3.15576e13, "Gyear": 3.15576e16,
    "Tyear": 3.15576e19, "Pyear": 3.15576e22, "Eyear": 3.15576e25, "Zyear": 3.15576e28,
    "Yyear": 3.15576e31,
}  # fmt: skip


def longest_lived(m):
    timed = [
        (i.half_life * HALF_LIFE_UNITS_S[i.half_life_unit], i)
        for i in m.isotopes
        if i.half_life and i.half_life_unit
    ]
    if not timed:
        return None
    _, best = max(timed, key=lambda t: t[0])
    return {"mass_number": best.mass_number, "half_life": best.half_life,
            "unit": best.half_life_unit}  # fmt: skip


def _mendeleev_isotope(m, a):
    return next((i for i in m.isotopes if i.mass_number == a), None)


def build():
    ciaaw_w = by_z(read("ciaaw_weights"))
    ciaaw_a = defaultdict(list)
    for r in read("ciaaw_abundances"):
        ciaaw_a[int(r["z"])].append(r)
    ame = by_za(read("ame2020_masses"))
    srd_rows = read("nist_srd144")
    srd = by_za(srd_rows)
    srd_first: dict[int, dict[str, str]] = {}
    for r in srd_rows:
        srd_first.setdefault(int(r["z"]), r)
    live = by_za(read("iaea_livechart"))
    asd = by_z(read("nist_asd_ground"))
    pub = by_z(read("pubchem"))

    mend = {z: mendeleev_element(z) for z in range(1, 119)}
    asd_cores = {r["symbol"]: r["ground_shells"] for r in asd.values()}
    mend_cores = {m.symbol: m.econf for m in mend.values()}
    mend_full = {m.symbol: expand(m.econf, mend_cores) for m in mend.values()}

    problems: list[str] = []
    elements = []

    for z in range(1, 119):
        m = mend[z]
        cw, pc, sf = ciaaw_w[z], pub[z], srd_first[z]
        symbol = cw["symbol"]

        # -- identity: symbol from three sources ----------------------------
        symbols = {cw["symbol"], sf["symbol"], pc["symbol"]}
        if len(symbols) != 1:
            problems.append(f"Z={z}: symbols differ {sorted(symbols)}")
        name = cw["name"].capitalize()  # IUPAC spelling (aluminium, caesium, sulfur)
        aliases = set(ALIASES.get(symbol, []))
        if pc["name"].lower() != cw["name"].lower():
            aliases.add(pc["name"].lower())

        # -- position: a definition -----------------------------------------
        group, period, block = position(z)
        if (group, period, block) != (m.group_id, m.period, m.block):
            problems.append(
                f"{symbol}: position {group}/{period}/{block} differs from mendeleev "
                f"{m.group_id}/{m.period}/{m.block} (layout convention)"
            )

        # -- standard atomic weight -----------------------------------------
        w_c, w_n, w_p = (
            cw["standard_atomic_weight"],
            sf["standard_atomic_weight"],
            pc["atomic_mass"],
        )
        if w_c in ("—", "-", ""):
            weight = field(
                None,
                DEFINITION,
                ["ciaaw-weights"],
                text="none",
                note="no stable isotopes; CIAAW gives no standard atomic weight",
            )
        elif iv := interval(w_c):
            low, high, _ = iv
            agree = ["ciaaw-weights"]
            if interval(w_n) == iv:
                agree.append("nist-srd144")
            if (p := number(w_p)) and in_interval(p, low, high):
                agree.append("pubchem")
            status = VERIFIED if len(agree) >= 3 else UNVERIFIED
            weight = field(
                None,
                status,
                agree,
                text=f"[{low}, {high}]",
                note="interval: the value depends on the source of the material",
            )
            if status != VERIFIED:
                problems.append(f"{symbol}: atomic weight interval agreed only by {agree}")
        else:
            c = number(w_c)
            agree = ["ciaaw-weights"]
            if (n := number(w_n)) and consistent(c, n):
                agree.append("nist-srd144")
            if (p := number(w_p)) and consistent(c, p):
                agree.append("pubchem")
            if len(agree) >= 3:
                weight = field(float(c[0]), VERIFIED, agree, text=w_c)
            else:
                weight = field(
                    m.atomic_weight,
                    UNVERIFIED,
                    ["mendeleev"],
                    text=f"{m.atomic_weight}",
                    agree=agree,
                )
                problems.append(f"{symbol}: atomic weight CIAAW {w_c}, NIST {w_n}, PubChem {w_p}")

        # -- natural isotopes -------------------------------------------------
        isotopes = []
        for row in ciaaw_a.get(z, []):
            a = int(row["mass_number"])
            comp = row["isotopic_composition"]
            s_row, l_row = srd.get((z, a)), live.get((z, a))

            # abundance in percent
            agree = ["ciaaw-abundances"]
            s_val = number(s_row["isotopic_composition"]) if s_row else None
            l_val = number(l_row["abundance_percent"]) if l_row else None
            if iv := interval(comp):
                low, high = iv[0] * 100, iv[1] * 100
                text = f"[{low.normalize():f}, {high.normalize():f}]"
                value = None
                if s_val and in_interval(scaled(s_val, 2), low, high):
                    agree.append("nist-srd144")
                if l_val and in_interval(l_val, low, high):
                    agree.append("iaea-livechart")
            else:
                c = scaled(number(comp), 2)
                text = f"{c[0]:.{c[1]}f}"
                value = float(c[0])
                if s_val and consistent(c, scaled(s_val, 2)):
                    agree.append("nist-srd144")
                if l_val and consistent(c, l_val):
                    agree.append("iaea-livechart")
            if len(agree) >= 3:
                abundance = field(value, VERIFIED, agree, text=text)
            else:
                mi = _mendeleev_isotope(m, a)
                ma = mi.abundance if mi else None
                abundance = field(
                    ma, UNVERIFIED, ["mendeleev"], text=f"{ma:g}" if ma else "—", agree=agree
                )
                problems.append(
                    f"{symbol}-{a}: abundance CIAAW {comp}, "
                    f"NIST {s_row['isotopic_composition'] if s_row else '—'}, "
                    f"LiveChart {l_row['abundance_percent'] if l_row else '—'} %"
                )

            # mass, compared at the displayed precision (6 decimals, in u)
            agree = []
            ref = Decimal(ame[(z, a)]["atomic_mass_u"]) if (z, a) in ame else None
            if ref is not None:
                agree.append("ame2020")
                if s_row and (n := number(s_row["relative_atomic_mass"])) and same_at(6, n[0], ref):
                    agree.append("nist-srd144")
                if l_row and l_row["atomic_mass_micro_u"]:
                    if same_at(6, Decimal(l_row["atomic_mass_micro_u"]).scaleb(-6), ref):
                        agree.append("iaea-livechart")
            if len(agree) >= 3:
                mass = field(float(ref), VERIFIED, agree, text=f"{ref:.6f}")
            else:
                mi = _mendeleev_isotope(m, a)
                mass = field(
                    mi.mass if mi else None,
                    UNVERIFIED,
                    ["mendeleev"],
                    text=f"{mi.mass:.6f}" if mi else "—",
                    agree=agree,
                )
                problems.append(f"{symbol}-{a}: mass agreed only by {agree}")
            isotopes.append({"mass_number": a, "abundance": abundance, "mass": mass})
        isotopes.sort(key=lambda i: -(i["abundance"]["value"] or 0))

        # -- longest-lived isotope (elements without natural isotopes) ------
        longest = None
        if not isotopes and (ll := longest_lived(m)):
            longest = field(
                ll,
                UNVERIFIED,
                ["nubase2020"],
                note="NUBASE2020 via mendeleev; no second compilation compared",
            )

        # -- electron configuration -------------------------------------------
        m_full = mend_full[symbol]
        agree = []
        if z in asd and expand(asd[z]["ground_shells"], asd_cores) == m_full:
            agree.append("nist-asd")
        pc_conf = pc["electron_configuration"]
        if pc_conf and expand(pc_conf, mend_cores) == m_full:
            agree.append("pubchem")
        # Only two sources exist (NIST ASD, PubChem), so this cannot be "verified".
        config = field(
            condensed(m_full, z, mend_full),
            UNVERIFIED,
            ["mendeleev"],
            agree=agree,
            note="only two sources available (NIST ASD, PubChem)",
        )
        config["full"] = m_full
        if z in asd and "nist-asd" not in agree:
            problems.append(
                f"{symbol}: configuration NIST ASD {asd[z]['ground_shells']} vs mendeleev {m.econf}"
            )
        if pc_conf and "pubchem" not in agree:
            problems.append(f"{symbol}: configuration PubChem {pc_conf} vs mendeleev {m.econf}")

        # -- properties with no primary source available: mendeleev only ----
        en_agree = []
        if m.en_pauling is not None and (p := number(pc["electronegativity"])):
            if consistent(p, (Decimal(str(m.en_pauling)), decimals(str(m.en_pauling)))):
                en_agree.append("pubchem")
        en = field(m.en_pauling, UNVERIFIED, ["crc2014"], agree=en_agree)
        radius = field(
            round(m.covalent_radius_pyykko, 1) if m.covalent_radius_pyykko else None,
            UNVERIFIED,
            ["pyykko2009"],
        )
        oxidation = field(
            {"main": m.oxidation_states("main"), "other": m.oxidation_states("extended")},
            UNVERIFIED,
            ["wikipedia-oxidation"],
        )

        elements.append(
            {
                "z": z,
                "symbol": symbol,
                "name": name,
                "aliases": sorted(aliases),
                "group": group,
                "period": period,
                "block": block,
                "identity_refs": ["ciaaw-weights", "nist-srd144", "pubchem"],
                "atomic_weight": weight,
                "isotopes": isotopes,
                "longest_lived_isotope": longest,
                "config": config,
                "en_pauling": en,
                "covalent_radius_pm": radius,
                "oxidation_states": oxidation,
            }
        )

    refs = tomllib.loads((SOURCES / "sources.toml").read_text(encoding="utf-8"))
    meta = {
        "built": date.today().isoformat(),
        "retrieved": json.loads((SOURCES / "retrieved.json").read_text()),
        "mendeleev": mendeleev.__version__,
        "references": {
            k: {"short": v["short"], "citation": v["citation"]} for k, v in refs.items()
        },
    }
    return {"meta": meta, "elements": elements}, problems


def report(data, problems) -> str:
    els = data["elements"]

    def count(get):
        c: dict[str, int] = defaultdict(int)
        for e in els:
            for f in get(e):
                c[f["status"]] += 1
        return c

    rows = [
        ("Standard atomic weight", count(lambda e: [e["atomic_weight"]])),
        ("Isotope abundance", count(lambda e: [i["abundance"] for i in e["isotopes"]])),
        ("Isotope mass", count(lambda e: [i["mass"] for i in e["isotopes"]])),
        ("Electron configuration", count(lambda e: [e["config"]])),
        ("Electronegativity (Pauling)", count(lambda e: [e["en_pauling"]])),
        ("Covalent radius", count(lambda e: [e["covalent_radius_pm"]])),
        ("Oxidation states", count(lambda e: [e["oxidation_states"]])),
    ]
    both = sum(1 for e in els if len(e["config"].get("agree", [])) == 2)
    lines = [
        "# Element data verification report",
        "",
        f"Built {data['meta']['built']} by `scripts/build_elements.py`. Do not edit by hand.",
        "",
        "| Property | verified | definition | unverified |",
        "|---|---|---|---|",
    ]
    for name, c in rows:
        lines.append(f"| {name} | {c[VERIFIED]} | {c[DEFINITION]} | {c[UNVERIFIED]} |")
    lines += [
        "",
        f"Electron configurations where both NIST ASD and PubChem agree with the shown value: "
        f"{both} of {len(els)}.",
        "",
        "## Disagreements and gaps",
        "",
    ]
    lines += [f"- {p}" for p in problems] or ["- none"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    data, problems = build()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report(data, problems), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} and {REPORT.relative_to(ROOT)}")
    print(f"{len(problems)} disagreements or gaps (see report)")
