# --- Tile grids --------------------------------------------------------------


def test_grid_slots_keep_every_row_the_same_width():
    from chemsidekick.core.schemas import CellInfo, Table
    from chemsidekick.ui.render import grid_slots

    cells = {s: CellInfo(tag=tag) for s, tag in [("A", "s"), ("B", "d"), ("C", "f"), ("D", "f")]}
    t = Table(
        columns=["", "1", "2", "3"],
        rows=[["1", "A", "B", ""], ["Ln", "", "C", "D"]],
        action_field="q",
        action_columns=[1, 2, 3],
        cells=cells,
        column_gaps=[2, 3],
    )
    # Row 1: gaps before columns 2 and 3 (the cells change block or are empty).
    assert grid_slots(t, t.rows[0]) == [0, 1, None, 2, None, 3]
    # Row 2: C and D are both f-block, so that gap moves to the end of the row.
    assert grid_slots(t, t.rows[1]) == [0, 1, None, 2, 3, None]
