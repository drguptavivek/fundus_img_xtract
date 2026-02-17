from __future__ import annotations

from dataclasses import dataclass, replace
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
    tesseract_timeout_seconds: float = 20.0
    max_preprocess_variants: int = 3
    max_ocr_configs: int = 2
    early_exit_on_pattern_match: bool = True


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
    text = text.strip()
    # Ignore OCR-ambiguous glyphs unless other alphanumerics exist.
    ignore_chars = {"0", "O", "1", "l", "L"}
    return any(c.isalnum() and c not in ignore_chars for c in text)


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
    processed_images = preprocess_roi_multi(roi)[: max(1, int(config.max_preprocess_variants))]
    configs = [
        "--psm 6 --oem 3",
        "--psm 11 --oem 3",
        "--psm 12 --oem 3",
        "--psm 7 --oem 3",
    ][: max(1, int(config.max_ocr_configs))]
    seen: set[tuple[str, int, int, int, int]] = set()

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
            left_values = data.get("left") or []
            top_values = data.get("top") or []
            width_values = data.get("width") or []
            height_values = data.get("height") or []
            for i, txt in enumerate(data.get("text", [])):
                txt_clean = (txt or "").strip()
                conf_raw = conf_values[i] if i < len(conf_values) else -1
                conf = _safe_int(conf_raw)
                left = _safe_int(left_values[i]) if i < len(left_values) else 0
                top = _safe_int(top_values[i]) if i < len(top_values) else 0
                width = _safe_int(width_values[i]) if i < len(width_values) else 0
                height = _safe_int(height_values[i]) if i < len(height_values) else 0
                if len(txt_clean) >= config.min_text_length and conf > config.min_confidence:
                    dedup_key = (
                        txt_clean.upper(),
                        max(0, left),
                        max(0, top),
                        max(0, width),
                        max(0, height),
                    )
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    matches_pattern = detect_text_patterns(txt_clean)
                    all_detections.append(
                        {
                            "text": txt_clean,
                            "conf": conf,
                            "matches_pattern": matches_pattern,
                            "box": {
                                "x": max(0, left),
                                "y": max(0, top),
                                "w": max(0, width),
                                "h": max(0, height),
                            },
                        }
                    )
                    if config.early_exit_on_pattern_match and matches_pattern:
                        return all_detections

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
    detect_cfg = config
    if not has_text_structure:
        # Fast path when ROI structure is weak: run a single OCR pass only.
        detect_cfg = replace(config, max_preprocess_variants=1, max_ocr_configs=1)
    detections = extract_text_multi_strategy(roi, detect_cfg)
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


def detect_pii_details_for_image(
    img: np.ndarray, config: OcrPiiConfig | None = None
) -> Dict[str, Any]:
    config = config or OcrPiiConfig()
    h, w = img.shape[:2]
    roi_h = int(h * config.roi_height_ratio)
    roi_w = int(w * config.roi_width_ratio)
    roi = img[0:roi_h, 0:roi_w]
    max_dim = config.max_roi_dim
    scale_x = 1.0
    scale_y = 1.0
    if max_dim and (roi.shape[0] > max_dim or roi.shape[1] > max_dim):
        scale = min(max_dim / roi.shape[0], max_dim / roi.shape[1])
        new_w = max(1, int(roi.shape[1] * scale))
        new_h = max(1, int(roi.shape[0] * scale))
        scale_x = roi.shape[1] / new_w
        scale_y = roi.shape[0] / new_h
        roi = cv2.resize(roi, (new_w, new_h), interpolation=cv2.INTER_AREA)

    has_text_structure = analyze_roi_structure(roi)
    detect_cfg = config
    if not has_text_structure:
        # Fast path when ROI structure is weak: run a single OCR pass only.
        detect_cfg = replace(config, max_preprocess_variants=1, max_ocr_configs=1)
    detections = extract_text_multi_strategy(roi, detect_cfg)
    valid_detections = [
        d for d in detections if d["conf"] > config.min_confidence
    ]
    pattern_matches = [d for d in valid_detections if d["matches_pattern"]]

    for det in valid_detections:
        box = det.get("box") or {}
        det["box"] = {
            "x": int((box.get("x", 0) or 0) * scale_x),
            "y": int((box.get("y", 0) or 0) * scale_y),
            "w": int((box.get("w", 0) or 0) * scale_x),
            "h": int((box.get("h", 0) or 0) * scale_y),
        }

    has_text = len(valid_detections) >= config.min_valid_detections
    has_patterns = bool(pattern_matches)
    is_pii = (has_text_structure and has_text) or has_patterns

    return {
        "is_pii": is_pii,
        "valid_detections": len(valid_detections),
        "pattern_matches": len(pattern_matches),
        "detections": valid_detections,
        "roi": {
            "x": 0,
            "y": 0,
            "w": roi_w,
            "h": roi_h,
        },
    }


def detect_pii_for_path(image_path: str, config: OcrPiiConfig | None = None) -> Dict[str, Any]:
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("Unable to read image")
    return detect_pii_for_image(img, config=config)


def detect_pii_details_for_path(image_path: str, config: OcrPiiConfig | None = None) -> Dict[str, Any]:
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("Unable to read image")
    return detect_pii_details_for_image(img, config=config)
