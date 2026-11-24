import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retailpulse import pipeline  # noqa: E402
from retailpulse.config import Paths  # noqa: E402


@pytest.fixture(scope="session")
def built(tmp_path_factory):
    """Runs the whole pipeline once on a small dataset in a temp folder."""
    paths = Paths.under(tmp_path_factory.mktemp("rp"))
    summary = pipeline.run_all(paths=paths, quick=True, verbose=False)
    return paths, summary
