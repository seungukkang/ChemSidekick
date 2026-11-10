"""IUPAC locants (position numbers) for stereo descriptors, e.g. (2R,3s,4S).

RDKit does not number molecules the IUPAC way, so this module chooses the
parent hydride and its numbering with the rules of the IUPAC 2013
Recommendations (P-44 parent selection, P-31.1.4 lowest locants), for:

    - open chains (acyclic carbon chains), and
    - single carbocyclic rings (cyclohexane, cyclohexene, benzene, ...).

Parent selection (simplified P-44.1): most principal characteristic groups
(suffixes such as -oic acid, -ol, -amine) -> rings before chains -> larger
ring / longer chain -> more multiple bonds -> more double bonds -> then the
lowest-locant rules below.

Numbering (P-31.1.4): lowest locants to (c) principal characteristic groups,
(d) multiple bonds, (e) double bonds, (f) all prefixes together, (g) the
prefix cited first in alphanumerical order, then (P-31.1.4.3.4) the
stereodescriptors Z before E, R before S, r before s.

Anything else raises `Unsupported` with a reason (fused, bridged or spiro ring
systems, heteroatoms in rings, stereocenters in a substituent), so a caller
can fall back to plain atom numbers instead of showing a wrong locant.
"""

from dataclasses import dataclass
from functools import cache

# Principal characteristic groups, most senior first (P-41, the ones handled here).
SENIORITY = ["acid", "ester", "amide", "nitrile", "aldehyde", "ketone", "alcohol", "thiol", "amine"]
# Groups whose carbon belongs to the group (-oic acid, -nitrile, ...). On a ring
# they are expressed as -carboxylic acid, -carbonitrile, ... on the ring atom.
CARBON_GROUPS = {"acid", "ester", "amide", "nitrile", "aldehyde"}


class Unsupported(Exception):
    """IUPAC numbering is not available for this structure (the message says why)."""


@dataclass
class Numbering:
    parent: str  # e.g. "pentane chain", "6-membered ring"
    locants: dict[int, int]  # atom index -> locant (parent atoms only)


# ---------------------------------------------------------------------------
# Characteristic groups
# ---------------------------------------------------------------------------


def _groups(mol) -> dict[int, list[tuple[str, set[int]]]]:
    """Carbon atom -> groups it carries: (kind, atoms that belong to the suffix)."""
    from rdkit import Chem

    out: dict[int, list[tuple[str, set[int]]]] = {}
    single, double, triple = Chem.BondType.SINGLE, Chem.BondType.DOUBLE, Chem.BondType.TRIPLE

    def branch(start: int, stop: int) -> set[int]:
        """Atoms reachable from `start` without passing through `stop`."""
        seen, todo = {start}, [start]
        while todo:
            for n in mol.GetAtomWithIdx(todo.pop()).GetNeighbors():
                if n.GetIdx() not in seen and n.GetIdx() != stop:
                    seen.add(n.GetIdx())
                    todo.append(n.GetIdx())
        return seen

    for a in mol.GetAtoms():
        if a.GetSymbol() != "C" or a.GetIsAromatic():
            continue
        i = a.GetIdx()
        nbrs = [(b.GetOtherAtom(a), b.GetBondType()) for b in a.GetBonds()]
        oxo = [n for n, t in nbrs if n.GetSymbol() == "O" and t == double and n.GetDegree() == 1]
        hydroxy = [
            n
            for n, t in nbrs
            if n.GetSymbol() in ("O", "S")
            and t == single
            and n.GetDegree() == 1
            and n.GetTotalNumHs() == 1
            and n.GetFormalCharge() == 0
        ]
        ether_o = [
            n for n, t in nbrs if n.GetSymbol() == "O" and t == single and n.GetDegree() == 2
        ]
        nitrogen = [n for n, t in nbrs if n.GetSymbol() == "N" and t == single]
        carbons = [n for n, _ in nbrs if n.GetSymbol() == "C"]
        found: list[tuple[str, set[int]]] = []
        if oxo:
            o = oxo[0].GetIdx()
            oh = [n for n in hydroxy if n.GetSymbol() == "O"]
            if oh:
                found.append(("acid", {o, oh[0].GetIdx()}))
            elif ether_o:
                found.append(("ester", {o} | branch(ether_o[0].GetIdx(), i)))
            elif nitrogen:
                found.append(("amide", {o} | branch(nitrogen[0].GetIdx(), i)))
            elif len(carbons) == 1 and a.GetTotalNumHs() == 1:
                found.append(("aldehyde", {o}))
            elif len(carbons) == 2:
                found.append(("ketone", {o}))
        elif any(n.GetSymbol() == "N" and t == triple and n.GetDegree() == 1 for n, t in nbrs):
            n = next(n for n, t in nbrs if n.GetSymbol() == "N" and t == triple)
            found.append(("nitrile", {n.GetIdx()}))
        else:
            for n in hydroxy:
                found.append(("alcohol" if n.GetSymbol() == "O" else "thiol", {n.GetIdx()}))
            for n in nitrogen:
                amide_n = any(
                    m.GetSymbol() == "C"
                    and any(
                        b.GetBondType() == double and b.GetOtherAtom(m).GetSymbol() == "O"
                        for b in m.GetBonds()
                    )
                    for m in n.GetNeighbors()
                )
                if not n.GetIsAromatic() and n.GetFormalCharge() == 0 and not amide_n:
                    found.append(("amine", branch(n.GetIdx(), i)))
        if found:
            out[i] = found
    return out


# ---------------------------------------------------------------------------
# Substituent prefixes (names are needed only for the alphanumerical rule)
# ---------------------------------------------------------------------------

_PREFIXES = {
    "*F": "fluoro", "*Cl": "chloro", "*Br": "bromo", "*I": "iodo",
    "*O": "hydroxy", "*=O": "oxo", "*N": "amino", "*S": "sulfanyl",
    "*C": "methyl", "*=C": "methylidene", "*CC": "ethyl", "*CCC": "propyl",
    "*C(C)C": "propan-2-yl", "*CCCC": "butyl", "*C(C)CC": "butan-2-yl",
    "*CC(C)C": "2-methylpropyl", "*C(C)(C)C": "tert-butyl", "*CCCCC": "pentyl",
    "*CCCCCC": "hexyl", "*C=C": "ethenyl", "*C(C)=C": "prop-1-en-2-yl",
    "*OC": "methoxy", "*OCC": "ethoxy", "*NC": "methylamino", "*N(C)C": "dimethylamino",
    "*c1ccccc1": "phenyl", "*[N+](=O)[O-]": "nitro", "*C(=O)O": "carboxy",
    "*C(C)=O": "acetyl", "*C#N": "cyano", "*C=O": "formyl", "*C(N)=O": "carbamoyl",
}  # fmt: skip


@cache
def _prefix_table() -> dict[str, str]:
    from rdkit import Chem

    return {Chem.CanonSmiles(k): v for k, v in _PREFIXES.items()}


def _prefix_name(mol, parent_atom: int, atoms: set[int]) -> str | None:
    """IUPAC prefix name of a substituent (e.g. 'chloro', 'propan-2-yl'), or None."""
    from rdkit import Chem

    m = Chem.RWMol(mol)
    attach = m.GetAtomWithIdx(parent_atom)
    attach.SetAtomicNum(0)  # the attachment point, written "*"
    attach.SetNoImplicit(True)
    attach.SetNumExplicitHs(0)
    attach.SetChiralTag(Chem.ChiralType.CHI_UNSPECIFIED)
    use = sorted(atoms | {parent_atom})
    from rdkit import rdBase

    with rdBase.BlockLogs():  # an unusual fragment is just "no name", not a warning
        try:
            key = Chem.CanonSmiles(Chem.MolFragmentToSmiles(m, atomsToUse=use, canonical=True))
        except Exception:
            return None
    return _prefix_table().get(key)


def _alpha_key(name: str) -> str:
    """Alphanumerical order (P-14.5): letters only; italic tert- is ignored."""
    return "".join(ch for ch in name.removeprefix("tert-") if ch.isalpha())


# ---------------------------------------------------------------------------
# Parents and numberings
# ---------------------------------------------------------------------------


@dataclass
class _Parent:
    kind: int  # 0 ring, 1 chain (rings are senior, P-44.1.2.2)
    atoms: list[int]  # in ring or chain order
    name: str


def _ring_order(mol, ring: tuple[int, ...]) -> list[int]:
    members = set(ring)
    order = [ring[0]]
    while len(order) < len(ring):
        last = mol.GetAtomWithIdx(order[-1])
        nxt = next(
            n.GetIdx()
            for n in last.GetNeighbors()
            if n.GetIdx() in members and n.GetIdx() not in order
            and (len(order) < 2 or n.GetIdx() != order[-2])
        )  # fmt: skip
        order.append(nxt)
    return order


def _parents(mol) -> list[_Parent]:
    ri = mol.GetRingInfo()
    for ring in ri.AtomRings():
        if any(mol.GetAtomWithIdx(i).GetSymbol() != "C" for i in ring):
            raise Unsupported("rings with heteroatoms are not supported")
        if any(ri.NumAtomRings(i) > 1 for i in ring):
            raise Unsupported("fused, bridged or spiro ring systems are not supported")
    parents = [
        _Parent(0, _ring_order(mol, ring), f"{len(ring)}-membered ring") for ring in ri.AtomRings()
    ]
    # Chains: paths between ends of the acyclic carbon skeleton (a forest, so the
    # path between two ends is unique).
    chain_atoms = {
        a.GetIdx()
        for a in mol.GetAtoms()
        if a.GetSymbol() == "C" and not ri.NumAtomRings(a.GetIdx())
    }
    adj = {
        i: [n.GetIdx() for n in mol.GetAtomWithIdx(i).GetNeighbors() if n.GetIdx() in chain_atoms]
        for i in chain_atoms
    }
    ends = sorted(i for i in chain_atoms if len(adj[i]) <= 1)
    for k, start in enumerate(ends):
        prev = {start: -1}
        todo = [start]
        while todo:
            cur = todo.pop()
            for n in adj[cur]:
                if n not in prev:
                    prev[n] = cur
                    todo.append(n)
        for end in ends[k:]:
            if end not in prev or (end == start and adj[start]):
                continue
            path = [end]
            while path[-1] != start:
                path.append(prev[path[-1]])
            parents.append(_Parent(1, path, f"chain of {len(path)} carbons"))
    if not parents:
        raise Unsupported("no carbon chain or ring to number")
    return parents


@dataclass
class _Scored:
    key: tuple
    locants: dict[int, int]
    alpha_unknown: bool  # an unnamed prefix took part in the alphanumerical rule
    pre_alpha: tuple  # the key up to the alphanumerical rule


def _numberings(parent: _Parent) -> list[list[int]]:
    a = parent.atoms
    if parent.kind == 1:
        return [a, a[::-1]] if len(a) > 1 else [a]
    n = len(a)
    out = []
    for s in range(n):
        out.append([a[(s + k) % n] for k in range(n)])
        out.append([a[(s - k) % n] for k in range(n)])
    return out


def _score(mol, parent, order, groups, principal, stereo) -> _Scored:
    from rdkit import Chem

    loc = {atom: k + 1 for k, atom in enumerate(order)}
    members = set(order)
    n = len(order)

    # (c) principal characteristic groups, and the atoms that belong to suffixes.
    principal_locs: list[int] = []
    suffix_atoms: set[int] = set()
    for atom in order:
        for kind, atoms in groups.get(atom, []):
            if kind == principal:
                principal_locs.append(loc[atom])
                suffix_atoms |= atoms
        if parent.kind == 0:  # -carboxylic acid, -carbonitrile, ... on a ring atom
            for nb in mol.GetAtomWithIdx(atom).GetNeighbors():
                j = nb.GetIdx()
                if j in members:
                    continue
                for kind, atoms in groups.get(j, []):
                    if kind == principal and kind in CARBON_GROUPS:
                        principal_locs.append(loc[atom])
                        suffix_atoms |= atoms | {j}

    # (d), (e) multiple bonds of the parent (none counted for aromatic rings).
    multiple, doubles = [], []
    pairs = list(zip(order, order[1:], strict=False))
    if parent.kind == 0:
        pairs.append((order[-1], order[0]))
    for u, v in pairs:
        b = mol.GetBondBetweenAtoms(u, v)
        if b is None or b.GetIsAromatic():
            continue
        if b.GetBondType() in (Chem.BondType.DOUBLE, Chem.BondType.TRIPLE):
            low = n if {loc[u], loc[v]} == {1, n} and n > 2 else min(loc[u], loc[v])
            multiple.append(low)
            if b.GetBondType() == Chem.BondType.DOUBLE:
                doubles.append(low)

    # (f), (g) prefixes: every branch on the parent that is not part of a suffix.
    prefixes: list[tuple[int, str | None]] = []
    for atom in order:
        for nb in mol.GetAtomWithIdx(atom).GetNeighbors():
            j = nb.GetIdx()
            if j in members or j in suffix_atoms:
                continue
            seen, todo = {j}, [j]
            while todo:
                for m in mol.GetAtomWithIdx(todo.pop()).GetNeighbors():
                    k = m.GetIdx()
                    if k not in seen and k not in members:
                        seen.add(k)
                        todo.append(k)
            prefixes.append((loc[atom], _prefix_name(mol, atom, seen)))
    names = sorted({name or "" for _, name in prefixes}, key=lambda s: (_alpha_key(s), s))
    alpha = tuple(tuple(sorted(lc for lc, nm in prefixes if (nm or "") == name)) for name in names)

    # P-31.1.4.3.4: Z before E, R before S, r before s.
    stereo_key = tuple(
        tuple(sorted(_stereo_locant(atoms, loc, n) for atoms, d in stereo if d == want))
        for want in ("Z", "R", "r")
    )
    pre_alpha = (
        -len(principal_locs),
        parent.kind,
        -n,
        -len(multiple),
        -len(doubles),
        tuple(sorted(principal_locs)),
        tuple(sorted(multiple)),
        tuple(sorted(doubles)),
        -len(prefixes),
        tuple(sorted(lc for lc, _ in prefixes)),
    )
    return _Scored(
        key=(*pre_alpha, alpha, stereo_key),
        locants=loc,
        alpha_unknown=any(name is None for _, name in prefixes) and len(names) > 1,
        pre_alpha=pre_alpha,
    )


def _stereo_locant(atoms: tuple[int, ...], loc: dict[int, int], n: int) -> int:
    if any(a not in loc for a in atoms):
        return 10**6  # not on this parent; such a parent is rejected later
    if len(atoms) == 1:
        return loc[atoms[0]]
    a, b = loc[atoms[0]], loc[atoms[1]]
    return n if {a, b} == {1, n} and n > 2 else min(a, b)


def stereo_elements(mol) -> list[tuple[tuple[int, ...], str]]:
    """CIP stereo elements from RDKit's new CIP labeler: ((atom,), 'R') for
    centers and ((atom1, atom2), 'E') for double bonds."""
    from rdkit.Chem import rdCIPLabeler

    rdCIPLabeler.AssignCIPLabels(mol)
    out: list[tuple[tuple[int, ...], str]] = [
        ((a.GetIdx(),), a.GetProp("_CIPCode")) for a in mol.GetAtoms() if a.HasProp("_CIPCode")
    ]
    for b in mol.GetBonds():
        if b.HasProp("_CIPCode"):
            out.append(((b.GetBeginAtomIdx(), b.GetEndAtomIdx()), b.GetProp("_CIPCode")))
    return out


def iupac_numbering(mol, stereo: list[tuple[tuple[int, ...], str]] | None = None) -> Numbering:
    """Parent and IUPAC locants for a molecule (no explicit hydrogens).

    Raises Unsupported if the structure is outside the supported scope, or if a
    stereo element does not lie on the parent chain or ring.
    """
    if stereo is None:
        stereo = stereo_elements(mol)
    groups = _groups(mol)
    kinds = {kind for found in groups.values() for kind, _ in found}
    principal = next((k for k in SENIORITY if k in kinds), None)

    scored = [
        (_score(mol, parent, order, groups, principal, stereo), parent)
        for parent in _parents(mol)
        for order in _numberings(parent)
    ]
    best, best_parent = min(scored, key=lambda sp: sp[0].key)
    # Did the alphanumerical rule decide? Then every prefix name must be known.
    alpha_decided = any(
        s.pre_alpha == best.pre_alpha and s.key[-2] != best.key[-2] for s, _ in scored
    )
    if alpha_decided and best.alpha_unknown:
        raise Unsupported("the numbering depends on a substituent name that is not supported")
    for atoms, _ in stereo:
        if any(a not in best.locants for a in atoms):
            raise Unsupported(
                "a stereocenter lies in a substituent, not on the parent chain or ring"
            )
    if best_parent.kind == 1:
        name = f"{len(best_parent.atoms)}-carbon chain"
    else:
        name = best_parent.name
    return Numbering(parent=name, locants=best.locants)


def descriptor_text(
    stereo: list[tuple[tuple[int, ...], str]], locants: dict[int, int] | None
) -> str:
    """'(2R,3s,4S)' with IUPAC locants. Double bonds take the lower locant of their
    two atoms: '(2E,4R)'. Without locants, atom numbers (from 1) are written out so
    they cannot be mistaken for locants: 'atom 3 S, atom 5 R'."""
    if not stereo:
        return ""
    if locants is None:
        items = sorted((min(atoms) + 1, d) for atoms, d in stereo)
        return ", ".join(f"atom {k} {d}" for k, d in items)
    n = len(locants)
    items = sorted((_stereo_locant(atoms, locants, n), d) for atoms, d in stereo)
    return "(" + ",".join(f"{k}{d}" for k, d in items) + ")"
