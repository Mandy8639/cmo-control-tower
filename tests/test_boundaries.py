"""The engine must not see the planted truth: only golden.py, evaluate.py and the CLI may read it."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "control_tower"
TRUTH_READERS = {"golden.py", "evaluate.py", "cli.py", "simulate.py"}


def test_engine_modules_never_touch_ground_truth():
    for py in SRC.glob("*.py"):
        if py.name in TRUTH_READERS:
            continue
        text = py.read_text()
        assert "ground_truth" not in text, py.name
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in ("golden", "evaluate", "simulate"), f"{py.name} imports {node.module}"


def test_frozen_set_untouched():
    from control_tower import golden

    assert golden.verify() == []
