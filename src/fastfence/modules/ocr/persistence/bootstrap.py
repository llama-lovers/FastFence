"""Operator-only bounded mobile-model initialization; no document processing."""

import os
import shutil
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python -m fastfence.modules.ocr.persistence.bootstrap MODEL_DIR"
        )
    target = Path(sys.argv[1]).resolve()
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    cache = target / "download-cache"
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(cache)
    from fastfence.modules.ocr.persistence.models import (
        MODEL_NAMES,
        load_models,
    )

    load_models(target, download=True)
    for name in MODEL_NAMES:
        source = cache / "official_models" / name
        if not source.is_dir():
            raise SystemExit("Required OCR mobile model was not downloaded")
        destination = target / name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
    sys.stdout.write("Local mobile OCR models ready\n")


if __name__ == "__main__":
    main()
