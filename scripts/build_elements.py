"""Build src/chemsidekick/tools/reference/data/elements.json from mendeleev.

mendeleev takes ~10 s to import, which is far too slow for a quick lookup
tool, so we extract the values we need once and ship them as JSON.

Run after upgrading mendeleev:

    uv run python scripts/build_elements.py
"""

import json
import re
from datetime import date
from pathlib import Path

import mendeleev
from mendeleev import element

OUT = Path(__file__).resolve().parents[1] / "src/chemsidekick/tools/reference/data/elements.json"

NOBLE_GASES = {2: "He", 10: "Ne", 18: "Ar", 36: "Kr", 54: "Xe", 86: "Rn", 118: "Og"}

# IUPAC gives no standard atomic weight for elements without stable isotopes,
# except Th, Pa, U. For these, mendeleev's value is the mass of a long-lived isotope.
NO_STANDARD_WEIGHT = {43, 61, *range(84, 90), *range(93, 119)}

# Alternative English spellings accepted by the search.
ALIASES = {
    "Al": ["aluminium", "aluminum"],
    "S": ["sulfur", "sulphur"],
    "Cs": ["caesium", "cesium"],
}

_YEAR = 3.15576e7  # Julian year in seconds
# Every unit string that mendeleev uses for half-lives.
HALF_LIFE_SECONDS = {
    "ysec": 1e-24, "zsec": 1e-21, "asec": 1e-18, "psec": 1e-12, "nsec": 1e-9,
    "usec": 1e-6, "msec": 1e-3, "sec": 1.0, "minute": 60.0, "hour": 3600.0,
    "day": 86400.0, "year": _YEAR, "kyear": 1e3 * _YEAR, "Myear": 1e6 * _YEAR,
    "Gyear": 1e9 * _YEAR, "Tyear": 1e12 * _YEAR, "Pyear": 1e15 * _YEAR,
    "Eyear": 1e18 * _YEAR, "Zyear": 1e21 * _YEAR, "Yyear": 1e24 * _YEAR,
}  # fmt: skip

_ORBITAL_WITHOUT_COUNT = re.compile(r"\b(\d[spdfg])(?=\s|$)")


def normalize_config(conf: str) -> str:
    """'[Ar] 3d5 4s' -> '[Ar] 3d5 4s1' (mendeleev omits a count of 1)."""
    return _ORBITAL_WITHOUT_COUNT.sub(r"\g<1>1", conf.strip())


_L_ORDER = "spdfg"


def expand_config(conf: str, by_symbol: dict[str, str]) -> str:
    """'[Ar] 3d6 4s2' -> '1s2 2s2 2p6 3s2 3p6 3d6 4s2', sorted by (n, l).

    mendeleev's own full string mixes filling order and n order between
    elements, so we build it ourselves from the condensed form.
    """
    tokens: list[str] = []
    for tok in conf.split():
        if tok.startswith("["):
            tokens += expand_config(by_symbol[tok.strip("[]")], by_symbol).split()
        else:
            tokens.append(tok)
    tokens.sort(key=lambda t: (int(t[0]), _L_ORDER.index(t[1])))
    return " ".join(tokens)


def check_core(z: int, conf: str) -> None:
    """The condensed configuration must start from the preceding noble gas."""
    previous = [n for n in NOBLE_GASES if n < z]
    if not previous:  # H, He
        assert not conf.startswith("["), (z, conf)
        return
    expected = f"[{NOBLE_GASES[max(previous)]}]"
    assert conf.startswith(expected + " "), f"Z={z}: {conf!r} should start with {expected}"


def isotopes_of(el) -> tuple[list[dict], dict | None]:
    natural = sorted(
        (i for i in el.isotopes if i.abundance),
        key=lambda i: -i.abundance,
    )
    natural_rows = [
        {"mass_number": i.mass_number, "mass": i.mass, "abundance": i.abundance} for i in natural
    ]
    if natural_rows:
        return natural_rows, None

    # No natural abundance: report the longest-lived isotope instead.
    timed = []
    for i in el.isotopes:
        if i.half_life is None or i.half_life_unit is None:
            continue
        unit = i.half_life_unit
        if unit not in HALF_LIFE_SECONDS:
            raise ValueError(f"{el.symbol}-{i.mass_number}: unknown half-life unit {unit!r}")
        timed.append((i.half_life * HALF_LIFE_SECONDS[unit], i))
    if not timed:
        return [], None
    _, best = max(timed, key=lambda pair: pair[0])
    return [], {
        "mass_number": best.mass_number,
        "half_life": best.half_life,
        "half_life_unit": best.half_life_unit,
    }


def build() -> dict:
    elements = [element(z) for z in range(1, 119)]
    condensed_by_symbol = {el.symbol: normalize_config(el.econf) for el in elements}
    rows = []
    for el in elements:
        z = el.atomic_number
        condensed = condensed_by_symbol[el.symbol]
        check_core(z, condensed)
        natural, most_stable = isotopes_of(el)
        rows.append(
            {
                "z": z,
                "symbol": el.symbol,
                "name": el.name,
                "aliases": ALIASES.get(el.symbol, []),
                "atomic_weight": el.atomic_weight,
                "atomic_weight_uncertainty": el.atomic_weight_uncertainty,
                "standard_weight": z not in NO_STANDARD_WEIGHT,
                "group": el.group_id,
                "period": el.period,
                "block": el.block,
                "config": condensed,
                "config_full": expand_config(condensed, condensed_by_symbol),
                "en_pauling": el.en_pauling,
                "covalent_radius_pm": (
                    round(el.covalent_radius_pyykko, 1) if el.covalent_radius_pyykko else None
                ),
                "oxidation_states_main": el.oxidation_states("main"),
                "oxidation_states_other": el.oxidation_states("extended"),
                "radioactive": bool(el.is_radioactive),
                "isotopes": natural,
                "most_stable_isotope": most_stable,
            }
        )
    return {
        "meta": {
            "source": f"mendeleev {mendeleev.__version__}",
            "covalent_radius": "Pyykkö & Atsumi (2009), single-bond radii",
            "oxidation_states": "mendeleev 'main' and 'extended' categories",
            "generated": date.today().isoformat(),
        },
        "elements": rows,
    }


if __name__ == "__main__":
    data = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(data['elements'])} elements to {OUT}")
