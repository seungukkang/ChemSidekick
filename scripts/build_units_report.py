"""Write data/verification/units.md: how the constants behind the units were checked.

    uv run python scripts/build_units_report.py          # write the report
    uv run python scripts/build_units_report.py --check  # exit 1 if it is out of date

Measured constants in src/chemsidekick/core/data/units.toml list the value
found in each reference. A constant is "verified" when at least three
references agree with the adopted value within its standard uncertainty.
Defined constants are exact by definition and are listed with their source.
"""

import argparse
import sys
from pathlib import Path

from chemsidekick.core.units import ConstantDef, format_number, load

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data/verification/units.md"
MIN_AGREEING = 3


def agrees(c: ConstantDef, value: float) -> bool:
    assert c.uncertainty is not None
    return abs(value - c.value) <= c.uncertainty


def status(c: ConstantDef) -> str:
    if c.exact:
        return "definition"
    n = sum(agrees(c, v) for _, v in c.checks)
    return "verified" if n >= MIN_AGREEING else "unverified"


def report() -> str:
    data = load()
    measured = [c for c in data.constants.values() if not c.exact]
    defined = [c for c in data.constants.values() if c.exact]
    lines = [
        "# Unit constants verification report",
        "",
        "Built by `scripts/build_units_report.py` from `src/chemsidekick/core/data/units.toml`. "
        "Do not edit by hand.",
        "",
        f"A measured constant is **verified** when at least {MIN_AGREEING} references agree "
        "with the adopted value within its standard uncertainty. Conversions that use only "
        "defined constants are exact.",
        "",
        "## Measured constants",
        "",
        "| Constant | Adopted value | Standard uncertainty | Unit | Status |",
        "|---|---|---|---|---|",
    ]
    for c in measured:
        lines.append(
            f"| {c.name} (`{c.key}`) | {c.value!r} | {format_number(c.uncertainty or 0, 2)} "
            f"| {c.unit} | {status(c)} |"
        )
    lines += ["", "### Values found in each reference", ""]
    for c in measured:
        lines += [f"**{c.name}**", "", "| Reference | Value | Agrees |", "|---|---|---|"]
        for ref, value in c.checks:
            lines.append(f"| {ref} | {value!r} | {'yes' if agrees(c, value) else 'no'} |")
        lines.append("")
    lines += [
        "## Defined constants",
        "",
        "| Constant | Value | Unit | Source |",
        "|---|---|---|---|",
    ]
    for c in defined:
        lines.append(f"| {c.name} (`{c.key}`) | {c.value!r} | {c.unit} | {c.source} |")
    lines += ["", "## References", ""]
    for key, citation in data.references.items():
        lines.append(f"- `{key}`: {citation}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the report is out of date")
    args = parser.parse_args()
    text = report()
    if args.check:
        if not REPORT.exists() or REPORT.read_text(encoding="utf-8") != text:
            sys.exit(f"{REPORT.relative_to(ROOT)} is out of date: run {Path(__file__).name}")
        return
    REPORT.write_text(text, encoding="utf-8")
    print(f"wrote {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
