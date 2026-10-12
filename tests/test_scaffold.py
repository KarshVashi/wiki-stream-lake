import importlib

import pytest


@pytest.mark.parametrize("package", ["producer", "transform_lambda", "glue_jobs"])
def test_source_packages_import(package):
    assert importlib.import_module(package)
