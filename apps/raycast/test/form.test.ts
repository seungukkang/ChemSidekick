import { describe, expect, it } from "vitest";
import type { ToolListResponse } from "../src/lib/contract";
import { formSpec, toInput } from "../src/lib/form";
import { fixture } from "./helpers";

const tools = (JSON.parse(fixture("list")) as ToolListResponse).tools;
const schemaOf = (name: string) => tools.find((t) => t.name === name)!.input_schema;

describe("formSpec on the real tools", () => {
  it("every current tool is supported", () => {
    for (const t of tools) expect(formSpec(t.input_schema).unsupported).toEqual([]);
  });

  it("stereo: required SMILES first, integer range, check boxes", () => {
    const { fields } = formSpec(schemaOf("stereo"));
    expect(fields.map((f) => f.name)).toEqual(["smiles", "max_isomers", "enumerate_all", "skip_3d"]);
    const [smiles, max, all] = fields;
    expect(smiles).toMatchObject({ kind: "text", label: "SMILES", required: true, positional: true });
    expect(max).toMatchObject({ kind: "integer", label: "Max isomers", default: "8", minimum: 1, maximum: 1024 });
    expect(all).toMatchObject({ kind: "checkbox", default: false });
  });

  it("xyz: long text, optional integer, choices", () => {
    const { fields } = formSpec(schemaOf("xyz"));
    const byName = Object.fromEntries(fields.map((f) => [f.name, f]));
    expect(byName.text).toMatchObject({ kind: "textarea", fileInput: true, required: false });
    expect(byName.frame).toMatchObject({ kind: "integer", nullable: true, default: "", minimum: 1 });
    expect(byName.style).toMatchObject({ kind: "dropdown", default: "ball-and-stick" });
    expect(byName.style.options).toEqual(["ball-and-stick", "stick", "sphere"]);
  });

  it("element: optional text (empty = periodic table)", () => {
    expect(formSpec(schemaOf("element")).fields[0]).toMatchObject({
      name: "query",
      kind: "text",
      nullable: true,
      required: false,
      default: "",
    });
  });

  it("reports field types it cannot show", () => {
    const spec = formSpec({ properties: { values: { type: "array", items: { type: "number" } } } });
    expect(spec.unsupported).toEqual(['values: "array"']);
  });
});

describe("toInput", () => {
  const stereo = formSpec(schemaOf("stereo")).fields;

  it("converts numbers and keeps check boxes", () => {
    const r = toInput(stereo, { smiles: " CC(Br)C(Br)C ", max_isomers: "16", enumerate_all: true, skip_3d: false });
    expect(r.errors).toEqual({});
    expect(r.input).toEqual({ smiles: "CC(Br)C(Br)C", max_isomers: 16, enumerate_all: true, skip_3d: false });
  });

  it("checks required fields and ranges before running csk", () => {
    expect(toInput(stereo, { smiles: "", max_isomers: "8" }).errors).toEqual({ smiles: "Required" });
    expect(toInput(stereo, { smiles: "CC", max_isomers: "0" }).errors).toEqual({ max_isomers: "At least 1" });
    expect(toInput(stereo, { smiles: "CC", max_isomers: "2000" }).errors).toEqual({ max_isomers: "At most 1024" });
    expect(toInput(stereo, { smiles: "CC", max_isomers: "2.5" }).errors).toEqual({
      max_isomers: "Enter a whole number",
    });
  });

  it("leaves empty optional fields out so the tool's default applies", () => {
    const xyz = formSpec(schemaOf("xyz")).fields;
    const r = toInput(xyz, { text: "3\n\nO 0 0 0\n", frame: "", style: "stick", labels: false });
    expect(r.input).toEqual({ text: "3\n\nO 0 0 0\n", style: "stick", labels: false });
    const element = formSpec(schemaOf("element")).fields;
    expect(toInput(element, { query: "" }).input).toEqual({});
  });
});
