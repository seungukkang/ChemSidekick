// The amino-acid tool's data (BIO-01 `aa`, result.data of `csk run aa`) and how
// the Amino Acids command orders and searches it. Pure, so it can be tested.

export interface AminoAcid {
  one: string;
  three: string;
  name: string;
  class: string; // nonpolar | aromatic | polar | positive | negative | other
  class_title: string; // e.g. "Aromatic"
  essential: boolean;
  ids: { ccd: string; pubchem_cid: number; chebi: string };
  smiles: string;
  smiles_ph7: string;
  inchikey: string;
  formula: string;
  iupac_name: string;
  stereo: { alpha: string | null; beta: string | null; other: string[]; text: string };
  mass: { mono: number; avg: number; residue_mono: number; residue_avg: number };
  mass_check: { mono: string; mono_refs: string[]; avg: string; avg_refs: string[] };
  pka: {
    alpha_cooh: number | null;
    alpha_nh3: number | null;
    side_chain: number | null;
    status: string; // provisional | none
  };
  pi: number | null;
  hydropathy_kd: number | null;
  codons: string[];
  codons_note: string;
}

export interface Ambiguous {
  one: string;
  three: string;
  meaning: string;
  members: string[];
}

export interface AminoAcidData {
  classes: Record<string, string>; // key -> title, in display order
  amino_acids: AminoAcid[];
  ambiguous: Ambiguous[];
  drawings: Record<string, string>; // one-letter -> SVG text: white card, border in the class color
  banners: Record<string, string>; // the same as a wide card, for the list's side panel
}

// True when `value` has the shape this version expects (e.g. not a list cached by
// an older version of the extension, whose drawings were { light, dark } objects).
export function isAminoAcidData(value: unknown): value is AminoAcidData {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Partial<AminoAcidData>;
  return (
    Array.isArray(v.amino_acids) &&
    typeof v.drawings === "object" &&
    v.drawings !== null &&
    Object.values(v.drawings).every((svg) => typeof svg === "string") &&
    typeof v.banners === "object" &&
    v.banners !== null
  );
}

export type SortMode = "class" | "alphabetical" | "hydropathy" | "mass";

export const SORT_TITLES: Record<SortMode, string> = {
  class: "By Class",
  alphabetical: "Alphabetical",
  hydropathy: "By Hydropathy",
  mass: "By Residue Mass",
};

// Same hues as the card borders and side-chain highlights (CLASS_COLORS in aa.py).
export const CLASS_COLORS: Record<string, string> = {
  nonpolar: "#f59e0b",
  aromatic: "#8b5cf6",
  polar: "#10b981",
  positive: "#3b82f6",
  negative: "#f43f5e",
  other: "#6b7280",
};

export interface Section {
  title: string;
  subtitle: string;
  items: AminoAcid[];
}

// The grid's sections for a sort mode. Sec and Pyl (class "other") stay in their
// own section at the end, except alphabetically.
export function sections(data: AminoAcidData, mode: SortMode): Section[] {
  const all = data.amino_acids;
  const standard = all.filter((a) => a.class !== "other");
  const other = all.filter((a) => a.class === "other");
  const otherSection = { title: data.classes.other ?? "Other", subtitle: "", items: other };
  if (mode === "class") {
    return Object.entries(data.classes)
      .map(([key, title]) => ({ title, subtitle: "", items: all.filter((a) => a.class === key) }))
      .filter((s) => s.items.length > 0)
      .map((s) => ({ ...s, subtitle: String(s.items.length) }));
  }
  if (mode === "alphabetical") {
    const items = [...all].sort((a, b) => a.name.localeCompare(b.name));
    return [{ title: "All", subtitle: "by name", items }];
  }
  if (mode === "hydropathy") {
    const items = [...standard].sort((a, b) => (b.hydropathy_kd ?? 0) - (a.hydropathy_kd ?? 0));
    return [{ title: "Kyte–Doolittle", subtitle: "most hydrophobic first", items }, otherSection];
  }
  const items = [...standard].sort((a, b) => a.mass.residue_mono - b.mass.residue_mono);
  return [{ title: "Residue mass", subtitle: "lightest first", items }, otherSection];
}

// Search: one letter is a one-letter code (W = Trp only); B, Z, J, X show the
// amino acids they stand for; longer text matches the start of the three-letter
// code, the name, or a class.
export function search(data: AminoAcidData, text: string): { matches: AminoAcid[] | null; ambiguous?: Ambiguous } {
  const q = text.trim().toLowerCase();
  if (!q) return { matches: null }; // no search: show the sections
  if (q.length === 1) {
    const exact = data.amino_acids.filter((a) => a.one.toLowerCase() === q);
    if (exact.length) return { matches: exact };
    const amb = data.ambiguous.find((b) => b.one.toLowerCase() === q);
    if (amb) return { matches: membersOf(data, amb), ambiguous: amb };
    return { matches: [] };
  }
  const amb = data.ambiguous.find((b) => b.three.toLowerCase() === q);
  if (amb) return { matches: membersOf(data, amb), ambiguous: amb };
  const matches = data.amino_acids.filter(
    (a) =>
      a.three.toLowerCase().startsWith(q) ||
      a.name.toLowerCase().startsWith(q) ||
      (data.classes[a.class] ?? "")
        .toLowerCase()
        .split(/[\s,]+/)
        .some((w) => w.startsWith(q)) ||
      (CLASS_WORDS[a.class] ?? []).some((w) => w.startsWith(q)),
  );
  return { matches };
}

const CLASS_WORDS: Record<string, string[]> = {
  nonpolar: ["nonpolar", "aliphatic"],
  aromatic: ["aromatic"],
  polar: ["polar", "uncharged"],
  positive: ["basic", "positive"],
  negative: ["acidic", "negative"],
};

function membersOf(data: AminoAcidData, amb: Ambiguous): AminoAcid[] {
  return amb.members.map((m) => data.amino_acids.find((a) => a.one === m)).filter((a): a is AminoAcid => Boolean(a));
}

// --- Formatting ------------------------------------------------------------------

export function num(value: number | null | undefined, digits: number): string {
  return value === null || value === undefined ? "—" : value.toFixed(digits).replace("-", "−");
}

export function signed(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return (value > 0 ? `+${value.toFixed(1)}` : value.toFixed(1)).replace("-", "−");
}

export function stereoText(a: AminoAcid): string {
  return a.stereo.text === "achiral" ? "achiral (no L/D)" : `L · ${a.stereo.text}`;
}

export function pkaText(a: AminoAcid): string {
  const parts = [num(a.pka.alpha_cooh, 2), num(a.pka.alpha_nh3, 2)];
  if (a.pka.side_chain !== null) parts.push(num(a.pka.side_chain, 2));
  return a.pka.status === "none" ? "—" : parts.join(" · ");
}

export function links(a: AminoAcid): { title: string; text: string; url: string }[] {
  return [
    { title: "PDB CCD", text: a.ids.ccd, url: `https://www.rcsb.org/ligand/${a.ids.ccd}` },
    {
      title: "PubChem",
      text: `CID ${a.ids.pubchem_cid}`,
      url: `https://pubchem.ncbi.nlm.nih.gov/compound/${a.ids.pubchem_cid}`,
    },
    { title: "ChEBI", text: a.ids.chebi, url: `https://www.ebi.ac.uk/chebi/searchId.do?chebiId=${a.ids.chebi}` },
  ];
}
