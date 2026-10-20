import pytest
from feedflow.dedup import simhash_features


def test_same_features_same_fingerprint():
    assert simhash_features([("a", 1), ("b", 2)]) == simhash_features([("a", 1), ("b", 2)])


def test_different_features_different_fingerprint():
    assert simhash_features([("a", 1), ("b", 2)]) != simhash_features([("c", 1), ("d", 2)])


def test_weight_changes_fingerprint():
    assert simhash_features([("a", 1), ("b", 3)]) != simhash_features([("a", 3), ("b", 1)])
    assert simhash_features([("a", 1), ("b", 3)]) != simhash_features([("a", 1), ("b", 1)])
