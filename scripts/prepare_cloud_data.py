"""Restore the public runtime archives shipped with the cloud deployment.

Raw training downloads are reproduced by the existing backfill scripts. This
bundle contains the original app's scores, schedules, structures, metadata,
F1 inputs, box scores, news cache and warm engine states, without credentials.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile


def prepare(root: Path) -> None:
    bundle = root / "deployment" / "engine-data"
    manifest = json.loads((bundle / "manifest.json").read_text())
    encoded = "".join((bundle / name).read_text() for name in manifest["parts"])
    archive = base64.b64decode(encoded, validate=True)
    if hashlib.sha256(archive).hexdigest() != manifest["sha256"]:
        raise ValueError("Cloud data checksum mismatch")
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            path = Path(member.name)
            if (not member.isfile() or path.is_absolute() or ".." in path.parts
                    or path.parts[:2] not in {("data", "real"), ("data", "state")}):
                raise ValueError(f"Unexpected cloud archive member: {member.name}")
        if len(members) != manifest["files"]:
            raise ValueError("Cloud archive file count mismatch")
        tar.extractall(root, members=members, filter="data")
    print(f"Restored {len(members)} public engine input files", flush=True)


if __name__ == "__main__":
    prepare(Path(__file__).resolve().parents[1])
