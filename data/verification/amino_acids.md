# Amino-acid data verification report

Built by `scripts/build_amino_acids.py` from `data/sources/aa/`. Do not edit by hand.

Sources retrieved: ccd 2026-11-26, pubchem 2026-11-26, chebi 2026-11-26, expasy_kd 2026-11-26, ncbi_gc 2026-11-26.

## Structures

Each structure is the same molecule (standard InChIKey) in the curated SMILES, the CCD InChIKey, the molecule rebuilt from the CCD bonds and **ideal 3D coordinates** (stereo from 3D), PubChem and ChEBI. CIP labels are computed by RDKit from the SMILES and from the CCD 3D model and must agree. Any difference stops the build. CCD stores Lys, His and Arg with a protonated side chain (+1); for these the InChIKey protonation character (last letter) is ignored.

| 1 | 3 | Formula | InChIKey | Structure | Stereo (CIP) | Kyte–Doolittle | Codons |
|---|---|---|---|---|---|---|---|
| G | Gly | C2H5NO2 | `DHMQDGOQFOQNFH-UHFFFAOYSA-N` | ✓ | achiral | -0.4 | 4 |
| A | Ala | C3H7NO2 | `QNAYBMKLOCPYGJ-REOHCLBHSA-N` | ✓ | (2S) | 1.8 | 4 |
| P | Pro | C5H9NO2 | `ONIBWKKTOPOVIA-BYPYZUCNSA-N` | ✓ | (2S) | -1.6 | 4 |
| V | Val | C5H11NO2 | `KZSNJWFQEVHDMF-BYPYZUCNSA-N` | ✓ | (2S) | 4.2 | 4 |
| L | Leu | C6H13NO2 | `ROHFNLRQFUQHCH-YFKPBYRVSA-N` | ✓ | (2S) | 3.8 | 6 |
| I | Ile | C6H13NO2 | `AGPKZVBTJJNPAG-WHFBIAKZSA-N` | ✓ | (2S,3S) | 4.5 | 3 |
| M | Met | C5H11NO2S | `FFEARJCKVFRZRR-BYPYZUCNSA-N` | ✓ | (2S) | 1.9 | 1 |
| F | Phe | C9H11NO2 | `COLNVLDHVKWLRT-QMMMGPOBSA-N` | ✓ | (2S) | 2.8 | 2 |
| Y | Tyr | C9H11NO3 | `OUYCCCASQSFEME-QMMMGPOBSA-N` | ✓ | (2S) | -1.3 | 2 |
| W | Trp | C11H12N2O2 | `QIVBCDIJIAJPQS-VIFPVBQESA-N` | ✓ | (2S) | -0.9 | 1 |
| S | Ser | C3H7NO3 | `MTCFGRXMJLQNBG-REOHCLBHSA-N` | ✓ | (2S) | -0.8 | 6 |
| T | Thr | C4H9NO3 | `AYFVYJQAPQTCCC-GBXIJSLDSA-N` | ✓ | (2S,3R) | -0.7 | 4 |
| C | Cys | C3H7NO2S | `XUJNEKJLAYXESH-REOHCLBHSA-N` | ✓ | (2R) | 2.5 | 2 |
| N | Asn | C4H8N2O3 | `DCXYFEDJOCDNAF-REOHCLBHSA-N` | ✓ | (2S) | -3.5 | 2 |
| Q | Gln | C5H10N2O3 | `ZDXPYRJPNDTMRX-VKHMYHEASA-N` | ✓ | (2S) | -3.5 | 2 |
| K | Lys | C6H14N2O2 | `KDXKERNSBIXSRK-YFKPBYRVSA-N` | ✓ | (2S) | -3.9 | 2 |
| H | His | C6H9N3O2 | `HNDVDQJCIGZPNO-YFKPBYRVSA-N` | ✓ | (2S) | -3.2 | 2 |
| R | Arg | C6H14N4O2 | `ODKSFYDXXFIFQN-BYPYZUCNSA-N` | ✓ | (2S) | -4.5 | 6 |
| D | Asp | C4H7NO4 | `CKLJMWTZIZZHCS-REOHCLBHSA-N` | ✓ | (2S) | -3.5 | 2 |
| E | Glu | C5H9NO4 | `WHUUTDBJXJRKMK-VKHMYHEASA-N` | ✓ | (2S) | -3.5 | 2 |
| U | Sec | C3H7NO2Se | `ZKZBPNGNEQAJSX-REOHCLBHSA-N` | ✓ | (2R) | — | 0 |
| O | Pyl | C12H21N3O3 | `ZFOMKMMPBOQKMC-KXUCPTDWSA-N` | ✓ | (2S) + R,R in the side chain | — | 0 |

## Masses

Computed from the formula with element data of the `element` tool: monoisotopic = most abundant isotope (AME2020, verified), average = CIAAW 2024 abridged atomic weights (verified). Residue mass = molecule − H₂O. Compared with PubChem, ChEBI and CCD within 0.0001 u (monoisotopic) and 0.01 g/mol (average). Verified = at least 2 databases agree with the computed value.

| 1 | 3 | Mono (u) | Agreeing | Average (g/mol) | Agreeing | Residue mono | Residue avg |
|---|---|---|---|---|---|---|---|
| G | Gly | 75.032028 | PubChem, ChEBI | 75.067 | PubChem, ChEBI, CCD | 57.021464 | 57.052 |
| A | Ala | 89.047678 | PubChem, ChEBI | 89.094 | PubChem, ChEBI, CCD | 71.037114 | 71.079 |
| P | Pro | 115.063329 | PubChem, ChEBI | 115.132 | PubChem, ChEBI, CCD | 97.052764 | 97.117 |
| V | Val | 117.078979 | PubChem, ChEBI | 117.148 | PubChem, ChEBI, CCD | 99.068414 | 99.133 |
| L | Leu | 131.094629 | PubChem, ChEBI | 131.175 | PubChem, ChEBI, CCD | 113.084064 | 113.160 |
| I | Ile | 131.094629 | PubChem, ChEBI | 131.175 | PubChem, ChEBI, CCD | 113.084064 | 113.160 |
| M | Met | 149.051050 | PubChem, ChEBI | 149.208 | PubChem, ChEBI, CCD | 131.040485 | 131.193 |
| F | Phe | 165.078979 | PubChem, ChEBI | 165.192 | PubChem, ChEBI, CCD | 147.068414 | 147.177 |
| Y | Tyr | 181.073893 | PubChem, ChEBI | 181.191 | PubChem, ChEBI, CCD | 163.063329 | 163.176 |
| W | Trp | 204.089878 | PubChem, ChEBI | 204.229 | PubChem, ChEBI, CCD | 186.079313 | 186.214 |
| S | Ser | 105.042593 | PubChem, ChEBI | 105.093 | PubChem, ChEBI, CCD | 87.032028 | 87.078 |
| T | Thr | 119.058243 | PubChem, ChEBI | 119.120 | PubChem, ChEBI, CCD | 101.047678 | 101.105 |
| C | Cys | 121.019750 | PubChem, ChEBI | 121.154 | PubChem, ChEBI, CCD | 103.009185 | 103.139 |
| N | Asn | 132.053492 | PubChem, ChEBI | 132.119 | PubChem, ChEBI, CCD | 114.042927 | 114.104 |
| Q | Gln | 146.069142 | PubChem, ChEBI | 146.146 | PubChem, ChEBI, CCD | 128.058578 | 128.131 |
| K | Lys | 146.105528 | PubChem, ChEBI | 146.190 | PubChem, ChEBI | 128.094963 | 128.175 |
| H | His | 155.069477 | PubChem, ChEBI | 155.157 | PubChem, ChEBI | 137.058912 | 137.142 |
| R | Arg | 174.111676 | PubChem, ChEBI | 174.204 | PubChem, ChEBI | 156.101111 | 156.189 |
| D | Asp | 133.037508 | PubChem, ChEBI | 133.103 | PubChem, ChEBI, CCD | 115.026943 | 115.088 |
| E | Glu | 147.053158 | PubChem, ChEBI | 147.130 | PubChem, ChEBI, CCD | 129.042593 | 129.115 |
| U | Sec | 168.964200 | PubChem, ChEBI | 168.065 | PubChem | 150.953636 | 150.050 |
| O | Pyl | 255.158292 | PubChem, ChEBI | 255.318 | PubChem, ChEBI, CCD | 237.147727 | 237.303 |

Values found (mono / average):

- G: PubChem 75.032028402 / 75.07; ChEBI 75.03203 / 75.067; CCD — / 75.067
- A: PubChem 89.047678466 / 89.09; ChEBI 89.04768 / 89.094; CCD — / 89.093
- P: PubChem 115.06332853 / 115.13; ChEBI 115.06333 / 115.132; CCD — / 115.13
- V: PubChem 117.078978594 / 117.15; ChEBI 117.07898 / 117.148; CCD — / 117.146
- L: PubChem 131.094628657 / 131.17; ChEBI 131.09463 / 131.175; CCD — / 131.173
- I: PubChem 131.094628657 / 131.17; ChEBI 131.09463 / 131.175; CCD — / 131.173
- M: PubChem 149.05104977 / 149.21; ChEBI 149.05105 / 149.215; CCD — / 149.211
- F: PubChem 165.078978594 / 165.19; ChEBI 165.07898 / 165.192; CCD — / 165.189
- Y: PubChem 181.07389321 / 181.19; ChEBI 181.07389 / 181.191; CCD — / 181.189
- W: PubChem 204.08987763 / 204.22; ChEBI 204.08988 / 204.229; CCD — / 204.225
- S: PubChem 105.042593085 / 105.09; ChEBI 105.04259 / 105.093; CCD — / 105.093
- T: PubChem 119.058243149 / 119.12; ChEBI 119.05824 / 119.12; CCD — / 119.119
- C: PubChem 121.01974964 / 121.16; ChEBI 121.01975 / 121.161; CCD — / 121.158
- N: PubChem 132.05349212 / 132.12; ChEBI 132.05349 / 132.119; CCD — / 132.118
- Q: PubChem 146.06914219 / 146.14; ChEBI 146.06914 / 146.146; CCD — / 146.144
- K: PubChem 146.105527694 / 146.19; ChEBI 146.10553 / 146.19
- H: PubChem 155.069476538 / 155.15; ChEBI 155.06948 / 155.157
- R: PubChem 174.1116757 / 174.2; ChEBI 174.11168 / 174.204
- D: PubChem 133.0375077 / 133.1; ChEBI 133.03751 / 133.103; CCD — / 133.103
- E: PubChem 147.05315777 / 147.13; ChEBI 147.05316 / 147.13; CCD — / 147.129
- U: PubChem 168.9642 / 168.06; ChEBI 168.9642 / 168.054; CCD — / 168.053
- O: PubChem 255.15829154 / 255.31; ChEBI 255.15829 / 255.318; CCD — / 255.313

## Hydropathy (Kyte–Doolittle)

Transcribed from the original paper and equal to the ExPASy ProtScale copy for all 20. Shown as ≈ (2 references): the paper defines the scale; a third copy is still to add.

## Codons

From NCBI translation table 1 (the standard code, a definition). Every codon maps to one of the 20 amino acids or a stop; Sec (UGA) and Pyl (UAG) reuse stop codons in special contexts.

## pKa and pI — provisional

pKa values are from one textbook table (Lehninger, 7th ed., Table 3-1) and are **not** cross-checked yet; pKa values differ between sources by 0.1–0.5 units (plan 006 Q4). pI is computed from these pKa values (zero net charge, Henderson–Hasselbalch).

## References

- **jcbn1984**: IUPAC-IUB Joint Commission on Biochemical Nomenclature (JCBN), Nomenclature and Symbolism for Amino Acids and Peptides (Recommendations 1983), Pure Appl. Chem. 1984, 56, 595–624.
- **ccd**: wwPDB Chemical Component Dictionary (CCD), J. D. Westbrook et al., Bioinformatics 2015, 31, 1274–1278; files.rcsb.org/ligands.
- **pubchem**: PubChem (NCBI), S. Kim et al., Nucleic Acids Res. 2025, 53, D1516–D1525; compound records by CID.
- **chebi**: ChEBI (EMBL-EBI), A. Malik et al., Nucleic Acids Res. 2026; compound records by ChEBI ID.
- **kd1982**: J. Kyte, R. F. Doolittle, A simple method for displaying the hydropathic character of a protein, J. Mol. Biol. 1982, 157, 105–132 (Table 2).
- **expasy**: ExPASy ProtScale, Amino acid scale: Hydropathicity (Kyte & Doolittle), SIB Swiss Institute of Bioinformatics, web.expasy.org/protscale.
- **ncbi_gc**: NCBI, The Genetic Codes, Table 1 (Standard Code), www.ncbi.nlm.nih.gov/Taxonomy/Utils/wprintgc.cgi; gc.prt.
- **lehninger7**: D. L. Nelson, M. M. Cox, Lehninger Principles of Biochemistry, 7th ed., W. H. Freeman, 2017, Table 3-1 and Fig. 3-5.
