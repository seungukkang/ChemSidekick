"""Units: parse quantities like "1 eV to kcal/mol" and convert between units.

The unit list lives in core/data/units.toml. Each unit has a factor to its
group's base unit, written as an expression over named constants, so whether
a conversion is exact follows from the constants it uses.

Energies and energy equivalents (cm⁻¹, nm, Hz, K) share the base unit J
(per particle): they convert into each other through E = hc·ν̃ = hc/λ = hν = k_B·T.
Wavelength units are inversely related to energy.

Also used by other tools for their unit inputs, e.g. `parse_temperature`.
"""

import ast
import difflib
import math
import operator
import re
import tomllib
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import Any

from chemsidekick.core.schemas import ToolError

# Groups whose units convert into each other (same base quantity).
_FAMILIES = {"energy": "energy", "equivalents": "energy"}


class UnitError(ToolError):
    """A unit or quantity the user typed cannot be read or converted."""


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConstantDef:
    key: str
    name: str
    value: float
    unit: str
    exact: bool
    source: str
    uncertainty: float | None
    checks: tuple[tuple[str, float], ...]  # (reference key, value)


@dataclass(frozen=True)
class Group:
    id: str
    title: str
    base: str
    headline: tuple[str, ...]
    example: str = ""

    @property
    def family(self) -> str:
        return _FAMILIES.get(self.id, self.id)


@dataclass(frozen=True)
class Unit:
    symbol: str
    group: str
    factor: float  # base units per 1 unit (wavelength: metres per 1 unit)
    factor_expr: str
    constants: tuple[str, ...]  # constant keys used by the factor
    exact: bool
    aliases: tuple[str, ...] = ()
    label: str = ""
    kind: str = "linear"  # "linear" or "wavelength"
    more: bool = False  # hidden unless typed or "show all"

    @property
    def display(self) -> str:
        return self.label or self.symbol


@dataclass(frozen=True)
class UnitData:
    constants: dict[str, ConstantDef]
    groups: dict[str, Group]  # in display order
    units: tuple[Unit, ...]
    references: dict[str, str]
    index: dict[str, tuple[Unit, ...]]  # normalized spelling -> units

    def in_group(self, group: str) -> list[Unit]:
        return [u for u in self.units if u.group == group]

    def unit(self, group: str, symbol: str) -> Unit:
        for u in self.units:
            if u.group == group and u.symbol == symbol:
                return u
        raise KeyError(f"no unit {symbol!r} in group {group!r}")


_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}


def evaluate(expr: str, names: dict[str, float]) -> tuple[float, set[str]]:
    """Evaluate a factor expression. Returns (value, names used).

    Only numbers, + - * / **, unary minus, parentheses, `pi`, and the given
    names are allowed (no function calls, no attribute access).
    """
    used: set[str] = set()

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.Name):
            if node.id == "pi":
                return math.pi
            if node.id in names:
                used.add(node.id)
                return names[node.id]
            raise ValueError(f"unknown name {node.id!r} in {expr!r}")
        raise ValueError(f"unsupported expression {expr!r}")

    return ev(ast.parse(expr, mode="eval")), used


_SUPER = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")
_UNIFY = str.maketrans(
    {
        "µ": "μ",  # micro sign -> Greek mu
        "Å": "Å",  # angstrom sign -> letter A with ring
        "−": "-",
        "–": "-",
        "·": "",
        "⋅": "",
        "*": "",
        "^": "",
        " ": "",
        "\t": "",
    }
)


def normalize(text: str) -> str:
    """Spelling used to look units up: superscripts become digits, and ^ · * and
    spaces are dropped, so "M^-1 s^-1", "M⁻¹s⁻¹" and "M-1 s-1" are the same."""
    return text.strip().translate(_SUPER).translate(_UNIFY)


def _data_text() -> str:
    return files("chemsidekick.core").joinpath("data/units.toml").read_text(encoding="utf-8")


@cache
def load() -> UnitData:
    raw = tomllib.loads(_data_text())
    constants: dict[str, ConstantDef] = {}
    values: dict[str, float] = {}
    for key, c in raw["constants"].items():
        value, _ = evaluate(c["value"], {})
        unc = evaluate(c["uncertainty"], {})[0] if "uncertainty" in c else None
        checks = tuple((ch["ref"], evaluate(ch["value"], {})[0]) for ch in c.get("checks", []))
        constants[key] = ConstantDef(
            key, c["name"], value, c["unit"], c["exact"], c["source"], unc, checks
        )
        values[key] = value
    groups = {
        g["id"]: Group(
            g["id"], g["title"], g["base"], tuple(g.get("headline", [])), g.get("example", "")
        )
        for g in raw["group"]
    }
    units: list[Unit] = []
    for u in raw["unit"]:
        factor, used = evaluate(u["factor"], values)
        kind = u.get("kind", "linear")
        if kind == "wavelength":
            used |= {"h", "c"}  # E = hc/λ
        units.append(
            Unit(
                symbol=u["symbol"],
                group=u["group"],
                factor=factor,
                factor_expr=u["factor"],
                constants=tuple(sorted(used)),
                exact=all(constants[k].exact for k in used),
                aliases=tuple(u.get("aliases", [])),
                label=u.get("label", ""),
                kind=kind,
                more=u.get("more", False),
            )
        )
    index: dict[str, list[Unit]] = {}
    for unit in units:
        # The label (e.g. "nm (wavelength)") is accepted too: it names one meaning.
        for spelling in {unit.symbol, *unit.aliases, *([unit.label] if unit.label else [])}:
            bucket = index.setdefault(normalize(spelling), [])
            if unit not in bucket:
                bucket.append(unit)
    return UnitData(
        constants=constants,
        groups=groups,
        units=tuple(units),
        references=dict(raw.get("references", {})),
        index={k: tuple(v) for k, v in index.items()},
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Lookup:
    units: tuple[Unit, ...]  # every unit with this spelling (e.g. nm: wavelength and length)
    typed: str
    corrected: str = ""  # set when matched only by ignoring upper/lower case


def find_unit(text: str) -> Lookup:
    """Every unit spelled `text`. Raises UnitError with suggestions if none."""
    data = load()
    key = normalize(text)
    if not key:
        raise UnitError("No unit given.")
    if key in data.index:
        return Lookup(data.index[key], text.strip())
    folded = [k for k in data.index if k.lower() == key.lower()]
    if len(folded) == 1:
        units = data.index[folded[0]]
        return Lookup(units, text.strip(), corrected=units[0].symbol)
    close = difflib.get_close_matches(key, list(data.index), n=4, cutoff=0.6)
    hint = ""
    if close:
        symbols = dict.fromkeys(data.index[c][0].symbol for c in close)
        hint = f" Did you mean: {', '.join(symbols)}?"
    groups = ", ".join(g.title.lower() for g in data.groups.values())
    raise UnitError(f"Unknown unit {text.strip()!r}.{hint} Supported: {groups}.")


_NUMBER = re.compile(
    r"""^\s*
    (?P<num>[-+]?(?:\d+(?:\.\d*)?|\.\d+))
    (?:\s*[eE]\s*(?P<exp>[-+]?\d+)
      |\s*[×xX*]\s*10\s*(?:\^|\*\*)?\s*(?P<exp10>[-+]?\d+))?
    """,
    re.VERBOSE,
)


def parse_number(text: str) -> tuple[float | None, str]:
    """Read a leading number ("1.2e-3", "1.2×10⁻³", "1.2*10^-3", "−5").
    Returns (value or None, the rest of the text)."""
    t = text.strip().translate(_SUPER).replace("−", "-")
    m = _NUMBER.match(t)
    if not m:
        return None, t
    exp = m.group("exp") or m.group("exp10") or "0"
    value = float(m.group("num")) * 10.0 ** int(exp)
    if not math.isfinite(value):
        raise UnitError(f"Number out of range: {text.strip()!r}.")
    return value, t[m.end() :].strip()


_SPLIT = re.compile(r"\s+(?:to|in|into)\s+|\s*(?:->|→|=>)\s*", re.IGNORECASE)


@dataclass(frozen=True)
class Query:
    value: float
    source: Lookup
    target: Lookup | None


def parse_query(text: str) -> Query:
    """ "1 eV to kcal/mol", "300 nm", "kcal/mol" (value 1) -> Query."""
    parts = _SPLIT.split(text.strip(), maxsplit=1)
    left = parts[0]
    value, unit_text = parse_number(left)
    if value is None:
        value = 1.0
    if not unit_text:
        raise UnitError(f"No unit after the number in {text.strip()!r}. Example: 1 eV to kcal/mol")
    target = find_unit(parts[1]) if len(parts) > 1 and parts[1].strip() else None
    return Query(value, find_unit(unit_text), target)


# ---------------------------------------------------------------------------
# Converting
# ---------------------------------------------------------------------------


def family(unit: Unit) -> str:
    return load().groups[unit.group].family


def to_base(value: float, unit: Unit) -> float:
    if unit.kind == "wavelength":
        if value <= 0:
            raise UnitError(f"A wavelength must be positive, got {value:g} {unit.symbol}.")
        c = load().constants
        return c["h"].value * c["c"].value / (value * unit.factor)
    return value * unit.factor


def from_base(base: float, unit: Unit) -> float:
    if unit.kind == "wavelength":
        if base <= 0:
            raise UnitError(f"Only a positive energy has a wavelength (got {base:g} J).")
        c = load().constants
        return c["h"].value * c["c"].value / (base * unit.factor)
    return base / unit.factor


def convert(value: float, source: Unit, target: Unit) -> float:
    if family(source) != family(target):
        g = load().groups
        raise UnitError(
            f"Cannot convert {source.symbol} ({g[source.group].title.lower()}) "
            f"to {target.symbol} ({g[target.group].title.lower()})."
        )
    return from_base(to_base(value, source), target)


def pair(source: Lookup, target: Lookup) -> tuple[Unit, Unit]:
    """Choose the meaning of both spellings that makes the conversion possible
    (e.g. nm -> eV is a wavelength, nm -> Å is a length)."""
    pairs = [(s, t) for s in source.units for t in target.units if family(s) == family(t)]
    if not pairs:
        convert(1.0, source.units[0], target.units[0])  # raises a clear error
    same_group = [p for p in pairs if p[0].group == p[1].group]
    return (same_group or pairs)[0]


# ---------------------------------------------------------------------------
# Temperature (for other tools' inputs; not a conversion group)
# ---------------------------------------------------------------------------

_TEMPERATURE_UNITS = {
    "": ("K", 1.0, 0.0),
    "k": ("K", 1.0, 0.0),
    "kelvin": ("K", 1.0, 0.0),
    "c": ("°C", 1.0, 273.15),
    "°c": ("°C", 1.0, 273.15),
    "degc": ("°C", 1.0, 273.15),
    "celsius": ("°C", 1.0, 273.15),
    "f": ("°F", 5 / 9, 273.15 - 32 * 5 / 9),
    "°f": ("°F", 5 / 9, 273.15 - 32 * 5 / 9),
    "degf": ("°F", 5 / 9, 273.15 - 32 * 5 / 9),
    "fahrenheit": ("°F", 5 / 9, 273.15 - 32 * 5 / 9),
}


def parse_temperature(text: str | float) -> float:
    """A temperature in K. A bare number is K; "25 C", "25 °C", "77 F" are converted."""
    if isinstance(text, (int, float)):
        kelvin = float(text)
        typed = f"{text:g}"
    else:
        value, rest = parse_number(text)
        unit = rest.strip().lower().replace(" ", "").replace("º", "°")
        if value is None or unit not in _TEMPERATURE_UNITS:
            raise UnitError(
                f"Cannot read the temperature {text.strip()!r}. Examples: 298.15, 25 C, -78 °C."
            )
        _, scale, offset = _TEMPERATURE_UNITS[unit]
        kelvin = value * scale + offset
        typed = text.strip()
    if not math.isfinite(kelvin) or kelvin <= 0:
        raise UnitError(f"Temperature must be above absolute zero (0 K), got {typed}.")
    return kelvin


_DURATION_UNITS = {
    "fs": 1e-15,
    "ps": 1e-12,
    "ns": 1e-9,
    "μs": 1e-6,
    "us": 1e-6,
    "µs": 1e-6,
    "ms": 1e-3,
    "s": 1.0,
    "sec": 1.0,
    "second": 1.0,
    "seconds": 1.0,
    "min": 60.0,
    "minute": 60.0,
    "minutes": 60.0,
    "h": 3600.0,
    "hr": 3600.0,
    "hour": 3600.0,
    "hours": 3600.0,
    "d": 86400.0,
    "day": 86400.0,
    "days": 86400.0,
    "wk": 604800.0,
    "week": 604800.0,
    "weeks": 604800.0,
    "yr": 31557600.0,  # Julian year, 365.25 d
    "year": 31557600.0,
    "years": 31557600.0,
}


def parse_duration(text: str | float) -> float:
    """A duration in s. A bare number is s; "1 h", "30 min", "2 d" are converted."""
    if isinstance(text, (int, float)):
        seconds = float(text)
    else:
        value, rest = parse_number(text)
        unit = rest.strip()
        factor = _DURATION_UNITS.get(unit, _DURATION_UNITS.get(unit.lower()))
        if value is None or (unit and factor is None):
            raise UnitError(f"Cannot read the time {text.strip()!r}. Examples: 30 s, 5 min, 2 h.")
        seconds = value * (factor or 1.0)
    if not math.isfinite(seconds) or seconds <= 0:
        raise UnitError(f"A time must be positive, got {text}.")
    return seconds


def format_duration(seconds: float) -> str:
    """Readable duration: '189 ps', '51 s', '28.4 min', '3.2 h', '4.6 d', '2.1 yr'."""
    for limit, unit, size in [
        (1e-12, "fs", 1e-15),
        (1e-9, "ps", 1e-12),
        (1e-6, "ns", 1e-9),
        (1e-3, "μs", 1e-6),
        (1, "ms", 1e-3),
        (120, "s", 1.0),
        (7200, "min", 60.0),
        (172800, "h", 3600.0),
        (3 * 31557600, "d", 86400.0),
    ]:
        if seconds < limit:
            return f"{format_number(seconds / size, 3)} {unit}"
    return f"{format_number(seconds / 31557600, 3)} yr"


ENERGY_UNITS = ("kcal/mol", "kJ/mol", "eV", "Eh")


def molar_energy(value: float, unit_text: str) -> float:
    """A value in an energy unit (kcal/mol, kJ/mol, eV, Eh, …) -> J/mol."""
    units = [u for u in find_unit(unit_text).units if u.group == "energy"]
    if not units:
        raise UnitError(
            f"{unit_text!r} is not an energy unit. Use one of: {', '.join(ENERGY_UNITS)}."
        )
    return value * units[0].factor * load().constants["NA"].value


def from_molar_energy(joule_per_mol: float, unit_text: str) -> float:
    """J/mol -> the given energy unit (inverse of molar_energy)."""
    return joule_per_mol / molar_energy(1.0, unit_text)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

_SUPERSCRIPT = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")


def _trim(text: str) -> str:
    """'760.000' -> '760', '1.50' -> '1.5' (trailing zeros after the point only)."""
    return text.rstrip("0").rstrip(".") if "." in text else text


def format_number(x: float, digits: int = 6) -> str:
    """Up to 6 significant figures, trailing zeros dropped; scientific notation
    below 10⁻³ or from 10⁶ (e.g. '4.35974 × 10⁻¹⁸')."""
    if x == 0:
        return "0"
    if not math.isfinite(x):
        return str(x)
    if 1e-3 <= abs(x) < 1e6:
        decimals = max(digits - 1 - math.floor(math.log10(abs(x))), 0)
        text = f"{x:.{decimals}f}"
        # 999999.7 rounds to 1000000.0: fall through to scientific notation
        if abs(float(text)) < 1e6:
            return _trim(text)
    mantissa, exp = f"{x:.{digits - 1}e}".split("e")
    return f"{_trim(mantissa)} × 10{str(int(exp)).translate(_SUPERSCRIPT)}"


_RELATION = {
    "cm⁻¹": "E = hc·ν̃",
    "K": "E = k_B·T",
}


def definition(unit: Unit) -> str:
    """How one unit relates to its group's base unit, e.g.
    '1 kcal/mol = 6.947695457 × 10⁻²¹ J' or 'E = hc / λ (inverse)'."""
    base = load().groups[unit.group].base
    if unit.kind == "wavelength":
        return "E = hc / λ (inversely proportional)"
    sign = "=" if unit.exact else "≈"
    text = f"1 {unit.symbol} {sign} {format_number(unit.factor, 10)} {base}"
    if unit.group == "equivalents":
        text += f" ({_RELATION.get(unit.symbol, 'E = h·ν')})"
    return text


def describe(unit: Unit) -> dict[str, Any]:
    """Machine-readable description of a unit (for JSON output)."""
    return {
        "symbol": unit.symbol,
        "label": unit.display,
        "group": unit.group,
        "group_title": load().groups[unit.group].title,
        "exact": unit.exact,
        "kind": unit.kind,
        "definition": definition(unit),
        "constants": list(unit.constants),
    }


def describe_constant(key: str) -> dict[str, Any]:
    c = load().constants[key]
    return {
        "symbol": key,
        "name": c.name,
        "value": c.value,
        "text": format_number(c.value, 11),
        "unit": c.unit,
        "exact": c.exact,
        "source": c.source,
    }
