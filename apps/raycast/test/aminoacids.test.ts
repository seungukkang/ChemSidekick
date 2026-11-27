import { describe, expect, it } from "vitest";
import {
  type AminoAcid,
  type AminoAcidData,
  isAminoAcidData,
  num,
  pkaText,
  search,
  sections,
  signed,
} from "../src/lib/aminoacids";

function aa(one: string, three: string, name: string, cls: string, kd: number | null, mass: number): AminoAcid {
  return {
    one,
    three,
    name,
    class: cls,
    class_title: cls,
    essential: false,
    ids: { ccd: three.toUpperCase(), pubchem_cid: 1, chebi: "CHEBI:1" },
    smiles: "",
    smiles_ph7: "",
    inchikey: "",
    formula: "",
    iupac_name: "",
    stereo: { alpha: "S", beta: null, other: [], text: "(2S)" },
    mass: { mono: mass + 18, avg: mass + 18, residue_mono: mass, residue_avg: mass },
    mass_check: { mono: "verified", mono_refs: [], avg: "verified", avg_refs: [] },
    pka: { alpha_cooh: 2.2, alpha_nh3: 9.1, side_chain: null, status: "provisional" },
    pi: 5.6,
    hydropathy_kd: kd,
    codons: [],
    codons_note: "",
  };
}

const DATA: AminoAcidData = {
  classes: {
    nonpolar: "Nonpolar, aliphatic",
    aromatic: "Aromatic",
    polar: "Polar, uncharged",
    negative: "Negatively charged",
    other: "Other proteinogenic",
  },
  amino_acids: [
    aa("G", "Gly", "Glycine", "nonpolar", -0.4, 57),
    aa("I", "Ile", "Isoleucine", "nonpolar", 4.5, 113),
    aa("W", "Trp", "Tryptophan", "aromatic", -0.9, 186),
    aa("S", "Ser", "Serine", "polar", -0.8, 87),
    aa("D", "Asp", "Aspartate", "negative", -3.5, 115),
    aa("N", "Asn", "Asparagine", "polar", -3.5, 114),
    aa("U", "Sec", "Selenocysteine", "other", null, 151),
  ],
  ambiguous: [{ one: "B", three: "Asx", meaning: "Aspartate or asparagine", members: ["D", "N"] }],
  drawings: {},
  banners: {},
};

const ones = (items: AminoAcid[] | null) => (items ?? []).map((a) => a.one).join("");

describe("sections", () => {
  it("groups by class in the given order, skipping empty classes", () => {
    const s = sections(DATA, "class");
    expect(s.map((x) => x.title)).toEqual([
      "Nonpolar, aliphatic",
      "Aromatic",
      "Polar, uncharged",
      "Negatively charged",
      "Other proteinogenic",
    ]);
    expect(ones(s[0].items)).toBe("GI");
  });
  it("orders by hydropathy with Sec/Pyl apart", () => {
    const s = sections(DATA, "hydropathy");
    expect(ones(s[0].items)).toBe("IGSWDN");
    expect(ones(s[1].items)).toBe("U");
  });
  it("orders by residue mass and by name", () => {
    expect(ones(sections(DATA, "mass")[0].items)).toBe("GSINDW");
    expect(ones(sections(DATA, "alphabetical")[0].items)).toBe("NDGIUSW");
  });
});

describe("search", () => {
  it("reads one letter as a one-letter code", () => {
    expect(ones(search(DATA, "w").matches)).toBe("W");
    expect(ones(search(DATA, "S").matches)).toBe("S");
  });
  it("expands ambiguity codes", () => {
    const r = search(DATA, "B");
    expect(ones(r.matches)).toBe("DN");
    expect(r.ambiguous?.three).toBe("Asx");
    expect(ones(search(DATA, "asx").matches)).toBe("DN");
  });
  it("matches codes, names and classes by their start", () => {
    expect(ones(search(DATA, "as").matches)).toBe("DN");
    expect(ones(search(DATA, "trypt").matches)).toBe("W");
    expect(ones(search(DATA, "acidic").matches)).toBe("D");
    expect(ones(search(DATA, "polar").matches)).toBe("SN"); // not "Nonpolar"
  });
  it("shows sections when empty, nothing for unknown letters", () => {
    expect(search(DATA, "  ").matches).toBeNull();
    expect(search(DATA, "@").matches).toEqual([]);
  });
});

describe("cached data", () => {
  it("accepts the current shape and rejects an older cache", () => {
    expect(isAminoAcidData({ ...DATA, drawings: { G: "<svg/>" } })).toBe(true);
    expect(isAminoAcidData({ ...DATA, banners: undefined })).toBe(false);
    expect(isAminoAcidData({ ...DATA, drawings: { G: { light: "<svg/>", dark: "<svg/>" } } })).toBe(false);
    expect(isAminoAcidData(undefined)).toBe(false);
  });
});

describe("formatting", () => {
  it("formats numbers with a real minus sign", () => {
    expect(num(-0.4, 1)).toBe("−0.4");
    expect(signed(4.5)).toBe("+4.5");
    expect(signed(null)).toBe("—");
    expect(pkaText(DATA.amino_acids[0])).toBe("2.20 · 9.10");
  });
});
