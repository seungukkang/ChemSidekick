// Does text (e.g. the clipboard) look like XYZ coordinates? Only a quick guess
// to fill in the form: csk reads and checks the coordinates for real.

// An atom line: element symbol (any case, optionally numbered like "C1") or
// atomic number, then three numbers (Fortran "D" exponents allowed).
const NUMBER = String.raw`[-+]?(?:\d+\.?\d*|\.\d+)(?:[eEdD][-+]?\d+)?`;
const ATOM_LINE = new RegExp(String.raw`^\s*(?:[A-Za-z]{1,3}\d*|\d{1,3})\s+${NUMBER}\s+${NUMBER}\s+${NUMBER}(?:\s|$)`);

export function looksLikeXyz(text: string | undefined, minAtoms = 2): boolean {
  if (!text) return false;
  const atoms = text.split(/\r?\n/).filter((line) => ATOM_LINE.test(line)).length;
  return atoms >= minAtoms;
}
