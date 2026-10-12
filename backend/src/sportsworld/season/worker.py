"""Private simulation subprocess; not an HTTP or user-upload interface."""
from pathlib import Path
import pickle
import sys

from .engine import run_season


if __name__ == "__main__":
    source, output = map(Path, sys.argv[1:3])
    with source.open("rb") as stream:
        setup, kwargs = pickle.load(stream)
    result = run_season(setup, **kwargs)
    with output.open("wb") as stream:
        pickle.dump(result, stream)
