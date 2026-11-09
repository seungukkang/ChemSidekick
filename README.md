# ChemSidekick

A personal toolbox of small chemistry calculators and visualizers, available from the CLI, a web UI, a launcher (Raycast), and AI assistants (MCP).

> **Status:** Planning (v0.0.0). No code yet.

## Planned tools (v0.1.0)

- **element**: quick element lookup and periodic table
- **xyz**: paste XYZ coordinates → interactive 3D view
- **stereo**: SMILES → all stereoisomers as 2D images and 3D structures

## Architecture

```
Interfaces (CLI · Streamlit → Web · Raycast · MCP)
        │
   Local API (FastAPI, localhost)
        │
   chemsidekick core (tool registry + tools)
```

## Release notes

See [`docs/release-notes/`](docs/release-notes/README.md) for changes in each version.

## License

[MIT](LICENSE)
