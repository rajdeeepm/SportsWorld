"""Private simulation subprocess; not an HTTP or user-upload interface."""
from pathlib import Path
import pickle
import sys
import os

from .engine import run_season


if __name__ == "__main__":
    if sys.platform.startswith("linux"):
        os.nice(5)  # Keep the web API responsive when CPU is shared.
    source, output = map(Path, sys.argv[1:3])
    with source.open("rb") as stream:
        setup, kwargs = pickle.load(stream)
    result = run_season(setup, **kwargs)
    with output.open("wb") as stream:
        pickle.dump(result, stream)
