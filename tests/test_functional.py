"""Functional tests using the DataDirTester framework."""

from pathlib import Path

from keboola.datadirtest import DataDirTester

FUNCTIONAL_DIR = Path(__file__).parent / "functional"
COMPONENT_SCRIPT = Path(__file__).parent.parent / "src" / "component.py"


def test_functional():
    DataDirTester(
        data_dir=str(FUNCTIONAL_DIR),
        component_script=str(COMPONENT_SCRIPT),
    ).run()
