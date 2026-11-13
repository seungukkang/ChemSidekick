# Unit constants verification report

Built by `scripts/build_units_report.py` from `src/chemsidekick/core/data/units.toml`. Do not edit by hand.

A measured constant is **verified** when at least 3 references agree with the adopted value within its standard uncertainty. Conversions that use only defined constants are exact.

## Measured constants

| Constant | Adopted value | Standard uncertainty | Unit | Status |
|---|---|---|---|---|
| Hartree energy (`Eh`) | 4.359744722206e-18 | 4.8 × 10⁻³⁰ | J | verified |
| Bohr radius (`a0`) | 5.29177210544e-11 | 8.2 × 10⁻²¹ | m | verified |
| vacuum electric permittivity (`eps0`) | 8.8541878188e-12 | 1.4 × 10⁻²¹ | F/m | verified |

### Values found in each reference

**Hartree energy**

| Reference | Value | Agrees |
|---|---|---|
| nist | 4.359744722206e-18 | yes |
| codata2022 | 4.359744722206e-18 | yes |
| pdg2025 | 4.3597447222058135e-18 | yes |

**Bohr radius**

| Reference | Value | Agrees |
|---|---|---|
| nist | 5.29177210544e-11 | yes |
| codata2022 | 5.29177210544e-11 | yes |
| pdg2025 | 5.29177210544e-11 | yes |

**vacuum electric permittivity**

| Reference | Value | Agrees |
|---|---|---|
| nist | 8.8541878188e-12 | yes |
| codata2022 | 8.8541878188e-12 | yes |
| pdg2025 | 8.8541878188e-12 | yes |

## Defined constants

| Constant | Value | Unit | Source |
|---|---|---|---|
| Planck constant (`h`) | 6.62607015e-34 | J s | SI Brochure, 9th ed. (BIPM, 2019): defining constant |
| elementary charge (`e`) | 1.602176634e-19 | C | SI Brochure, 9th ed. (BIPM, 2019): defining constant |
| Boltzmann constant (`kB`) | 1.380649e-23 | J/K | SI Brochure, 9th ed. (BIPM, 2019): defining constant |
| Avogadro constant (`NA`) | 6.02214076e+23 | 1/mol | SI Brochure, 9th ed. (BIPM, 2019): defining constant |
| speed of light in vacuum (`c`) | 299792458.0 | m/s | SI Brochure, 9th ed. (BIPM, 2019): defining constant |
| thermochemical calorie (`cal`) | 4.184 | J | NIST SP 811 (2008), Appendix B.8: calorie (thermochemical) = 4.184 J |
| standard atmosphere (`atm`) | 101325.0 | Pa | IUPAC Green Book, 3rd ed. (2007), sec. 7.2; NIST SP 811 (2008), Appendix B.8 |
| conventional millimetre of mercury (`mmHg`) | 133.322387415 | Pa | IUPAC Green Book, 3rd ed. (2007), sec. 7.2: mmHg = 13.5951 × 980.665 × 10⁻² Pa |
| pound-force per square inch (`psi`) | 6894.757293168361 | Pa | NIST SP 811 (2008), Appendix B.8 (lb = 0.45359237 kg, gₙ = 9.80665 m/s², in = 0.0254 m, all exact) |

## References

- `nist`: NIST CODATA 2022 values, physics.nist.gov/cuu/Constants (retrieved 2026-11-13)
- `codata2022`: P. J. Mohr, D. B. Newell, B. N. Taylor, E. Tiesinga, CODATA Recommended Values of the Fundamental Physical Constants: 2022, Rev. Mod. Phys. 97, 025002 (2025)
- `pdg2025`: Particle Data Group, Review of Particle Physics 2025, Physical Constants table (based on CODATA 2022)
