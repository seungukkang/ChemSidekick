"""Energetics: free energies ↔ rate constants, half-lives, equilibrium constants,
populations, and selectivities.

All energies here are molar, in J/mol, and temperatures in K. Tools convert
user units with core/units.py before calling these functions. Constants come
from core/data/units.toml (one source for the whole project).

    Eyring:        k = κ (k_B T / h) · exp(−ΔG‡ / RT)
    Equilibrium:   K = exp(−ΔG / RT)
    Boltzmann:     pᵢ = gᵢ exp(−Eᵢ / RT) / Σ gⱼ exp(−Eⱼ / RT)
    Diffusion:     k_diff = 8RT / (3η)        (Smoluchowski + Stokes–Einstein)
    Combined:      1/k_obs = 1/k_act + 1/k_diff
"""

import math
from collections.abc import Sequence

from chemsidekick.core.units import load


def _c(key: str) -> float:
    return load().constants[key].value


def gas_constant() -> float:
    """R = N_A · k_B in J/(mol K)."""
    return _c("NA") * _c("kB")


def rt(temperature: float) -> float:
    """RT in J/mol."""
    return gas_constant() * temperature


# ---------------------------------------------------------------------------
# Rates (Eyring)
# ---------------------------------------------------------------------------


def eyring_k(dg_act: float, temperature: float, kappa: float = 1.0) -> float:
    """Rate constant from ΔG‡ (J/mol): s⁻¹ for unimolecular steps, M⁻¹ s⁻¹ for
    bimolecular steps with a 1 M standard state."""
    return kappa * _c("kB") * temperature / _c("h") * math.exp(-dg_act / rt(temperature))


def dg_act_from_k(k: float, temperature: float, kappa: float = 1.0) -> float:
    """ΔG‡ (J/mol) from a rate constant (inverse of eyring_k)."""
    if k <= 0:
        raise ValueError("A rate constant must be positive.")
    return -rt(temperature) * math.log(k * _c("h") / (kappa * _c("kB") * temperature))


def half_life(k: float) -> float:
    """t½ = ln 2 / k (first order, or pseudo-first order with k′ = k[B])."""
    return math.log(2) / k


def time_to_conversion(k: float, percent: float) -> float:
    """Time (s) to reach `percent` conversion in a first-order reaction."""
    if not 0 < percent < 100:
        raise ValueError("Conversion must be between 0 and 100 %.")
    return -math.log(1 - percent / 100) / k


def k_from_half_life(t_half: float) -> float:
    if t_half <= 0:
        raise ValueError("A half-life must be positive.")
    return math.log(2) / t_half


def temperature_for_half_life(
    dg_act: float, t_half: float, kappa: float = 1.0, low: float = 1.0, high: float = 5000.0
) -> float:
    """The temperature (K) at which a barrier ΔG‡ (J/mol, taken as independent of
    temperature) gives the half-life t_half (s). Solved by bisection: t½ falls
    monotonically with temperature."""
    if t_half <= 0:
        raise ValueError("A half-life must be positive.")

    def too_slow(t: float) -> bool:
        k = eyring_k(dg_act, t, kappa)
        return k == 0 or half_life(k) > t_half  # k underflows to 0 when far too cold

    if not too_slow(low) or too_slow(high):
        raise ValueError(f"No temperature between {low:g} and {high:g} K gives this half-life.")
    for _ in range(200):
        mid = (low + high) / 2
        if too_slow(mid):
            low = mid
        else:
            high = mid
        if high - low < 1e-9:
            break
    return (low + high) / 2


def wigner_kappa(imaginary_wavenumber: float, temperature: float) -> float:
    """Wigner tunneling correction κ = 1 + (hcν / k_B T)² / 24, with ν the
    magnitude of the imaginary frequency in cm⁻¹."""
    u = _c("h") * _c("c") * 100 * abs(imaginary_wavenumber) / (_c("kB") * temperature)
    return 1 + u * u / 24


# ---------------------------------------------------------------------------
# Diffusion
# ---------------------------------------------------------------------------


def k_diffusion(temperature: float, viscosity: float) -> float:
    """Diffusion-limited bimolecular rate constant (M⁻¹ s⁻¹) for two neutral
    spheres of equal size: 8RT / (3η), η in Pa s."""
    if viscosity <= 0:
        raise ValueError("Viscosity must be positive.")
    return 8 * rt(temperature) / (3 * viscosity) * 1000  # m³ mol⁻¹ s⁻¹ -> M⁻¹ s⁻¹


def k_observed(k_act: float, k_diff: float) -> float:
    """Activation and diffusion in series: 1/k_obs = 1/k_act + 1/k_diff."""
    return k_act * k_diff / (k_act + k_diff)


# ---------------------------------------------------------------------------
# Equilibria and populations
# ---------------------------------------------------------------------------


def k_eq(dg: float, temperature: float) -> float:
    """Equilibrium constant from ΔG (J/mol)."""
    return math.exp(-dg / rt(temperature))


def dg_from_k_eq(k: float, temperature: float) -> float:
    if k <= 0:
        raise ValueError("An equilibrium constant must be positive.")
    return -rt(temperature) * math.log(k)


def populations(
    energies: Sequence[float], temperature: float, degeneracy: Sequence[float] | None = None
) -> list[float]:
    """Boltzmann populations (fractions summing to 1) of states with energies
    in J/mol. The lowest energy is taken as zero, so absolute energies (e.g. in
    hartree, converted) do not overflow."""
    if not energies:
        return []
    g = list(degeneracy) if degeneracy is not None else [1.0] * len(energies)
    if len(g) != len(energies):
        raise ValueError("One degeneracy per energy is needed.")
    if any(x <= 0 for x in g):
        raise ValueError("Degeneracies must be positive.")
    low = min(energies)
    weights = [
        gi * math.exp(-(e - low) / rt(temperature)) for e, gi in zip(energies, g, strict=True)
    ]
    total = sum(weights)
    return [w / total for w in weights]


def standard_state_shift(temperature: float, delta_n: int = 1) -> float:
    """Free-energy change (J/mol) when moving from a 1 atm (gas) to a 1 M
    standard state, for a step that changes the number of molecules by
    `delta_n` (reactants − products, e.g. 1 for A + B → TS):
    Δn · RT · ln(V_m / 1 L), V_m = RT / p° the molar volume at 1 atm."""
    molar_volume_litres = rt(temperature) / _c("atm") * 1000
    return delta_n * rt(temperature) * math.log(molar_volume_litres)


# ---------------------------------------------------------------------------
# Selectivity
# ---------------------------------------------------------------------------


def ratio_from_ddg(ddg: float, temperature: float) -> float:
    """k₁/k₂ (or K-ratio) = exp(ΔΔG / RT), ΔΔG in J/mol."""
    return math.exp(ddg / rt(temperature))


def ddg_from_ratio(ratio: float, temperature: float) -> float:
    if ratio <= 0:
        raise ValueError("A ratio must be positive.")
    return rt(temperature) * math.log(ratio)


def ee_to_ratio(ee_percent: float) -> float:
    """ee 90 % -> 95:5 = 19."""
    if not 0 <= ee_percent < 100:
        raise ValueError("ee must be between 0 and 100 %.")
    return (100 + ee_percent) / (100 - ee_percent)


def ratio_to_ee(ratio: float) -> float:
    return (ratio - 1) / (ratio + 1) * 100
