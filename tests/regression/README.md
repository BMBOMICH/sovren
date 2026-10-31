# Actual regression implementations

`cache.py`, `dependencies.py`, `artifact_modes.py` and `constant_eval.py` contain the real tests. The first three were moved out of `work/session20261014/`; old command paths remain regular Python forwarding files.

`../integration/native_frontend.py` owns sugar, suite and bootstrap checks. `../integration/physical_layout.py` verifies real implementation files and compatibility entry points. `../conformance/` contains semantic/runtime and output/worker fault tests. No symlink is needed to retain these files across a workspace save.
