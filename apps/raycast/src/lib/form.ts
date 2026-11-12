// A tool's input JSON Schema (from `csk list --json`) -> form fields, and form
// values -> the tool input JSON for `csk run`. Pure, so it can be tested.
//
// Supported field types match the CLI and Streamlit forms: text, long text,
// integer, number, choice, on/off. A tool with any other field type is marked
// unsupported (the screen offers its csk command instead).

export type FieldKind = "text" | "textarea" | "integer" | "number" | "checkbox" | "dropdown";

export interface FieldSpec {
  name: string;
  kind: FieldKind;
  label: string;
  description: string;
  required: boolean; // must be given (no default)
  nullable: boolean; // may be left empty -> omitted, the tool uses its default
  default: string | boolean; // form value: text for text/number fields, boolean for checkboxes
  options: string[]; // dropdown choices
  minimum?: number;
  maximum?: number;
  minLength?: number;
  positional: boolean; // the main input (first field)
  fileInput: boolean; // long text that may come from the clipboard
}

export interface FormSpec {
  fields: FieldSpec[];
  unsupported: string[]; // "field: reason"
}

type Schema = Record<string, unknown>;

function asSchema(value: unknown): Schema {
  return typeof value === "object" && value !== null ? (value as Schema) : {};
}

// `X | None` is written as anyOf [X, {type: null}]: unwrap it.
function unwrapNullable(prop: Schema): { schema: Schema; nullable: boolean } {
  const anyOf = prop.anyOf;
  if (Array.isArray(anyOf)) {
    const nonNull = anyOf.map(asSchema).filter((s) => s.type !== "null");
    if (nonNull.length === 1 && nonNull.length < anyOf.length) {
      return { schema: { ...prop, ...nonNull[0], anyOf: undefined }, nullable: true };
    }
  }
  return { schema: prop, nullable: false };
}

function kindOf(schema: Schema): FieldKind | null {
  if (Array.isArray(schema.enum) && schema.enum.every((v) => typeof v === "string")) return "dropdown";
  switch (schema.type) {
    case "string":
      return schema.multiline ? "textarea" : "text";
    case "integer":
      return "integer";
    case "number":
      return "number";
    case "boolean":
      return "checkbox";
    default:
      return null;
  }
}

export function formSpec(inputSchema: Record<string, unknown>): FormSpec {
  const properties = asSchema(inputSchema.properties);
  const required = new Set(Array.isArray(inputSchema.required) ? (inputSchema.required as string[]) : []);
  const fields: FieldSpec[] = [];
  const unsupported: string[] = [];
  for (const [name, raw] of Object.entries(properties)) {
    const prop = asSchema(raw);
    const { schema, nullable } = unwrapNullable(prop);
    const kind = kindOf(schema);
    if (!kind) {
      unsupported.push(`${name}: ${JSON.stringify(prop.type ?? prop.anyOf ?? "unknown type")}`);
      continue;
    }
    const dflt = prop.default;
    fields.push({
      name,
      kind,
      label: String(schema.label ?? schema.title ?? name),
      description: String(schema.description ?? ""),
      required: required.has(name),
      nullable,
      default: kind === "checkbox" ? dflt === true : dflt === undefined || dflt === null ? "" : String(dflt),
      options: kind === "dropdown" ? (schema.enum as string[]) : [],
      minimum: typeof schema.minimum === "number" ? schema.minimum : undefined,
      maximum: typeof schema.maximum === "number" ? schema.maximum : undefined,
      minLength: typeof schema.minLength === "number" ? schema.minLength : undefined,
      positional: schema.positional === true,
      fileInput: schema.file_input === true,
    });
  }
  // The main input first, as in the CLI.
  fields.sort((a, b) => Number(b.positional) - Number(a.positional));
  return { fields, unsupported };
}

export type FormValues = Record<string, string | boolean | undefined>;

export interface ToInputResult {
  input: Record<string, unknown>;
  errors: Record<string, string>; // field name -> message, shown on the field
}

// Form values -> tool input. Empty optional fields are left out so the tool's
// own default applies; csk validates everything again.
export function toInput(fields: FieldSpec[], values: FormValues): ToInputResult {
  const input: Record<string, unknown> = {};
  const errors: Record<string, string> = {};
  for (const f of fields) {
    const value = values[f.name];
    if (f.kind === "checkbox") {
      input[f.name] = value === true;
      continue;
    }
    const text = typeof value === "string" ? value : "";
    const empty = f.kind === "textarea" || f.kind === "text" ? text.length === 0 : text.trim().length === 0;
    if (empty) {
      if (f.required) errors[f.name] = "Required";
      continue; // default (or null) applies
    }
    if (f.kind === "integer" || f.kind === "number") {
      const n = Number(text.trim());
      if (!Number.isFinite(n) || (f.kind === "integer" && !Number.isInteger(n))) {
        errors[f.name] = f.kind === "integer" ? "Enter a whole number" : "Enter a number";
        continue;
      }
      if (f.minimum !== undefined && n < f.minimum) {
        errors[f.name] = `At least ${f.minimum}`;
        continue;
      }
      if (f.maximum !== undefined && n > f.maximum) {
        errors[f.name] = `At most ${f.maximum}`;
        continue;
      }
      input[f.name] = n;
      continue;
    }
    input[f.name] = f.kind === "text" ? text.trim() : text;
  }
  return { input, errors };
}
