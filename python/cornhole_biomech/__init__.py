"""Cornhole Biomechanics Lab scientific analysis package."""

__version__ = "0.6.1"

# Version of the measurement definitions. Bump it only when a change alters
# what a saved number means (a formula, filter, event rule or unit). Throws
# analysed under different method versions are never pooled or compared.
# The engine source hash stays in each manifest as provenance, but it is not
# used for compatibility, so edits to comments or UI code keep old analyses usable.
METHOD_VERSION = "2026.09.22"

REQUIRED_LANDMARKS = (
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
)
