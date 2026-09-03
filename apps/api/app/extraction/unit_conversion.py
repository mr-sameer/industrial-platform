"""
Minimum deterministic unit handling for industrial pump/motor
datasheets. A small, hand-reviewed allow-list only — five conversion
pairs, chosen because each is a single, unambiguous, physically-defined
constant. Adding a unit pair here is a deliberate, reviewed decision,
never a generic "parse anything that looks like a unit" engine.

HP is deliberately excluded from `_CONVERTERS` — not an oversight.
Mechanical HP (~0.7457 kW), metric HP/PS (~0.7355 kW), and electrical
HP (~0.746 kW) are three different real constants, and a real
datasheet rarely states which one it means. Auto-converting would be a
guess dressed up as a fact, so HP is listed in `UNSAFE_UNITS`: it is a
recognized unit (comparisons against it never get rejected as
"unrecognized"), but it is never the source or target of an automatic
conversion, and any candidate that needs one is left unresolved
(app.extraction.validation.resolve_unit's caller then caps confidence
and never rejects — see that function's own docstring).

rpm has no conversion partner in this domain (rad/s is a scientific
unit, not one printed on industrial nameplates) — it is compared as an
exact token, like any unit with no configured conversion.
"""

from collections.abc import Callable

# unit -> physical quantity family. Two units convert into each other
# only if they share a family AND a factor is registered in
# `_CONVERTERS` below — sharing a family alone (e.g. HP and kW, both
# "power") is not sufficient, see UNSAFE_UNITS.
UNIT_FAMILY: dict[str, str] = {
    "kW": "power",
    "W": "power",
    "HP": "power",
    "m³/h": "flow",
    "L/min": "flow",
    "bar": "pressure",
    "psi": "pressure",
    "mm": "length",
    "m": "length",
    "°C": "temperature",
    "°F": "temperature",
    "rpm": "speed",
}

KNOWN_UNITS: frozenset[str] = frozenset(UNIT_FAMILY)

# Same-family units that are never auto-converted, by deliberate design
# decision — see this module's own docstring.
UNSAFE_UNITS: frozenset[str] = frozenset({"HP"})


def _linear(factor: float) -> Callable[[float], float]:
    return lambda value: value * factor


# Each conversion is a single, physically-defined constant — never a
# derived/approximate one. Power (kW<->W) and length (mm<->m) are exact
# decimal-shift definitions; flow (m³/h<->L/min) is an exact rational
# conversion (1 m³/h = 1000/60 L/min); pressure (bar<->psi) uses the
# internationally defined bar (1 bar = 14.5038 psi); temperature is the
# one non-linear (affine) pair, handled separately below.
_CONVERTERS: dict[tuple[str, str], Callable[[float], float]] = {
    ("kW", "W"): _linear(1000.0),
    ("W", "kW"): _linear(0.001),
    ("m³/h", "L/min"): _linear(1000.0 / 60.0),
    ("L/min", "m³/h"): _linear(60.0 / 1000.0),
    ("bar", "psi"): _linear(14.5038),
    ("psi", "bar"): _linear(1.0 / 14.5038),
    ("mm", "m"): _linear(0.001),
    ("m", "mm"): _linear(1000.0),
    ("°C", "°F"): lambda value: value * 9.0 / 5.0 + 32.0,
    ("°F", "°C"): lambda value: (value - 32.0) * 5.0 / 9.0,
}


class UnitResolution:
    """
    The outcome of comparing one observed unit against a specification's
    declared unit.

    unit_resolved  — True only when the observed value can be trusted
                      as directly comparable to the specification's own
                      unit: either they matched exactly, or a factor in
                      `_CONVERTERS` proved the conversion. False means
                      "usable, but not provably so" (see `convert`).
    reject_reason  — set only when the candidate must be rejected
                      outright (an unrecognized token, or two units
                      from different physical families) — never set
                      merely because a safe conversion doesn't exist
                      (that's the HP case: unit_resolved=False,
                      reject_reason=None).
    convert        — a function from a value in the observed unit to
                      the specification's unit, present only when
                      unit_resolved is True and an actual conversion
                      (not a same-unit no-op) was needed.
    """

    __slots__ = ("unit_resolved", "reject_reason", "convert")

    def __init__(
        self,
        *,
        unit_resolved: bool,
        reject_reason: str | None,
        convert: Callable[[float], float] | None,
    ) -> None:
        self.unit_resolved = unit_resolved
        self.reject_reason = reject_reason
        self.convert = convert


def resolve_unit(observed_unit: str | None, specification_unit: str | None) -> UnitResolution:
    """
    Deterministic unit comparison — see this module's docstring for the
    conversion table and UnitResolution's docstring for what each
    outcome means. Never guesses: every branch is a fixed rule over
    `UNIT_FAMILY`/`_CONVERTERS`/`UNSAFE_UNITS`, not a heuristic.
    """
    if observed_unit is None:
        # No unit token found in the source text for this reading. If
        # the specification expects none either, that's a clean match;
        # if it expects one, the number may still be correct (the unit
        # may be implied elsewhere, e.g. a table header) — left
        # unresolved rather than rejected, so real data isn't discarded
        # on a formatting technicality.
        return UnitResolution(
            unit_resolved=specification_unit is None, reject_reason=None, convert=None
        )
    if specification_unit is None:
        # The specification declares no unit, but the document printed
        # one anyway — the number itself may still be right.
        return UnitResolution(unit_resolved=False, reject_reason=None, convert=None)
    if observed_unit == specification_unit:
        return UnitResolution(unit_resolved=True, reject_reason=None, convert=None)
    if observed_unit not in KNOWN_UNITS or specification_unit not in KNOWN_UNITS:
        return UnitResolution(unit_resolved=False, reject_reason="unrecognized_unit", convert=None)
    if UNIT_FAMILY[observed_unit] != UNIT_FAMILY[specification_unit]:
        return UnitResolution(unit_resolved=False, reject_reason="incompatible_unit", convert=None)
    if observed_unit in UNSAFE_UNITS or specification_unit in UNSAFE_UNITS:
        # Same family (e.g. HP vs kW) but deliberately never converted.
        return UnitResolution(unit_resolved=False, reject_reason=None, convert=None)
    converter = _CONVERTERS.get((observed_unit, specification_unit))
    if converter is None:
        # Same family, both "safe" units, but no factor registered —
        # shouldn't occur given the table above, but fails closed
        # rather than guessing if the table is ever incomplete.
        return UnitResolution(unit_resolved=False, reject_reason="incompatible_unit", convert=None)
    return UnitResolution(unit_resolved=True, reject_reason=None, convert=converter)


__all__ = ["KNOWN_UNITS", "UNIT_FAMILY", "UNSAFE_UNITS", "UnitResolution", "resolve_unit"]
