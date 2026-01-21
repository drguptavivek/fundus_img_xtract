from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import cv2
import numpy as np
import pytesseract


@dataclass(frozen=True)
class OcrPiiConfig:
    roi_height_ratio: float = 0.20
    roi_width_ratio: float = 0.30
    min_text_length: int = 2
    min_confidence: int = 50
    min_valid_detections: int = 1
    max_roi_dim: int = 1200
    tesseract_timeout_seconds: float = 10.0


def preprocess_roi_multi(roi: np.ndarray) -> List[np.ndarray]:
    processed_images: List[np.ndarray] = []

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    adaptive = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11,
        2,
    )
    processed_images.append(adaptive)

    gray_eq = cv2.equalizeHist(gray)
    _, binary = cv2.threshold(gray_eq, 150, 255, cv2.THRESH_BINARY)
    processed_images.append(binary)

    _, binary_inv = cv2.threshold(gray_eq, 150, 255, cv2.THRESH_BINARY_INV)
    processed_images.append(binary_inv)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    clahe_img = clahe.apply(gray)
    _, clahe_bin = cv2.threshold(clahe_img, 160, 255, cv2.THRESH_BINARY)
    processed_images.append(clahe_bin)

    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, 50, 150)
    kernel = np.ones((2, 2), np.uint8)
    edges_dilated = cv2.dilate(edges, kernel, iterations=1)
    processed_images.append(edges_dilated)

    return processed_images


def detect_text_patterns(text: str) -> bool:
    text = text.strip().upper()
    pii_indicators = [
        lambda t: any(c.isdigit() for c in t) and len(t) >= 4,
        lambda t: any(word in t for word in ["OD", "OS", "NAME", "ID", "DATE", "DOB", "AGE"]),
        lambda t: any(c.isdigit() for c in t) and any(c.isalpha() for c in t),
        lambda t: sum(c.isdigit() for c in t) >= 4,
    ]
    return any(check(text) for check in pii_indicators)


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return -1


def extract_text_multi_strategy(
    roi: np.ndarray,
    config: OcrPiiConfig,
) -> List[Dict[str, Any]]:
    all_detections: List[Dict[str, Any]] = []
    processed_images = preprocess_roi_multi(roi)
    configs = [
        "--psm 6 --oem 3",
        "--psm 11 --oem 3",
        "--psm 12 --oem 3",
        "--psm 7 --oem 3",
    ]

    for proc_img in processed_images:
        for ocr_config in configs:
            try:
                data = pytesseract.image_to_data(
                    proc_img,
                    config=ocr_config,
                    output_type=pytesseract.Output.DICT,
                    timeout=config.tesseract_timeout_seconds,
                )
            except pytesseract.TesseractError:
                continue
            conf_values = data.get("conf") or []
            for i, txt in enumerate(data.get("text", [])):
                txt_clean = (txt or "").strip()
                conf_raw = conf_values[i] if i < len(conf_values) else -1
                conf = _safe_int(conf_raw)
                if len(txt_clean) >= config.min_text_length and conf > config.min_confidence:
                    all_detections.append(
                        {
                            "text": txt_clean,
                            "conf": conf,
                            "matches_pattern": detect_text_patterns(txt_clean),
                        }
                    )

    return all_detections


def analyze_roi_structure(roi: np.ndarray) -> bool:
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    white_pixels = np.sum(binary == 255)
    dark_pixels = np.sum(gray < 30)

    total_pixels = gray.size
    white_ratio = white_pixels / total_pixels
    dark_ratio = dark_pixels / total_pixels

    return (white_ratio > 0.01 and dark_ratio > 0.05) or white_ratio > 0.03


def detect_pii_for_image(img: np.ndarray, config: OcrPiiConfig | None = None) -> Dict[str, Any]:
    config = config or OcrPiiConfig()
    h, w = img.shape[:2]
    roi_h = int(h * config.roi_height_ratio)
    roi_w = int(w * config.roi_width_ratio)
    roi = img[0:roi_h, 0:roi_w]
    max_dim = config.max_roi_dim
    if max_dim and (roi.shape[0] > max_dim or roi.shape[1] > max_dim):
        scale = min(max_dim / roi.shape[0], max_dim / roi.shape[1])
        new_w = max(1, int(roi.shape[1] * scale))
        new_h = max(1, int(roi.shape[0] * scale))
        roi = cv2.resize(roi, (new_w, new_h), interpolation=cv2.INTER_AREA)

    has_text_structure = analyze_roi_structure(roi)
    detections = extract_text_multi_strategy(roi, config)
    valid_detections = [
        d for d in detections if d["conf"] > config.min_confidence
    ]
    pattern_matches = [d for d in valid_detections if d["matches_pattern"]]

    has_text = len(valid_detections) >= config.min_valid_detections
    has_patterns = bool(pattern_matches)
    is_pii = (has_text_structure and has_text) or has_patterns

    return {
        "is_pii": is_pii,
        "valid_detections": len(valid_detections),
        "pattern_matches": len(pattern_matches),
    }


def detect_pii_for_path(image_path: str, config: OcrPiiConfig | None = None) -> Dict[str, Any]:
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("Unable to read image")
    return detect_pii_for_image(img, config=config)
