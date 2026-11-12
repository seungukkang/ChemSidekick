# Solvent viscosity verification report

Built by `scripts/build_solvents_report.py` from `src/chemsidekick/core/data/solvents.toml`. Do not edit by hand.

Viscosities at 298.15 K (25 °C), 1 atm, in mPa s. A solvent is **verified** when at least 3 references agree with the adopted value within 2%. Used for diffusion-limited rate constants (energy profile, ENE-01).

| Solvent | Adopted (mPa s) | From | Agreeing | Status |
|---|---|---|---|---|
| Water | 0.890022 | nist | 3 of 3 | verified |
| Methanol | 0.543712 | nist | 4 of 4 | verified |
| Toluene | 0.552198 | nist | 3 of 3 | verified |
| Benzene | 0.603006 | nist | 3 of 3 | verified |

## Values found in each reference

**Water**

| Reference | mPa s | Agrees |
|---|---|---|
| nist | 0.890022 | yes |
| hsdb | 0.8949 | yes |
| crc85 | 0.89 | yes |

**Methanol**

| Reference | mPa s | Agrees |
|---|---|---|
| nist | 0.543712 | yes |
| hsdb | 0.544 | yes |
| crc85 | 0.54 | yes |
| icsc | 0.544 | yes |

**Toluene**

| Reference | mPa s | Agrees |
|---|---|---|
| nist | 0.552198 | yes |
| hsdb | 0.56 | yes |
| crc85 | 0.56 | yes |

**Benzene**

| Reference | mPa s | Agrees |
|---|---|---|
| nist | 0.603006 | yes |
| hsdb | 0.604 | yes |
| crc85 | 0.6 | yes |

## Not listed

Fewer than three references with a 25 °C value were found on 2026-11-13: acetonitrile, DMSO, THF, dichloromethane, acetone (CRC only); ethanol and DMF (HSDB and CRC only). Type their viscosity instead.

## References

- `nist`: NIST Chemistry WebBook, SRD 69, Thermophysical Properties of Fluid Systems, 298.15 K and 0.101325 MPa (retrieved 2026-11-13)
- `hsdb`: Hazardous Substances Data Bank (HSDB), via PubChem, value at 25 °C (retrieved 2026-11-13)
- `crc85`: CRC Handbook of Chemistry and Physics, 85th ed. (2004), viscosity at 25 °C, as tabulated by Diversified Enterprises (accudynetest.com/visc_table.html, retrieved 2026-11-13)
- `icsc`: ILO-WHO International Chemical Safety Cards, via PubChem (retrieved 2026-11-13)
