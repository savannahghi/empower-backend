"""Tests for config utils module."""
from sil_advantage.config.utils import split_env_values

assert split_env_values(None) == []
assert split_env_values("A,B") == ["A", "B"]
assert split_env_values("", ",") == []
assert split_env_values("A,B", ",") == ["A", "B"]
assert split_env_values("1,2,3", transform_func=int) == [1, 2, 3]
