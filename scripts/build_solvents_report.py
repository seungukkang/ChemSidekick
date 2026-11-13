"""Write data/verification/solvents.md: how the solvent viscosities were checked.

    uv run python scripts/build_solvents_report.py          # write the report
    uv run python scripts/build_solvents_report.py --check  # exit 1 if it is out of date

A solvent is "verified" when at least three references agree with the adopted
viscosity within the relative tolerance in src/chemsidekick/core/data/solvents.toml.
"""

import argparse
import sys
from pathlib import Path

from chemsidekick.core.solvents import Solvent, load

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "data/verification/solvents.md"
MIN_AGREEING = 3


def status(s: Solvent) -> str:
    return "verified" if load().agreeing(s) >= MIN_AGREEING else "unverified"


def report() -> str:
    data = load()
    lines = [
        "# Solvent viscosity verification report",
        "",
        "Built by `scripts/build_solvents_report.py` from "
        "`src/chemsidekick/core/data/solvents.toml`. Do not edit by hand.",
        "",
        f"Viscosities at {data.temperature:g} K (25 °C), 1 atm, in mPa s. A solvent is "
        f"**verified** when at least {MIN_AGREEING} references agree with the adopted value "
        f"within {data.tolerance:.0%}. Used for diffusion-limited rate constants "
        "(energy profile, ENE-01).",
        "",
        "| Solvent | Adopted (mPa s) | From | Agreeing | Status |",
        "|---|---|---|---|---|",
    ]
    for s in data.solvents.values():
        lines.append(
            f"| {s.name} | {s.viscosity:g} | {s.source} | {data.agreeing(s)} of {len(s.checks)} "
            f"| {status(s)} |"
        )
    lines += ["", "## Values found in each reference", ""]
    for s in data.solvents.values():
        lines += [f"**{s.name}**", "", "| Reference | mPa s | Agrees |", "|---|---|---|"]
        for ref, v in s.checks:
            ok = abs(v - s.viscosity) <= data.tolerance * s.viscosity
            lines.append(f"| {ref} | {v:g} | {'yes' if ok else 'no'} |")
        lines.append("")
    lines += [
        "## Not listed",
        "",
        "Fewer than three references with a 25 °C value were found on 2026-11-13: "
        "acetonitrile, DMSO, THF, dichloromethane, acetone (CRC only); ethanol and DMF "
        "(HSDB and CRC only). Type their viscosity instead.",
        "",
        "## References",
        "",
    ]
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
