"""json_ready must turn every NumPy scalar type actually produced by the engine into a
plain, `json.dumps`-safe Python value -- including NumPy booleans at the root, not only
inside a dict/list/array."""
import json

import numpy as np

from cornhole_biomech.serialization import canonical_hash, json_ready


def test_json_ready_converts_a_root_level_numpy_bool():
    # NumPy 2's np.bool_ (aka np.bool) is not a subclass of Python's bool or np.integer,
    # so json.dumps rejects it unless json_ready converts it first.
    value = np.bool_(True)
    assert isinstance(value, np.bool_) and not isinstance(value, bool)
    ready = json_ready(value)
    assert ready is True and isinstance(ready, bool)
    json.dumps(ready)   # must not raise


def test_json_ready_converts_numpy_bools_nested_in_a_dict():
    payload = {"distinguishes": np.bool_(False), "clear": np.bool_(True)}
    ready = json_ready(payload)
    assert ready == {"distinguishes": False, "clear": True}
    json.dumps(ready)


def test_canonical_hash_accepts_a_root_level_numpy_bool():
    assert canonical_hash(np.bool_(True)) == canonical_hash(True)
