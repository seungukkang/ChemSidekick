# ChemSidekick

A personal toolbox of small chemistry calculators and visualizers, used from the terminal (`csk`) or a local web interface.

> **Status:** v0.1.0 — three tools, CLI and Streamlit web interface. A launcher (Raycast) and AI assistant (MCP) interfaces are planned.

## Tools

| ID | Command | What it does |
|---|---|---|
| STR-01 | `csk xyz` | Paste XYZ coordinates (one or many frames): formula, molecular weight, closest atoms, and an interactive 3D view |
| STR-02 | `csk stereo` | All stereoisomers of a SMILES (or a simple condensed formula): R/S, r/s and E/Z with IUPAC locants, enantiomer/diastereomer/meso relations, 2D drawings and 3D structures |
| REF-01 | `csk element` | Element card (atomic weights, electron configuration, isotopes, …) or the periodic table |

Every chemical value in `element` is cross-checked against one primary source and two authoritative compilations, and each value shows whether it was confirmed (see [`data/verification/elements.md`](data/verification/elements.md)).

## Install

Requires macOS, [uv](https://docs.astral.sh/uv/), and Python 3.12 (uv installs it if needed).

```sh
git clone https://github.com/seungukkang/ChemSidekick.git
cd ChemSidekick
uv sync
```

Run commands with `uv run csk …`, or install the `csk` command once with `uv tool install .`.

## Use

```sh
csk element Fe                 # element card
csk element                    # periodic table
csk xyz molecule.xyz           # or paste coordinates: pbpaste | csk xyz
csk stereo "CC(O)C(O)C(O)C"    # stereoisomers; also accepts CH3-CH(OH)-CH3
csk ui                         # web interface in the browser
```

- `csk list` and `csk search <word>` find tools; `csk <tool> --help` shows its options.
- `--json` prints one JSON object (`{"ok": true, "result": …, "run": …}` or `{"ok": false, "error": …}`), also for errors, and exits with a code per error type. `csk list --json` describes every tool and its inputs.
- `csk run <tool> --json` takes the tool's input as JSON on standard input, for programs: `echo '{"smiles": "CC(Br)C(Br)C"}' | csk run stereo --json`. The format is versioned; its JSON Schemas are in [`schemas/`](schemas/).
- `--no-record` runs without keeping a recent result.
- `csk gif --json` turns one 3D structure (a frame from a result, as JSON on standard input) into a rotating GIF, for places without the interactive viewer.
- Every run is kept as a recent result (newest 50). `csk recent` lists them and `csk save <number>` keeps one in `~/Documents/ChemSidekick`.
- The 3D viewer loads [3Dmol.js](https://3dmol.csb.pitt.edu/) from a CDN, so it needs an internet connection.

## Architecture

```
Interfaces (CLI · Streamlit; later Raycast · MCP)
        │
   chemsidekick core (tool registry, runner with time/memory limits, result store)
        │
   tools (each declares its inputs once; CLI options and web forms are generated)
```

Adding a tool means adding one module under `src/chemsidekick/tools/`; no interface code changes.

## Development

```sh
uv run pytest          # tests
uv run ruff check      # lint
uv run ruff format     # format
```

## Release notes

See [`docs/release-notes/`](docs/release-notes/README.md) for changes in each version.

## License

[MIT](LICENSE)
