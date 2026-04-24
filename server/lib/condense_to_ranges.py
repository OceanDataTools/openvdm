#!/usr/bin/env python3
"""Utilities for condensing consecutive integers into human-readable range strings.

Used primarily to compact line-number lists in file-parsing error messages, e.g.
``[1, 2, 3, 5, 6]`` → ``['1-3', '5-6']``.
"""

from typing import Iterable, Iterator


def condense_to_ranges(integers: Iterable[int]) -> Iterator[str]:
    """Reduce a collection of integers to a sequence of condensed range strings.

    Consecutive integers are collapsed into ``"start-end"`` notation.
    Single-element ranges are returned as plain integers (e.g. ``"5"`` not
    ``"5-5"``).  Primarily used to shorten file-parsing error messages that
    list large numbers of bad row numbers.

    Args:
        integers: An iterable of integers to condense.

    Returns:
        An iterator of range strings, e.g. ``['1-3', '5', '7-9']``.

    Example:
        >>> list(condense_to_ranges([1, 2, 3, 5, 7, 8, 9]))
        ['1-3', '5', '7-9']
    """

    ranges = []
    start = None
    prev = None

    def reduce_ranges(r: str) -> str:
        """Collapse a ``"start-end"`` string to ``"start"`` when both are equal."""
        s, p = r.split('-')
        return s if s == p else r

    for num in sorted(integers):
        if start is None:
            start = num
            prev = num
        elif num == prev + 1:
            prev = num
        else:
            ranges.append(f"{start}-{prev}")
            start = num
            prev = num

    if start is not None:
        ranges.append(f"{start}-{prev}")

    return map(reduce_ranges, ranges)
