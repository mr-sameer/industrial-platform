"""
2-level regular-grid table geometry — deterministic pitch+origin
fitting and position-based cell assignment. Pure functions only: no
database, no OCR execution, no I/O. Consumes word bounding boxes
already produced by app.services.tesseract_ocr_service.get_word_boxes;
produces an internal representation (never persisted as new database
tables — see app.services.table_extraction_service) for turning one
table row into a ProductAttributeEvidence row via the EXISTING,
unmodified
app.services.product_attribute_evidence_service.create_ocr_derived_attribute_evidence.

Every rule enforced here was established by three consecutive,
approved technology-validation spikes against the real CRI 2024
catalogue, not invented in the abstract:

- Absolute x-position assignment ONLY, never ordinal sequence. An
  ordinal read of this exact document silently mis-mapped a real cell
  during discovery — "38.5" is discharge=0.3, not discharge=0.1, which
  only position-based comparison against the header's own observed
  tokens caught. See assign_row_to_grid.

- Origin must be fit via robust multi-row residue consensus, never
  min(x) of a single row. A single-row/motor-power-polluted origin
  produced a ~34px systematic misalignment during discovery, fully
  resolved by the residue-consensus method used in fit_origin_phase.

- Sub-harmonic pitches must be explicitly out-competed via occupancy
  fraction, never by picking the smallest residual. A false half-pitch
  candidate achieves HIGHER raw coverage than the true pitch (a finer
  grid is trivially easier to be "near") and must never win on
  coverage alone — see score_grid_candidate's occupancy_fraction term
  and the SCORE_WEIGHT_* constants below.

Scope, deliberately: 2-level regular-grid tables only (e.g. the JTS/
CTSS/ROYALE-PRIDE performance-chart archetype). This module does not
attempt table-region detection (separating one table's rows from
another, or from surrounding prose) or header-row/data-row
classification — those remain the caller's responsibility in V1 (see
that module's own docstring for why this line is drawn here). It does
not attempt 3-level nested-header tables (the MTC/MVC dimension-table
archetype), which remain blocked far upstream by near-total OCR text
recognition loss that no geometric technique can repair.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

# ---------------------------------------------------------------------
# Named constants — grid quality gates and scoring weights. Every
# threshold here is a config value, not a magic number scattered
# through the algorithm.
# ---------------------------------------------------------------------

#: Sub-harmonic divisors tested as explicit competitors against every
#: base candidate pitch (see generate_candidate_pitches) — the
#: algorithm must be given the chance to pick pitch/2 or pitch/3
#: wrongly, so that occupancy-based scoring can be shown to correctly
#: reject them, rather than simply never considering them.
SUBHARMONIC_DIVISORS: tuple[int, ...] = (2, 3)

#: Fraction of the candidate pitch used as the position-assignment
#: tolerance (a token further than this from every grid line is
#: unassigned, never force-matched).
ASSIGNMENT_TOLERANCE_FRACTION = 0.15

#: Composite score weights (must sum to <= 1.0 with the residual
#: penalty). Coverage and occupancy are weighted equally and heaviest —
#: occupancy is what defeats sub-harmonics; coverage alone would not
#: (see this module's own docstring).
SCORE_WEIGHT_COVERAGE = 0.35
SCORE_WEIGHT_OCCUPANCY = 0.35
SCORE_WEIGHT_CROSS_ROW = 0.20
SCORE_WEIGHT_RESIDUAL_PENALTY = 0.10

# ---- grid acceptance gates (fail-closed thresholds) ----
MIN_WINNER_SCORE = 0.55
MIN_WINNER_MARGIN = 0.05
MIN_CROSS_ROW_CONSISTENCY = 0.4
MAX_NORMALIZED_RESIDUAL = 0.15
MIN_POPULATED_ROWS = 2

# ---- header semantic-resolution gate ----
#: Fraction of a table's occupied grid columns that must have an
#: independently-recovered (from real OCR text, never guessed) numeric
#: header token within tolerance before ANY semantic column label is
#: attached. Below this, semantics are reported unresolved — see
#: resolve_header_semantics. This is what makes the CTSS case
#: (grid geometry recoverable, header text never OCR'd) fail closed
#: rather than falling back to ordinal-position guessing.
MIN_HEADER_COVERAGE_FOR_SEMANTICS = 0.5

_NUMERIC_TOKEN_RE = re.compile(r"^\|?\[?(-?\d+\.?\d*)\]?\|?$")
_DASH_TOKEN_RE = re.compile(r"^-+$")
_MODEL_TOKEN_RE = re.compile(r"^[A-Z]{2,6}-\d{1,3}(?:/\d{1,3}[A-Z]{0,2})?$")

__all__ = [
    "ASSIGNMENT_TOLERANCE_FRACTION",
    "MAX_NORMALIZED_RESIDUAL",
    "MIN_CROSS_ROW_CONSISTENCY",
    "MIN_HEADER_COVERAGE_FOR_SEMANTICS",
    "MIN_POPULATED_ROWS",
    "MIN_WINNER_MARGIN",
    "MIN_WINNER_SCORE",
    "SUBHARMONIC_DIVISORS",
    "CellAssignment",
    "CellStatus",
    "GridFit",
    "GridQualityError",
    "WordBox",
    "assign_row_to_grid",
    "cluster_words_into_rows",
    "fit_best_grid",
    "fit_origin_phase",
    "generate_candidate_pitches",
    "is_dash_token",
    "is_model_shaped_token",
    "is_numeric_token",
    "resolve_header_semantics",
    "score_grid_candidate",
]


@dataclass(frozen=True)
class WordBox:
    """One OCR word, in the shape app.services.tesseract_ocr_service.get_word_boxes
    produces — x/y are the box's TOP-LEFT corner (matching pytesseract's
    own convention), width/height are the box dimensions."""

    text: str
    x: float
    y: float
    width: float
    height: float
    confidence: int  # Tesseract's native 0-100 scale, unconverted

    @property
    def x_center(self) -> float:
        return self.x + self.width / 2

    @property
    def y_center(self) -> float:
        return self.y + self.height / 2


def is_numeric_token(text: str) -> bool:
    return bool(_NUMERIC_TOKEN_RE.match(text.strip()))


def is_dash_token(text: str) -> bool:
    """A literal '-' (or repeated dashes) — the not-applicable marker
    this document uses, e.g. a 3-phase dimension column for a
    single-phase-only model variant. Deliberately distinct from
    is_numeric_token's own leading-minus-sign handling (a real negative
    number like '-15' still requires digits; a bare dash never does)."""
    return bool(_DASH_TOKEN_RE.match(text.strip()))


def is_model_shaped_token(text: str) -> bool:
    """Content-based shape check for a model-number-looking token
    (e.g. 'JTS-3/11M', 'CTSS-8/15T') — never a lookup against known
    model names. Used only to identify CANDIDATE row-identity tokens;
    see app.services.table_extraction_service for the stricter
    validation (uncertain identity blocks evidence entirely, per the
    approved V1 scope) this shape check alone does not perform."""
    return bool(_MODEL_TOKEN_RE.match(text.strip()))


def cluster_words_into_rows(words: list[WordBox], y_tolerance: float = 10.0) -> list[list[WordBox]]:
    """Simplest deterministic row clustering: sort by vertical center,
    greedily group into the current row if within y_tolerance of its
    running average center, else start a new row. Validated across
    three discovery spikes; not redesigned here."""
    if not words:
        return []
    ordered = sorted(words, key=lambda w: w.y_center)
    rows: list[list[WordBox]] = [[ordered[0]]]
    row_centers = [ordered[0].y_center]
    for w in ordered[1:]:
        if abs(w.y_center - row_centers[-1]) <= y_tolerance:
            rows[-1].append(w)
            row_centers[-1] = sum(x.y_center for x in rows[-1]) / len(rows[-1])
        else:
            rows.append([w])
            row_centers.append(w.y_center)
    for row in rows:
        row.sort(key=lambda w: w.x_center)
    return rows


# ---------------------------------------------------------------------
# Pitch + origin fitting
# ---------------------------------------------------------------------


def generate_candidate_pitches(rows: list[list[WordBox]], top_n: int = 6) -> list[float]:
    """Candidates from OBSERVED spacing only — no assumed/expected
    pitch value anywhere. Explicitly expands every base candidate into
    its own sub-harmonics (pitch/2, pitch/3) as direct competitors, per
    SUBHARMONIC_DIVISORS, so the scoring step (not this generation
    step) is what has to correctly reject them."""
    xs = sorted(w.x_center for row in rows for w in row)
    diffs = [b - a for a, b in zip(xs, xs[1:], strict=False) if b - a > 5]
    if not diffs:
        return []
    bucketed = Counter(round(d / 5) * 5 for d in diffs)
    base_candidates = [float(b) for b, _ in bucketed.most_common(top_n)]
    expanded: set[float] = set()
    for p in base_candidates:
        expanded.add(round(p, 1))
        for divisor in SUBHARMONIC_DIVISORS:
            expanded.add(round(p / divisor, 1))
    return sorted(x for x in expanded if x > 20)


def fit_origin_phase(rows: list[list[WordBox]], pitch: float, bins: int = 60) -> float:
    """Robust circular mode of (x_center mod pitch), pooled across
    EVERY word in EVERY row given — including any unrelated
    column-group (e.g. a motor-power block) that happens to be present.
    Real grid members cluster tightly at one residue; unrelated points
    scatter and are naturally outvoted — no manual block segmentation
    or filtering is performed or required."""
    all_words = [w for row in rows for w in row]
    residues = [w.x_center % pitch for w in all_words]
    if not residues:
        return 0.0
    bin_width = pitch / bins
    hist = Counter(int(r / bin_width) for r in residues)
    best_bin, _count = hist.most_common(1)[0]
    peak_residues = [r for r in residues if int(r / bin_width) == best_bin]
    return sum(peak_residues) / len(peak_residues)


@dataclass(frozen=True)
class GridFit:
    pitch: float
    origin_phase: float
    score: float
    coverage: float
    occupancy_fraction: float
    cross_row_consistency: float
    normalized_residual: float
    grid_lines: list[float] = field(default_factory=list)
    tolerance: float = 0.0
    occupied_indices: frozenset[int] = frozenset()


def score_grid_candidate(rows: list[list[WordBox]], pitch: float, origin_phase: float) -> GridFit:
    """Scores one (pitch, origin) candidate against MULTIPLE rows.
    Coverage and occupancy are weighted equally and heaviest —
    occupancy_fraction (occupied grid lines / total grid lines spanned)
    is the anti-aliasing signal: a false sub-harmonic trivially wins on
    coverage (finer grid, easier to be "near") but needs twice the grid
    lines to explain the same data, half of which sit permanently
    empty — occupancy correctly penalizes that, coverage alone would
    not."""
    all_words = [w for row in rows for w in row]
    if not all_words:
        return GridFit(pitch, origin_phase, 0.0, 0.0, 0.0, 0.0, 1.0)

    min_x = min(w.x_center for w in all_words)
    max_x = max(w.x_center for w in all_words)
    first_line = origin_phase + pitch * ((min_x - origin_phase) // pitch)
    n_lines = int((max_x - first_line) / pitch) + 2
    grid = [first_line + i * pitch for i in range(n_lines)]

    tolerance = pitch * ASSIGNMENT_TOLERANCE_FRACTION
    occupied: set[int] = set()
    residuals: list[float] = []
    assigned = 0
    rows_touching: dict[int, set[int]] = {}
    for row_idx, row in enumerate(rows):
        for w in row:
            distances = [(abs(w.x_center - g), i) for i, g in enumerate(grid)]
            dist, idx = min(distances)
            if dist <= tolerance:
                occupied.add(idx)
                residuals.append(dist)
                assigned += 1
                rows_touching.setdefault(idx, set()).add(row_idx)

    coverage = assigned / len(all_words)
    occupancy_fraction = len(occupied) / len(grid) if grid else 0.0
    avg_residual = sum(residuals) / len(residuals) if residuals else tolerance
    normalized_residual = avg_residual / pitch
    multi_row_lines = sum(1 for s in rows_touching.values() if len(s) > 1)
    cross_row_consistency = multi_row_lines / len(occupied) if occupied else 0.0

    score = (
        coverage * SCORE_WEIGHT_COVERAGE
        + occupancy_fraction * SCORE_WEIGHT_OCCUPANCY
        + cross_row_consistency * SCORE_WEIGHT_CROSS_ROW
        - normalized_residual * SCORE_WEIGHT_RESIDUAL_PENALTY
    )
    return GridFit(
        pitch=pitch,
        origin_phase=origin_phase,
        score=score,
        coverage=coverage,
        occupancy_fraction=occupancy_fraction,
        cross_row_consistency=cross_row_consistency,
        normalized_residual=normalized_residual,
        grid_lines=grid,
        tolerance=tolerance,
        occupied_indices=frozenset(occupied),
    )


class GridQualityError(Exception):
    """Raised by fit_best_grid when no candidate clears the configured
    quality gates (MIN_WINNER_SCORE, MIN_WINNER_MARGIN,
    MIN_CROSS_ROW_CONSISTENCY, MAX_NORMALIZED_RESIDUAL,
    MIN_POPULATED_ROWS). Callers MUST treat this as an unusable/
    ambiguous grid and create no evidence — never fall back to a
    lower-quality candidate silently."""


def fit_best_grid(rows: list[list[WordBox]]) -> GridFit:
    """The full joint pitch+origin fit: generate candidates (incl.
    explicit sub-harmonics), fit origin per candidate via residue
    consensus, score every candidate, and return the winner ONLY if it
    clears every configured quality gate — otherwise raises
    GridQualityError. Deterministic: identical input always produces
    identical output."""
    populated_rows = [r for r in rows if r]
    if len(populated_rows) < MIN_POPULATED_ROWS:
        raise GridQualityError(
            f"Only {len(populated_rows)} populated row(s) given, "
            f"need at least {MIN_POPULATED_ROWS} for multi-row consensus."
        )

    candidates = generate_candidate_pitches(populated_rows)
    if not candidates:
        raise GridQualityError("No candidate pitches could be generated from the observed spacing.")

    fits: list[GridFit] = []
    for pitch in candidates:
        origin_phase = fit_origin_phase(populated_rows, pitch)
        fits.append(score_grid_candidate(populated_rows, pitch, origin_phase))
    fits.sort(key=lambda f: -f.score)

    winner = fits[0]
    runner_up_score = fits[1].score if len(fits) > 1 else 0.0
    margin = winner.score - runner_up_score

    if winner.score < MIN_WINNER_SCORE:
        raise GridQualityError(
            f"Winning grid score {winner.score:.3f} below MIN_WINNER_SCORE {MIN_WINNER_SCORE}."
        )
    if margin < MIN_WINNER_MARGIN:
        raise GridQualityError(
            f"Winning margin {margin:.3f} over runner-up below MIN_WINNER_MARGIN {MIN_WINNER_MARGIN} "
            f"— grid is ambiguous between pitch={winner.pitch} and pitch={fits[1].pitch}."
        )
    if winner.cross_row_consistency < MIN_CROSS_ROW_CONSISTENCY:
        raise GridQualityError(
            f"Cross-row consistency {winner.cross_row_consistency:.3f} below "
            f"MIN_CROSS_ROW_CONSISTENCY {MIN_CROSS_ROW_CONSISTENCY}."
        )
    if winner.normalized_residual > MAX_NORMALIZED_RESIDUAL:
        raise GridQualityError(
            f"Normalized residual {winner.normalized_residual:.3f} exceeds "
            f"MAX_NORMALIZED_RESIDUAL {MAX_NORMALIZED_RESIDUAL}."
        )
    return winner


# ---------------------------------------------------------------------
# Cell assignment — absolute position only, never ordinal
# ---------------------------------------------------------------------


class CellStatus:
    PRESENT = "present"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class CellAssignment:
    column_index: int
    status: str
    value: str | None
    x_center: float | None
    ocr_confidence: float | None  # 0.0-1.0, rescaled from Tesseract's 0-100
    structural_deviation: float | None  # px from the ideal grid line


def assign_row_to_grid(
    row: list[WordBox], grid: GridFit, column_indices: list[int]
) -> dict[int, CellAssignment]:
    """Assigns EVERY word in `row` to its NEAREST grid line by absolute
    x-center distance only — never by position within the row's own
    token sequence (ordinal assignment is exactly the mistake that
    mis-mapped '38.5' during discovery; see this module's own
    docstring). Produces an EXPLICIT entry for every index in
    `column_indices` (the table's known real columns, from the fitted
    grid's occupied_indices), even when this row has nothing there —
    status=MISSING, never simply absent from the returned dict. A
    literal dash is NOT_APPLICABLE, never coerced to a value. Two words
    landing on the same line is AMBIGUOUS, never silently overwritten."""
    by_index: dict[int, list[WordBox]] = {}
    unassigned_count = 0
    for w in row:
        distances = [(abs(w.x_center - g), i) for i, g in enumerate(grid.grid_lines)]
        dist, idx = min(distances)
        if dist > grid.tolerance or idx not in column_indices:
            unassigned_count += 1
            continue
        by_index.setdefault(idx, []).append(w)

    result: dict[int, CellAssignment] = {}
    for idx in column_indices:
        words_here = by_index.get(idx, [])
        if not words_here:
            result[idx] = CellAssignment(idx, CellStatus.MISSING, None, None, None, None)
        elif len(words_here) > 1:
            result[idx] = CellAssignment(
                idx,
                CellStatus.AMBIGUOUS,
                " / ".join(w.text for w in words_here),
                sum(w.x_center for w in words_here) / len(words_here),
                None,
                None,
            )
        else:
            w = words_here[0]
            deviation = abs(w.x_center - grid.grid_lines[idx])
            if is_dash_token(w.text):
                result[idx] = CellAssignment(
                    idx,
                    CellStatus.NOT_APPLICABLE,
                    w.text,
                    w.x_center,
                    w.confidence / 100.0,
                    deviation,
                )
            else:
                result[idx] = CellAssignment(
                    idx, CellStatus.PRESENT, w.text, w.x_center, w.confidence / 100.0, deviation
                )
    return result


# ---------------------------------------------------------------------
# Header semantic resolution — deliberately separate from geometry
# ---------------------------------------------------------------------


def resolve_header_semantics(
    header_rows: list[list[WordBox]], grid: GridFit, column_indices: list[int]
) -> dict[int, str] | None:
    """Attempts to attach a semantic label (the header's own OCR'd
    text) to each occupied grid column, by the SAME absolute-position
    matching assign_row_to_grid uses — never inferred from ordinal
    column position. Returns None (semantics UNRESOLVED) whenever
    fewer than MIN_HEADER_COVERAGE_FOR_SEMANTICS of the real columns
    have an independently-recovered header token — this is what makes
    the CTSS case (grid geometry recoverable, header text never OCR'd
    at all) fail closed rather than guessing "column 2 must be
    0.55 LPS" from position alone."""
    labels: dict[int, str] = {}
    for header_row in header_rows:
        assigned = assign_row_to_grid(header_row, grid, column_indices)
        for idx, cell in assigned.items():
            if cell.status == CellStatus.PRESENT and idx not in labels:
                labels[idx] = cell.value  # type: ignore[assignment]

    if not column_indices:
        return None
    coverage = len(labels) / len(column_indices)
    if coverage < MIN_HEADER_COVERAGE_FOR_SEMANTICS:
        return None
    return labels
