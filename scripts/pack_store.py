#!/usr/bin/env python3
"""Package the Raspberry Ripple Chrome theme into a Chrome Web Store zip.

The zip keeps `manifest.json` at the root and contains only the theme body
(manifest + icon + README). Store artwork, promo tiles, scripts, and local
files are excluded. The zip is written to `dist/` and mirrored to the default
project folder (derived from this project's location), then self-verified.

See chrome-store-zip-structure-and-package-script-RULE.
"""
from pathlib import Path
import json
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
DEFAULT_OUT = ROOT.parent.parent          # D:\迅雷下载\vibe coding\
NAME = "raspberry-ripple-theme"

# Theme body only; store assets / scripts / local files are excluded.
INCLUDE_FILES = ["logo/logo.png", "README.md"]


def main():
    DIST.mkdir(exist_ok=True)
    raw = (ROOT / "manifest.json").read_text("utf-8-sig")
    manifest = json.loads(raw)
    version = manifest["version"]
    assert manifest.get("manifest_version") == 3, "manifest_version must be 3"

    zip_name = f"{NAME}-{version}.zip"

    # Every file referenced by the manifest must exist on disk.
    refs = [v for v in manifest.get("icons", {}).values()
            if isinstance(v, str) and "/" in v]
    missing = [r for r in refs if not (ROOT / r).exists()]
    assert not missing, f"manifest references missing files: {missing}"
    for rel in INCLUDE_FILES:
        assert (ROOT / rel).exists(), f"missing include: {rel}"

    zip_path = DIST / zip_name
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        # write manifest without a BOM so Chrome's parser is happy
        z.writestr("manifest.json", raw.encode("utf-8"))
        for rel in INCLUDE_FILES:
            z.write(ROOT / rel, rel)
        assert "manifest.json" in z.namelist(), "manifest.json must be at zip root"

    # Re-read the manifest from inside the zip to confirm it round-trips.
    with zipfile.ZipFile(zip_path) as z:
        inside = json.loads(z.read("manifest.json").decode("utf-8"))
        contents = sorted(z.namelist())
    assert inside["name"] == manifest["name"], "zip manifest name mismatch"

    # Mirror to the default folder, overwrite, verify byte-identical.
    DEFAULT_OUT.mkdir(parents=True, exist_ok=True)
    dst = DEFAULT_OUT / zip_name
    shutil.copyfile(zip_path, dst)
    assert zip_path.read_bytes() == dst.read_bytes(), "default-folder copy is not identical"

    print(f"Packaged {zip_path}")
    print(f"Mirrored  {dst}")
    print("Zip contents:", contents)


if __name__ == "__main__":
    main()
