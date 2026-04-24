from __future__ import annotations

from decimal import Decimal
from typing import Any


def canon_row(row) -> tuple[str, ...]:
    out: list[str] = []
    for v in row:
        if v is None:
            out.append("\x00NULL")
        elif isinstance(v, Decimal):
            out.append(f"{round(float(v), 2):.2f}")
        elif isinstance(v, bool):
            out.append("1" if v else "0")
        elif isinstance(v, (int, float)):
            out.append(f"{round(float(v), 2):.2f}")
        else:
            out.append(str(v).strip())
    return tuple(out)


def result_equal(pred_rows: list[list[Any]] | None, gold_rows: list[tuple]) -> bool:
    if pred_rows is None:
        return False
    if not pred_rows and not gold_rows:
        return True

    pset = sorted([canon_row(r) for r in pred_rows])
    gset = sorted([canon_row(r) for r in gold_rows])
    if pset == gset:
        return True

    if len(pset) == len(gset):
        return all(sorted(p) == sorted(g) for p, g in zip(pset, gset, strict=False))
    return False
