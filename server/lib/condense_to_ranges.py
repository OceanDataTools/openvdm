#!/usr/bin/env python3
"""Utilities for condensing file parsing error messages
"""

def condense_to_ranges(integers):
    """
    Function to reduce array of consecutive numbers to ranges. This helps
    condense message bodies related to file parsing errors. 
    """

    ranges = []
    start = None
    prev = None

    def reduce_ranges(r):
        start, prev = r.split('-')
        return start if start == prev else r

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

    # Add the last range
    if start is not None:
        ranges.append(f"{start}-{prev}")

    return map(reduce_ranges, ranges)
