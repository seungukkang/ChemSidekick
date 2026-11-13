# ChemSidekick

You can find most of this by googling or asking AI. But sometimes the AI's sense of style isn't yours, or its drawing looks like a five-year-old drew it, and sometimes it's just a hassle for something you only want to check for two seconds. ChemSidekick collects those little things one by one and puts them behind a hotkey, so researchers can look them up quickly and get back to work.

Use it from the terminal (`csk`), a local web interface, or Raycast.

> **Status:** v0.2.1. Five tools; CLI, Streamlit web interface, and a Raycast extension. More tools coming soon!

## Tools

| ID | Command | What it does |
|---|---|---|
| REF-01 | `csk element` | Element card (atomic weights, electron configuration, isotopes, …) or the periodic table |
| REF-02 | `csk units` | Chemistry unit conversions a calculator does not do: kcal/mol ↔ eV ↔ hartree, cm⁻¹ ↔ nm ↔ K, molar entropy, bohr, debye, polarizability, M⁻¹s⁻¹ ↔ cm³ molecule⁻¹ s⁻¹, pressure, charge; with RT and kT |
| STR-01 | `csk xyz` | Paste XYZ coordinates (one or many frames): formula, molecular weight, closest atoms, a 2D drawing from bonds inferred from the coordinates, and an interactive 3D view |
| STR-02 | `csk stereo` | All stereoisomers of a SMILES (or a simple condensed formula): R/S, r/s and E/Z with IUPAC locants, enantiomer/diastereomer/meso relations, 2D drawings and 3D structures |
| ENE-01 | `csk profile` | Energy profile A → TS → products: rate constants, half-lives, kinetic and equilibrium product ratios, diffusion-limited rates, the temperature for a target half-life, the ΔΔG‡ for a target selectivity; or Boltzmann populations of conformers |

Every chemical value in `element` is cross-checked against one primary source and two authoritative compilations, and each value shows whether it was confirmed (see [`data/verification/elements.md`](data/verification/elements.md)). In `units`, conversions that use only defined constants are marked exact; the measured constants (hartree, Bohr radius, ε₀; CODATA 2022) are each checked against three references ([`data/verification/units.md`](data/verification/units.md)). The solvent viscosities used for diffusion-limited rates in `profile` are listed only when three references agree ([`data/verification/solvents.md`](data/verification/solvents.md)).

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
csk units 1 eV to kcal/mol     # one conversion; `csk units 300 nm` shows every related unit
csk xyz molecule.xyz           # or paste coordinates: pbpaste | csk xyz
csk stereo "CC(O)C(O)C(O)C"    # stereoisomers; also accepts CH3-CH(OH)-CH3
csk profile --paths $'B 20.0 -3.0\nC 22.0 -5.0'   # energy profile: two competing paths
csk ui                         # web interface in the browser
```

- `csk list` and `csk search <word>` find tools; `csk <tool> --help` shows its options.
- `--json` prints one JSON object (`{"ok": true, "result": …, "run": …}` or `{"ok": false, "error": …}`), also for errors, and exits with a code per error type. `csk list --json` describes every tool and its inputs.
- `csk run <tool> --json` takes the tool's input as JSON on standard input, for programs: `echo '{"smiles": "CC(Br)C(Br)C"}' | csk run stereo --json`. The format is versioned; its JSON Schemas are in [`schemas/`](schemas/).
- `--no-record` runs without keeping a recent result.
- `csk gif --json` turns one 3D structure (a frame from a result, as JSON on standard input) into a rotating GIF, for places without the interactive viewer (used by the Raycast extension).
- Every run is kept as a recent result (newest 50). `csk recent` lists them and `csk save <number>` keeps one in `~/Documents/ChemSidekick`.
- The 3D viewer loads [3Dmol.js](https://3dmol.csb.pitt.edu/) from a CDN, so it needs an internet connection.

## Raycast extension

The extension in [`apps/raycast/`](apps/raycast/) runs `csk` in the background. It needs [Raycast](https://www.raycast.com/) and Node.js 22.22.2 or newer.

```sh
uv tool install --editable .    # puts csk in ~/.local/bin, where the extension looks for it
cd apps/raycast
npm install
npm run dev                     # loads the extension into Raycast; it stays after you stop this
```

| Command | What it does |
|---|---|
| ChemSidekick | All tools: pick one, fill in its form, see the result |
| Element | Search elements by symbol, name, or atomic number; card on Enter, periodic table on ⌘T |
| Convert Units | Type a value and pick its unit beside the search bar; every related unit is listed, with its definition, constants and sources on the right. Enter copies a value, ⌘⇧C at full precision, ⌘T sets the temperature for RT and kT |
| XYZ Viewer | Paste coordinates; 2D drawing and rotating 3D view side by side, then the details |
| Stereoisomers | Type `stereo` and a SMILES; isomers as cards, Enter turns a card into a rotating 3D view |
| Energy Profile | The paths on the left, the drawing and the answer on the right, redrawn as values change. Type `D 21 -4` (name, TS, product) in the search bar and press Enter to add a path; Enter on a path edits it. Reaction or Boltzmann populations beside the search bar; temperature (typed, in K) and unit in the list, the rest under More options; ⌘↵ shows the full result. The last input is remembered |

- If `csk` is somewhere else, set its path in the extension preferences.
- After Python dependencies change, reinstall with `uv tool install --editable . --reinstall`.

## Architecture

```
Interfaces (CLI · Streamlit · Raycast; later web app · MCP)
        │            Raycast talks to csk through a versioned JSON format (schemas/)
   chemsidekick core (tool registry, runner with time/memory limits, result store)
        │
   tools (each declares its inputs once; CLI options and forms are generated)
```

Adding a tool means adding one module under `src/chemsidekick/tools/`. It shows up in the CLI, the web interface, and the Raycast ChemSidekick command without interface changes.

## Development

```sh
uv run pytest          # tests
uv run ruff check      # lint
uv run ruff format     # format

cd apps/raycast
npm run check          # ESLint, Prettier, TypeScript
npm test               # vitest
```

## Release notes

See [`docs/release-notes/`](docs/release-notes/README.md) for changes in each version.

## License

[MIT](LICENSE)
