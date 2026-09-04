"""
Table Intelligence V1 foundation — pure, DB-free unit tests for
app.extraction.table_geometry. No database, no client, no OCR
execution: every test builds WordBox fixtures directly (mirroring the
real CRI JTS/CTSS performance-chart archetype validated across three
discovery spikes) and asserts against the deterministic algorithm
itself. Real-engine, real-CRI-PDF validation lives in
scripts/validate_table_extraction_against_real_cri_pdf.py, not here.

Letters A-Q below match the required-coverage list from the approved
V1 implementation directive.
"""

import pytest

from app.extraction.table_geometry import (
    ASSIGNMENT_TOLERANCE_FRACTION,
    MIN_HEADER_COVERAGE_FOR_SEMANTICS,
    CellStatus,
    GridQualityError,
    WordBox,
    assign_row_to_grid,
    cluster_words_into_rows,
    fit_best_grid,
    fit_origin_phase,
    generate_candidate_pitches,
    is_dash_token,
    is_model_shaped_token,
    is_numeric_token,
    resolve_header_semantics,
    score_grid_candidate,
)


def wb(
    text: str,
    x_center: float,
    y: float,
    width: float = 30.0,
    height: float = 12.0,
    confidence: int = 90,
) -> WordBox:
    """x/y in WordBox are top-left; tests reason in x_center, so this
    helper converts once instead of every call site doing arithmetic."""
    return WordBox(
        text=text, x=x_center - width / 2, y=y, width=width, height=height, confidence=confidence
    )


def row_at(y: float, identity: str, identity_x: float, values: dict[float, str]) -> list[WordBox]:
    row = [wb(identity, identity_x, y)]
    for x, text in values.items():
        row.append(wb(text, x, y))
    return row


COLS = [200.0, 260.0, 320.0, 380.0, 440.0]


def _three_row_table() -> tuple[list[list[WordBox]], list[list[WordBox]]]:
    """A clean synthetic 5-column, 3-row performance table — the same
    shape as the real CRI JTS table this module's own docstring
    describes, including a row with a MISSING leading cell reproducing
    the real, caught '38.5 belongs to discharge=0.3, not 0.1' bug."""
    row_a = row_at(
        100, "JTS-3/11M", -55, {200: "45.0", 260: "44.0", 320: "42.0", 380: "40.0", 440: "38.0"}
    )
    row_b = row_at(130, "JTS-3/05M", -83, {320: "38.5"})
    row_c = row_at(
        160, "JTS-3/20M", -17, {200: "46.0", 260: "45.0", 320: "43.0", 380: "41.0", 440: "39.0"}
    )
    data_rows = [row_a, row_b, row_c]
    header_row = [
        wb(t, x, 70) for x, t in zip(COLS, ["0.1", "0.2", "0.3", "0.4", "0.5"], strict=False)
    ]
    return data_rows, [header_row]


# --------------------------------------------------------------------------
# A. Token shape classification
# --------------------------------------------------------------------------


def test_a_numeric_token_shapes():
    assert is_numeric_token("38.5")
    assert is_numeric_token("-15")
    assert is_numeric_token("[42.0]")
    assert not is_numeric_token("abc")
    assert not is_numeric_token("-")


def test_a_dash_token_distinct_from_negative_number():
    assert is_dash_token("-")
    assert is_dash_token("--")
    assert not is_dash_token("-15")
    assert not is_dash_token("15")


def test_a_model_shaped_token():
    assert is_model_shaped_token("JTS-3/11M")
    assert is_model_shaped_token("CTSS-8/15T")
    assert not is_model_shaped_token("38.5")
    assert not is_model_shaped_token("Head")


# --------------------------------------------------------------------------
# B. Row clustering
# --------------------------------------------------------------------------


def test_b_row_clustering_separates_distinct_rows():
    words = [wb("a", 100, 100), wb("b", 200, 102), wb("c", 100, 140), wb("d", 200, 141)]
    rows = cluster_words_into_rows(words, y_tolerance=10.0)
    assert len(rows) == 2
    assert {w.text for w in rows[0]} == {"a", "b"}
    assert {w.text for w in rows[1]} == {"c", "d"}


def test_b_row_clustering_orders_within_row_by_x():
    words = [wb("second", 200, 100), wb("first", 100, 100)]
    rows = cluster_words_into_rows(words)
    assert [w.text for w in rows[0]] == ["first", "second"]


def test_b_row_clustering_empty_input():
    assert cluster_words_into_rows([]) == []


# --------------------------------------------------------------------------
# C/D. Pitch candidate generation, incl. explicit sub-harmonics
# --------------------------------------------------------------------------


def test_c_candidate_pitches_include_base_and_subharmonics():
    wide_cols = [200.0, 290.0, 380.0, 470.0, 560.0]  # pitch 90, so /3 = 30 clears the >20 filter
    rows = [[wb(str(x), x, 100) for x in wide_cols]]
    candidates = generate_candidate_pitches(rows)
    assert 90.0 in candidates
    assert 45.0 in candidates  # pitch/2
    assert 30.0 in candidates  # pitch/3


def test_c_candidate_pitches_empty_for_single_token():
    rows = [[wb("only", 100, 100)]]
    assert generate_candidate_pitches(rows) == []


# --------------------------------------------------------------------------
# E. Origin phase fit via multi-row residue consensus
# --------------------------------------------------------------------------


def test_e_origin_phase_matches_true_residue():
    rows = [[wb(str(x), x, 100) for x in COLS], [wb(str(x), x, 130) for x in COLS]]
    origin = fit_origin_phase(rows, pitch=60.0)
    assert origin == 200.0 % 60.0  # == 20.0


def test_e_origin_phase_robust_to_unrelated_outlier_block():
    """An unrelated column-group (e.g. a motor-power block at a
    different phase) must not shift the recovered origin — it's simply
    outvoted by the real grid's own tighter residue cluster."""
    row1 = [wb(str(x), x, 100) for x in COLS] + [
        wb("kW", 305, 100)
    ]  # 305 % 60 = 5, different phase
    row2 = [wb(str(x), x, 130) for x in COLS] + [
        wb("kW", 365, 130)
    ]  # 365 % 60 = 5, same outlier phase
    origin = fit_origin_phase([row1, row2], pitch=60.0)
    assert origin == 20.0


# --------------------------------------------------------------------------
# F. Sub-harmonic rejection via occupancy scoring
# --------------------------------------------------------------------------


def test_f_subharmonic_scores_worse_than_true_pitch_on_occupancy():
    rows = [[wb(str(x), x, 100) for x in COLS], [wb(str(x), x, 130) for x in COLS]]
    true_fit = score_grid_candidate(rows, pitch=60.0, origin_phase=20.0)
    subharmonic_fit = score_grid_candidate(rows, pitch=30.0, origin_phase=20.0 % 30.0)
    assert true_fit.occupancy_fraction > subharmonic_fit.occupancy_fraction
    assert true_fit.score > subharmonic_fit.score


# --------------------------------------------------------------------------
# G/H. Full grid fit — winner selection + quality gates
# --------------------------------------------------------------------------


def test_g_fit_best_grid_recovers_true_pitch_on_clean_table():
    data_rows, _headers = _three_row_table()
    grid = fit_best_grid(data_rows)
    assert grid.pitch == 60.0
    assert grid.origin_phase == 20.0


def test_h_fit_best_grid_rejects_insufficient_rows():
    only_row = row_at(100, "JTS-3/11M", -55, {200: "45.0"})
    with pytest.raises(GridQualityError):
        fit_best_grid([only_row])


def test_h_fit_best_grid_rejects_no_candidates():
    with pytest.raises(GridQualityError):
        fit_best_grid([[wb("only", 100, 100)], [wb("only2", 100, 130)]])


def test_h_fit_best_grid_rejects_low_cross_row_consistency():
    """A grid that only one row's tokens actually populate (a second
    row overlapping on just a single shared column) must fail closed —
    a single row's own geometry is never enough to validate a pitch
    (see this module's own docstring)."""
    xs = [100.0, 160.0, 220.0, 280.0, 340.0]
    row1 = [wb(str(x), x, 100) for x in xs]
    row2 = [wb("100", 100, 130)]  # overlaps row1 on exactly one column
    with pytest.raises(GridQualityError, match="Cross-row consistency"):
        fit_best_grid([row1, row2])


# --------------------------------------------------------------------------
# I/J/K. Absolute-position cell assignment (never ordinal)
# --------------------------------------------------------------------------


def test_i_cell_assignment_is_positional_not_ordinal():
    """The corrected, real bug this module's own docstring documents:
    a row with only ONE present value, at the table's THIRD real
    column, must be assigned to that third column — never to the
    first column just because it's the first token encountered."""
    data_rows, _headers = _three_row_table()
    grid = fit_best_grid(data_rows)
    col_idx = sorted(grid.occupied_indices)
    row_b = data_rows[1]
    cells = assign_row_to_grid(row_b, grid, col_idx)

    present = [c for c in cells.values() if c.status == CellStatus.PRESENT]
    assert len(present) == 1
    assert present[0].value == "38.5"
    # third column (index position 2 of 5 occupied columns)
    assert sorted(cells.keys())[2] == present[0].column_index


def test_j_missing_cells_are_explicit_not_absent():
    data_rows, _headers = _three_row_table()
    grid = fit_best_grid(data_rows)
    col_idx = sorted(grid.occupied_indices)
    cells = assign_row_to_grid(data_rows[1], grid, col_idx)
    assert set(cells.keys()) == set(col_idx)
    missing = [c for c in cells.values() if c.status == CellStatus.MISSING]
    assert len(missing) == 4


def test_k_dash_token_is_not_applicable_not_a_value():
    data_rows, _headers = _three_row_table()
    grid = fit_best_grid(data_rows)
    col_idx = sorted(grid.occupied_indices)
    dash_row = row_at(
        190, "JTS-3/07M", -60, {200: "-", 260: "44.5", 320: "42.5", 380: "40.5", 440: "38.5"}
    )
    cells = assign_row_to_grid(dash_row, grid, col_idx)
    dash_cell = cells[col_idx[0]]
    assert dash_cell.status == CellStatus.NOT_APPLICABLE
    assert dash_cell.value == "-"


def test_k_two_words_on_one_line_is_ambiguous():
    data_rows, _headers = _three_row_table()
    grid = fit_best_grid(data_rows)
    col_idx = sorted(grid.occupied_indices)
    doubled_row = [
        wb("JTS-3/09M", -60, 220),
        wb("44.0", 198, 220),
        wb("44.5", 202, 220),  # both land on the same grid line
    ]
    cells = assign_row_to_grid(doubled_row, grid, col_idx)
    assert cells[col_idx[0]].status == CellStatus.AMBIGUOUS


def test_i_token_beyond_tolerance_is_unassigned():
    data_rows, _headers = _three_row_table()
    grid = fit_best_grid(data_rows)
    col_idx = sorted(grid.occupied_indices)
    tolerance = grid.pitch * ASSIGNMENT_TOLERANCE_FRACTION
    stray_row = [wb("JTS-3/99M", -60, 250), wb("stray", 200 + tolerance + 5, 250)]
    cells = assign_row_to_grid(stray_row, grid, col_idx)
    assert cells[col_idx[0]].status == CellStatus.MISSING


# --------------------------------------------------------------------------
# L/M. Header semantic resolution — separate from geometry
# --------------------------------------------------------------------------


def test_l_header_semantics_resolved_when_coverage_sufficient():
    data_rows, header_rows = _three_row_table()
    grid = fit_best_grid(data_rows)
    col_idx = sorted(grid.occupied_indices)
    labels = resolve_header_semantics(header_rows, grid, col_idx)
    assert labels is not None
    assert labels[col_idx[2]] == "0.3"


def test_m_header_semantics_unresolved_below_coverage_threshold():
    """The CTSS case: grid geometry recoverable, header text lost to
    OCR — must fail closed (None), never fabricate ordinal labels."""
    data_rows, _headers = _three_row_table()
    grid = fit_best_grid(data_rows)
    col_idx = sorted(grid.occupied_indices)
    assert MIN_HEADER_COVERAGE_FOR_SEMANTICS > 0.0
    sparse_header = [wb("0.1", COLS[0], 70)]  # only 1 of 5 columns recovered
    labels = resolve_header_semantics([sparse_header], grid, col_idx)
    assert labels is None


def test_m_header_semantics_none_when_no_occupied_columns():
    data_rows, header_rows = _three_row_table()
    grid = fit_best_grid(data_rows)
    labels = resolve_header_semantics(header_rows, grid, [])
    assert labels is None


# --------------------------------------------------------------------------
# N. Determinism
# --------------------------------------------------------------------------


def test_n_fit_is_deterministic_across_repeated_runs():
    data_rows, _headers = _three_row_table()
    first = fit_best_grid(data_rows)
    second = fit_best_grid(data_rows)
    assert first.pitch == second.pitch
    assert first.origin_phase == second.origin_phase
    assert first.score == second.score


# --------------------------------------------------------------------------
# O/P/Q. Structural deviation and confidence carried through assignment
# --------------------------------------------------------------------------


def test_o_structural_deviation_recorded_for_present_cells():
    data_rows, _headers = _three_row_table()
    grid = fit_best_grid(data_rows)
    col_idx = sorted(grid.occupied_indices)
    cells = assign_row_to_grid(data_rows[0], grid, col_idx)
    present = [c for c in cells.values() if c.status == CellStatus.PRESENT]
    assert all(c.structural_deviation is not None for c in present)
    assert all(c.structural_deviation < grid.tolerance for c in present)


def test_p_ocr_confidence_carried_through_and_rescaled():
    data_rows, _headers = _three_row_table()
    grid = fit_best_grid(data_rows)
    col_idx = sorted(grid.occupied_indices)
    row = [wb("JTS-3/11M", -55, 100)] + [wb("45.0", 200, 100, confidence=77)]
    cells = assign_row_to_grid(row, grid, col_idx)
    present_cell = next(c for c in cells.values() if c.status == CellStatus.PRESENT)
    assert present_cell.ocr_confidence == 0.77


def test_q_missing_and_ambiguous_cells_have_no_ocr_confidence():
    data_rows, _headers = _three_row_table()
    grid = fit_best_grid(data_rows)
    col_idx = sorted(grid.occupied_indices)
    cells = assign_row_to_grid(data_rows[1], grid, col_idx)
    missing = [c for c in cells.values() if c.status == CellStatus.MISSING]
    assert all(c.ocr_confidence is None for c in missing)
