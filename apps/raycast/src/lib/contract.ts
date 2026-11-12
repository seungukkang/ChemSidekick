// JSON contract v1 between csk and its interfaces (src/chemsidekick/core/contract.py).
// JSON Schemas: schemas/contract-v1/. Readers must ignore fields they do not know.

export const CONTRACT_VERSION = 1;

// --- ToolResult (src/chemsidekick/core/schemas.py) ----------------------------

export type Cell = string | number | null;

export interface CellInfo {
  top: string;
  tag: string;
  lines: string[];
  unconfirmed: boolean;
}

export interface Table {
  title: string;
  columns: string[];
  rows: Cell[][];
  minor_columns: number[];
  action_field: string | null;
  action_columns: number[];
  cells: Record<string, CellInfo>;
  tags: Record<string, string>;
  column_gaps: number[];
}

export type ArtifactKind = "svg" | "png" | "sdf" | "xyz" | "html" | "json" | (string & {});

export interface Artifact {
  kind: ArtifactKind;
  path: string; // absolute
  title: string;
  note: string;
}

export interface Highlight {
  label: string;
  value: string;
  note: string;
}

export interface Formula {
  latex: string;
  text: string;
}

export interface Constant {
  name: string;
  symbol: string;
  value: number;
  unit: string;
  source: string;
}

export interface Mark {
  atoms: number[]; // atom indexes from 0
  label: string;
}

export interface Frame {
  symbols: string[];
  coords: [number, number, number][]; // Å
  comment: string;
  numbers: string[];
  marks: Mark[];
}

export interface Structure3D {
  frames: Frame[];
  title: string;
  style: string;
  labels: boolean;
  marks_shown: boolean;
  start_frame: number;
  navigation: "frames" | "pages" | (string & {});
  page_name: string;
  numbers_name: string;
}

export interface ToolResult {
  answer: string;
  highlights: Highlight[];
  formulas: Formula[];
  constants: Constant[];
  assumptions: string[];
  sources: string[];
  notes: string[];
  tables: Table[];
  structures: Structure3D[]; // the HTML 3D viewer and `csk gif` draw these
  artifacts: Artifact[];
  warnings: string[];
  data: Record<string, unknown>;
}

// --- Responses ----------------------------------------------------------------

interface Envelope {
  contract: number;
  csk_version: string;
}

export interface RunInfo {
  tool: string;
  tool_id: string;
  number: number | null; // null with --no-record
  folder: string;
  recorded: boolean;
  elapsed_s: number;
  peak_memory_mb: number | null;
}

export interface RunResponse extends Envelope {
  ok: true;
  result: ToolResult;
  run: RunInfo;
}

export type ErrorType = "input" | "limit" | "crash" | "confirm" | "missing_program" | "config" | (string & {});

export interface ErrorDetail {
  field: string;
  message: string;
}

export interface ErrorInfo {
  type: ErrorType;
  message: string;
  details: ErrorDetail[];
  traceback: string;
}

export interface ErrorResponse extends Envelope {
  ok: false;
  error: ErrorInfo;
}

export interface CategoryInfo {
  name: string;
  code: string;
  title: string;
}

export interface ToolInfo {
  id: string;
  name: string;
  title: string;
  summary: string;
  category: string;
  keywords: string[];
  resources: "light" | "medium" | "heavy";
  requires: string[];
  available: boolean;
  unavailable_reason: string;
  icon: string;
  start_view: string;
  input_schema: Record<string, unknown>;
}

export interface ToolListResponse extends Envelope {
  ok: true;
  categories: CategoryInfo[];
  tools: ToolInfo[];
}

export interface SaveResponse extends Envelope {
  ok: true;
  number: number;
  saved_to: string;
}

// `csk gif`: a rotating 3D view of one structure frame (a view, not a tool).
export interface GifRequest {
  frame: Pick<Frame, "symbols" | "coords" | "comment">;
  title?: string;
  note?: string;
}

export interface GifResponse extends Envelope {
  ok: true;
  path: string;
  frames: number;
}
