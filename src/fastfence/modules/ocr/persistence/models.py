"""Fixed mobile model catalogue; downloads are a separate operator command."""

import importlib
import os
from pathlib import Path
from typing import Any

from fastfence.shared.ocr import OCRError

MODEL_NAMES = (
    "PP-LCNet_x1_0_doc_ori",
    "PP-OCRv5_mobile_det",
    "latin_PP-OCRv5_mobile_rec",
)


def load_models(root: Path, *, download: bool = False) -> Any:
    os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
    paddle_ocr = importlib.import_module("paddleocr").PaddleOCR

    if not download and any(
        not (root / name / "inference.json").is_file() for name in MODEL_NAMES
    ):
        raise OCRError("ocr_unavailable")
    directories = (
        {}
        if download
        else {
            "doc_orientation_classify_model_dir": str(root / MODEL_NAMES[0]),
            "text_detection_model_dir": str(root / MODEL_NAMES[1]),
            "text_recognition_model_dir": str(root / MODEL_NAMES[2]),
        }
    )
    return paddle_ocr(
        doc_orientation_classify_model_name=MODEL_NAMES[0],
        text_detection_model_name=MODEL_NAMES[1],
        text_recognition_model_name=MODEL_NAMES[2],
        use_doc_orientation_classify=True,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        text_rec_score_thresh=0.0,
        device="cpu",
        cpu_threads=2,
        enable_mkldnn=False,
        **directories,
    )
