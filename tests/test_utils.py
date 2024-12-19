"""Test miscellaneous utility functions."""

import random
import numpy as np


from autocommit.utils import compute_truncation

def test_compute_truncation(num_lens = 15, max_len=40, max_total_length = 200):
    lengths = [random.randint(0, max_len) for _ in range(num_lens)]
    truncation = compute_truncation(lengths, max_total_length)
    np_lengths = np.array(lengths)
    assert truncation is None or truncation > 0
    if truncation is None:
        assert np_lengths.sum() <= max_total_length
    else:
        truncated_lengths = np.minimum(np_lengths, truncation)
        assert truncated_lengths.sum() <= max_total_length
        next_truncated_lengths = np.minimum(np_lengths, truncation + 1)
        assert next_truncated_lengths.sum() > max_total_length

