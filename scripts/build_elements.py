"""Build the element data by cross-checking reference sources.

    uv run python scripts/fetch_sources.py   # 1. download sources (data/sources/*.csv)
    uv run python scripts/build_elements.py  # 2. compare and build

Output:
    src/chemsidekick/tools/reference/data/elements.json   used by the `element` tool
    data/verification/elements.md                        what was verified, and what not

Verification rule (project policy):
    verified    one primary source and at least two authoritative secondary
                compilations give the same value (see data/sources/sources.toml)
    partial     the primary source and one compilation agree, and the other
                compilation is shown, with data, to reproduce an older edition
                (e.g. NIST SRD 144 v4.1 = AME2012 / CIAAW 2013 / CIAAW 2009).
                The primary value is shown.
    unverified  anything else: the mendeleev value is shown, with the original
                reference that mendeleev cites
    definition  atomic number, group, period, block (IUPAC periodic table), and
                "no standard atomic weight" (CIAAW)

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
# Two references agree and the third shows an older edition (with evidence).
PARTIAL = "partial"


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


def _flat(s: str) -> str:
    return s.replace(" ", "").replace("\xa0", "")


def decide(value, text, agree, older, fallback, problems, label):
    """Apply the verification rule to one value."""
    if len(agree) >= 3:
        return field(value, VERIFIED, agree, text=text)
    if len(agree) == 2 and older:
        out = field(value, PARTIAL, agree, text=text)
        out["older"] = older
        return out
    fb_value, fb_text = fallback()
    problems.append(f"{label}: agreed only by {agree}")
    return field(fb_value, UNVERIFIED, ["mendeleev"], text=fb_text, agree=agree)


PT_NAMES = {
    "iupac-periodic-table": "IUPAC periodic table (2022)",
    "nist-periodic-table": "NIST periodic table (2024)",
}


def abridged_field(z, symbol, abridged, abridged21, iupac_pt, nist_pt, pc, m, problems):
    """CIAAW abridged value (primary), checked against the IUPAC and NIST periodic
    tables and PubChem. Both periodic tables were printed before the 2024 revision,
    so where they differ from CIAAW 2024 they are compared with the 2021 table."""
    a = abridged[z]
    if a["abridged_atomic_weight"] in ("—", "-", ""):
        return field(
            None,
            DEFINITION,
            ["ciaaw-abridged"],
            text="none",
            note="no stable isotopes; CIAAW gives no abridged atomic weight",
        )
    text = f"{a['abridged_atomic_weight']} ± {a['uncertainty']}"
    value = number(a["abridged_atomic_weight"])
    shown = {
        "iupac-periodic-table": (iupac_pt.get(z) or {}).get("abridged_atomic_weight", ""),
        "nist-periodic-table": (nist_pt.get(z) or {}).get("abridged_atomic_weight", ""),
        "pubchem": pc["atomic_mass"],
    }
    agree = ["ciaaw-abridged"] + [
        k for k, v in shown.items() if (n := number(v)) and consistent(value, n)
    ]
    older = None
    old = abridged21[z]["abridged_atomic_weight"]
    for k in ("iupac-periodic-table", "nist-periodic-table"):
        if k not in agree and shown[k] and _flat(shown[k]) == _flat(old):
            older = {
                "source": k,
                "edition": "ciaaw-abridged-2021",
                "evidence": f"{PT_NAMES[k]} shows {shown[k]}, "
                "identical to the CIAAW 2021 abridged table",
            }
    out = decide(
        float(value[0]),
        text,
        agree,
        older,
        lambda: (m.atomic_weight, f"{m.atomic_weight}"),
        problems,
        f"{symbol} abridged atomic weight (CIAAW {text}, shown elsewhere {shown})",
    )
    if out["status"] != UNVERIFIED:
        out["uncertainty"] = float(a["uncertainty"])
    return out


def _mendeleev_isotope(m, a):
    return next((i for i in m.isotopes if i.mass_number == a), None)


def build():
    ciaaw_w = by_z(read("ciaaw_weights"))
    # Older editions, used only as evidence that NIST SRD 144 reproduces them.
    ciaaw_w13 = by_z(read("ciaaw_weights_2013"))
    ciaaw_a09 = by_za(read("ciaaw_abundances_2009"))
    ame12 = by_za(read("ame2012_masses"))
    history = {int(r["z"]): _flat(r["page_text"]) for r in read("ciaaw_history")}
    nubase = by_za(read("nubase2020"))
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
    abridged = by_z(read("ciaaw_abridged"))
    abridged21 = by_z(read("ciaaw_abridged_2021"))
    iupac_pt = by_z(read("iupac_periodic_table"))
    nist_pt = by_z(read("nist_periodic_table"))

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
        else:
            if iv := interval(w_c):
                low, high, _ = iv
                text, value = f"[{low}, {high}]", None
                nist_ok = interval(w_n) == iv
                pub_ok = bool((p := number(w_p)) and in_interval(p, low, high))
            else:
                c = number(w_c)
                text, value = w_c, float(c[0])
                nist_ok = bool((n := number(w_n)) and consistent(c, n))
                pub_ok = bool((p := number(w_p)) and consistent(c, p))
            agree = ["ciaaw-weights"] + ["nist-srd144"] * nist_ok + ["pubchem"] * pub_ok
            older = None
            if not nist_ok and _flat(w_n) == _flat(ciaaw_w13[z]["standard_atomic_weight"]):
                older = {
                    "source": "nist-srd144",
                    "edition": "ciaaw-weights-2013",
                    "evidence": f"NIST SRD 144 shows {w_n}, identical to the CIAAW 2013 table",
                }
            elif not nist_ok and w_n and _flat(w_n) in history[z]:
                older = {
                    "source": "nist-srd144",
                    "edition": "ciaaw-history",
                    "evidence": f"NIST SRD 144 shows {w_n}, "
                    f"a former value on CIAAW's page for {name}",
                }
            weight = decide(
                value,
                text,
                agree,
                older,
                lambda m=m: (m.atomic_weight, f"{m.atomic_weight}"),
                problems,
                f"{symbol} atomic weight (CIAAW {w_c}, NIST {w_n}, PubChem {w_p})",
            )
            if iv:
                weight["note"] = "interval: the value depends on the source of the material"

        # -- abridged standard atomic weight (one value; for molecular weights)
        abridged_weight = abridged_field(
            z, symbol, abridged, abridged21, iupac_pt, nist_pt, pc, m, problems
        )

        # -- natural isotopes -------------------------------------------------
        isotopes = []
        for row in ciaaw_a.get(z, []):
            a = int(row["mass_number"])
            comp = row["isotopic_composition"]
            s_row, l_row, n_row = srd.get((z, a)), live.get((z, a)), nubase.get((z, a))
            mi = _mendeleev_isotope(m, a)

            # abundance in percent; compilations: NIST SRD 144, IAEA LiveChart, NUBASE2020
            s_raw = s_row["isotopic_composition"] if s_row else ""
            s_val = scaled(number(s_raw), 2) if number(s_raw) else None
            l_val = number(l_row["abundance_percent"]) if l_row else None
            n_val = number(n_row["abundance_percent"]) if n_row else None
            if iv := interval(comp):
                low, high = iv[0] * 100, iv[1] * 100
                text = f"[{low.normalize():f}, {high.normalize():f}]"
                value = None

                def ok(v, low=low, high=high):
                    return bool(v and in_interval(v, low, high))
            else:
                c = scaled(number(comp), 2)
                text, value = f"{c[0]:.{c[1]}f}", float(c[0])

                def ok(v, c=c):
                    return bool(v and consistent(c, v))

            nist_ok = ok(s_val)
            agree = (
                ["ciaaw-abundances"]
                + ["nist-srd144"] * nist_ok
                + ["iaea-livechart"] * ok(l_val)
                + ["nubase2020"] * ok(n_val)
            )
            older = None
            old = ciaaw_a09.get((z, a))
            if not nist_ok and old and s_raw and _flat(s_raw) == _flat(old["isotopic_composition"]):
                older = {
                    "source": "nist-srd144",
                    "edition": "ciaaw-abundances-2009",
                    "evidence": f"NIST SRD 144 shows {s_raw}, identical to the CIAAW 2009 table",
                }
            abundance = decide(
                value,
                text,
                agree,
                older,
                lambda mi=mi: (
                    mi.abundance if mi else None,
                    f"{mi.abundance:g}" if mi and mi.abundance else "—",
                ),
                problems,
                f"{symbol}-{a} abundance (CIAAW {comp}, NIST {s_raw or '—'})",
            )

            # mass in u, compared at the displayed precision (6 decimals)
            ref = Decimal(ame[(z, a)]["atomic_mass_u"]) if (z, a) in ame else None
            agree, older = [], None
            if ref is not None:
                n = number(s_row["relative_atomic_mass"]) if s_row else None
                nist_ok = bool(n and same_at(6, n[0], ref))
                live_ok = bool(
                    l_row
                    and l_row["atomic_mass_micro_u"]
                    and same_at(6, Decimal(l_row["atomic_mass_micro_u"]).scaleb(-6), ref)
                )
                agree = ["ame2020"] + ["nist-srd144"] * nist_ok + ["iaea-livechart"] * live_ok
                old = ame12.get((z, a))
                if not nist_ok and n and old and consistent(n, number(old["atomic_mass_u"])):
                    older = {
                        "source": "nist-srd144",
                        "edition": "ame2012",
                        "evidence": f"NIST SRD 144 shows {s_row['relative_atomic_mass']}, "
                        f"equal to AME2012 ({old['atomic_mass_u']})",
                    }
            mass = decide(
                float(ref) if ref is not None else None,
                f"{ref:.6f}" if ref is not None else "—",
                agree,
                older,
                lambda mi=mi: (mi.mass if mi else None, f"{mi.mass:.6f}" if mi else "—"),
                problems,
                f"{symbol}-{a} mass",
            )
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
                "abridged_weight": abridged_weight,
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
        ("Abridged atomic weight", count(lambda e: [e["abridged_weight"]])),
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
        "| Property | verified | partial | definition | unverified |",
        "|---|---|---|---|---|",
    ]
    for name, c in rows:
        lines.append(
            f"| {name} | {c[VERIFIED]} | {c[PARTIAL]} | {c[DEFINITION]} | {c[UNVERIFIED]} |"
        )
    lines += [
        "",
        f"Electron configurations where both NIST ASD and PubChem agree with the shown value: "
        f"{both} of {len(els)}.",
        "",
        "## Partial: the third reference shows an older edition",
        "",
    ]
    for e in els:
        fields = [
            ("atomic weight", e["atomic_weight"]),
            ("abridged atomic weight", e["abridged_weight"]),
        ] + [
            (f"{e['symbol']}-{i['mass_number']} {kind}", i[kind])
            for i in e["isotopes"]
            for kind in ("mass", "abundance")
        ]
        for label, f in fields:
            if f["status"] == PARTIAL:
                lines.append(f"- {e['symbol']} {label}: {f['older']['evidence']}")
    lines += ["", "## Unverified (shown from mendeleev) and other gaps", ""]
    lines += [f"- {p}" for p in problems] or ["- none"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    data, problems = build()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report(data, problems), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} and {REPORT.relative_to(ROOT)}")
    print(f"{len(problems)} disagreements or gaps (see report)")
