"""Read a condensed structural formula as SMILES, e.g.

    CH3–CH(OH)–CH=CH–CH(OH)–CH3   ->  CC(O)C=CC(O)C
    HO-CH2-CH2-OH                 ->  OCCO
    (CH3)2CH-COOH                 ->  not supported (leading branch) -> None

Only simple chains are read: atoms with hydrogen counts (CH3, CH, NH2, OH),
bonds (- – = ≡), branches in parentheses with an optional count ((CH3)2),
and the end groups COOH and CHO. Anything else returns None.

Every result is checked: the SMILES is read back with RDKit and each atom must
carry exactly the number of hydrogens written in the formula. A reading that
does not pass is rejected, so a formula is never silently misread.
"""

import re
from dataclasses import dataclass, field

ELEMENTS = ("Cl", "Br", "C", "N", "O", "S", "F", "I", "P", "B")
DASHES = str.maketrans({"–": "-", "—": "-", "−": "-", "‐": "-", "≡": "#"})
BONDS = {"-": "", "=": "=", "#": "#"}
# End groups written as one unit: SMILES and the hydrogens on each of its atoms.
GROUPS = {"COOH": ("C(=O)O", [0, 0, 1]), "CHO": ("C=O", [1, 0])}
# Groups written with the hydrogen first, at the start of a formula.
LEADING = {"HO": ("O", 1), "HS": ("S", 1), "H2N": ("N", 2)}


@dataclass
class _Out:
    smiles: str = ""
    hydrogens: list[int] = field(default_factory=list)


class _Fail(Exception):
    pass


class _Reader:
    def __init__(self, text: str) -> None:
        self.s = text
        self.i = 0

    def peek(self, n: int = 1) -> str:
        return self.s[self.i : self.i + n]

    def chain(self) -> _Out:
        out = self.unit(first=True)
        while self.i < len(self.s) and self.peek() != ")":
            bond = ""
            if self.peek() in BONDS:
                bond = BONDS[self.peek()]
                self.i += 1
            nxt = self.unit()
            out.smiles += bond + nxt.smiles
            out.hydrogens += nxt.hydrogens
        return out

    def count(self) -> int:
        m = re.match(r"\d+", self.s[self.i :])
        if not m:
            return 1
        self.i += len(m.group())
        return int(m.group())

    def unit(self, first: bool = False) -> _Out:
        out = _Out()
        if first:
            for text, (atom, h) in LEADING.items():
                if self.s.startswith(text, self.i):
                    self.i += len(text)
                    out.smiles, out.hydrogens = atom, [h]
                    return self.branches(out)
        for text, (smiles, hs) in GROUPS.items():
            if self.s.startswith(text, self.i):
                self.i += len(text)
                return _Out(smiles, list(hs))
        element = next((e for e in ELEMENTS if self.s.startswith(e, self.i)), None)
        if element is None:
            raise _Fail
        self.i += len(element)
        h = 0
        if self.peek() == "H":
            self.i += 1
            h = self.count()
        out.smiles, out.hydrogens = element, [h]
        return self.branches(out)

    def branches(self, out: _Out) -> _Out:
        while self.peek() == "(":
            self.i += 1
            bond = ""
            if self.peek() in BONDS:
                bond = BONDS[self.peek()]
                self.i += 1
            inner = self.chain()
            if self.peek() != ")":
                raise _Fail
            self.i += 1
            for _ in range(self.count()):
                out.smiles += f"({bond}{inner.smiles})"
                out.hydrogens += inner.hydrogens
        return out


def parse(text: str) -> tuple[str, list[int]] | None:
    """Condensed formula -> (SMILES, hydrogens per atom in SMILES order), unchecked."""
    s = re.sub(r"\s+", "", text.translate(DASHES))
    if not s:
        return None
    reader = _Reader(s)
    try:
        out = reader.chain()
    except _Fail:
        return None
    if reader.i != len(s):
        return None
    return out.smiles, out.hydrogens


def to_smiles(text: str) -> str | None:
    """Condensed formula -> SMILES, only if RDKit agrees on every hydrogen count."""
    from rdkit import Chem, RDLogger

    parsed = parse(text)
    if parsed is None:
        return None
    smiles, hydrogens = parsed
    RDLogger.DisableLog("rdApp.*")
    try:
        mol = Chem.MolFromSmiles(smiles)
    finally:
        RDLogger.EnableLog("rdApp.*")
    if mol is None or mol.GetNumAtoms() != len(hydrogens):
        return None
    if any(a.GetTotalNumHs() != h for a, h in zip(mol.GetAtoms(), hydrogens, strict=True)):
        return None
    return smiles


def looks_condensed(text: str) -> bool:
    """Hydrogens written out (CH3, OH) or typographic dashes: not SMILES."""
    return bool(re.search(r"[CNOS]H\d?|[–—−]", text))
