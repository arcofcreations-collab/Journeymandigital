"""Download the pinned benchmark source files into bench/data/ (idempotent)."""

import hashlib
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from sources import SOURCES, raw_url  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")


def local_path(repo_key, path):
    return os.path.join(DATA, repo_key, path)


def main():
    manifest = {}
    for split, repo, path, col, parser in SOURCES:
        dst = local_path(repo, path)
        if not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            url = raw_url(repo, path)
            print("fetch", url)
            with urllib.request.urlopen(url, timeout=120) as r:
                blob = r.read()
            with open(dst, "wb") as fh:
                fh.write(blob)
        with open(dst, "rb") as fh:
            manifest[f"{repo}/{path}"] = hashlib.sha256(fh.read()).hexdigest()
    with open(os.path.join(DATA, "MANIFEST.json"), "w") as fh:
        json.dump(manifest, fh, indent=1, sort_keys=True)
    print(f"{len(manifest)} files ready in {DATA}")


if __name__ == "__main__":
    main()
