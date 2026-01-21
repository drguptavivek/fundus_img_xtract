import cv2
import pytesseract
import numpy as np
import os
import shutil
from pathlib import Path

# Configuration
INPUT_DIR = "/home/aiims/Desktop/Yash/DR/Phase_1/mild dr/"
OUTPUT_DIR = "/home/aiims/Desktop/Yash/OCR/v3/PII/"
CLEAN_DIR = "/home/aiims/Desktop/Yash/OCR/v3/PII/clean"  # Optional

# ROI for top-left corner (more conservative)
ROI_HEIGHT_RATIO = 0.20
ROI_WIDTH_RATIO = 0.30

# Multiple detection strategies
MIN_TEXT_LENGTH = 2
MIN_CONFIDENCE = 50
MIN_VALID_DETECTIONS = 1

# Create output directories
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CLEAN_DIR, exist_ok=True)


def preprocess_roi_multi(roi):
    """
    Apply multiple preprocessing strategies to maximize text detection
    Returns a list of processed images
    """
    processed_images = []
    
    # Strategy 1: Grayscale + Adaptive Threshold
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    adaptive = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY, 11, 2
    )
    processed_images.append(adaptive)
    
    # Strategy 2: Enhanced contrast + Binary threshold
    gray_eq = cv2.equalizeHist(gray)
    _, binary = cv2.threshold(gray_eq, 150, 255, cv2.THRESH_BINARY)
    processed_images.append(binary)
    
    # Strategy 3: Inverted binary (white text on black)
    _, binary_inv = cv2.threshold(gray_eq, 150, 255, cv2.THRESH_BINARY_INV)
    processed_images.append(binary_inv)
    
    # Strategy 4: CLAHE (Contrast Limited Adaptive Histogram Equalization)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    clahe_img = clahe.apply(gray)
    _, clahe_bin = cv2.threshold(clahe_img, 160, 255, cv2.THRESH_BINARY)
    processed_images.append(clahe_bin)
    
    # Strategy 5: Edge-enhanced for overlay text
    blurred = cv2.GaussianBlur(gray, (3,3), 0)
    edges = cv2.Canny(blurred, 50, 150)
    kernel = np.ones((2,2), np.uint8)
    edges_dilated = cv2.dilate(edges, kernel, iterations=1)
    processed_images.append(edges_dilated)
    
    return processed_images


def detect_text_patterns(text):
    """
    Check if detected text matches common PII patterns
    """
    text = text.strip().upper()
    
    # Common patterns in retinal images
    pii_indicators = [
        # Date patterns
        lambda t: any(c.isdigit() for c in t) and len(t) >= 4,
        # Common labels
        lambda t: any(word in t for word in ['OD', 'OS', 'NAME', 'ID', 'DATE', 'DOB', 'AGE']),
        # Mixed alphanumeric (IDs)
        lambda t: any(c.isdigit() for c in t) and any(c.isalpha() for c in t),
        # Sequential numbers (dates, IDs)
        lambda t: sum(c.isdigit() for c in t) >= 4,
    ]
    
    return any(check(text) for check in pii_indicators)


def extract_text_multi_strategy(roi):
    """
    Try multiple OCR configurations and preprocessing methods
    """
    all_detections = []
    
    # Get multiple preprocessed versions
    processed_images = preprocess_roi_multi(roi)
    
    # OCR configurations to try
    configs = [
        "--psm 6 --oem 3",  # Uniform block of text
        "--psm 11 --oem 3", # Sparse text
        "--psm 12 --oem 3", # Sparse text with OSD
        "--psm 7 --oem 3",  # Single line
    ]
    
    for proc_img in processed_images:
        for config in configs:
            try:
                # Get detailed data
                data = pytesseract.image_to_data(
                    proc_img,
                    config=config,
                    output_type=pytesseract.Output.DICT
                )
                
                # Extract valid text
                for i, txt in enumerate(data["text"]):
                    txt_clean = txt.strip()
                    conf = int(data["conf"][i])
                    
                    if len(txt_clean) >= MIN_TEXT_LENGTH and conf > MIN_CONFIDENCE:
                        all_detections.append({
                            'text': txt_clean,
                            'conf': conf,
                            'matches_pattern': detect_text_patterns(txt_clean)
                        })
            except Exception as e:
                continue
    
    return all_detections


def analyze_roi_structure(roi):
    """
    Analyze if ROI has the characteristic structure of overlaid text
    """
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    
    # Check for high-contrast regions (text overlay)
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    white_pixels = np.sum(binary == 255)
    
    # Check for very dark regions (black background of overlay)
    dark_pixels = np.sum(gray < 30)
    
    total_pixels = gray.size
    white_ratio = white_pixels / total_pixels
    dark_ratio = dark_pixels / total_pixels
    
    # Text overlay typically has both bright text and dark background
    has_structure = (white_ratio > 0.01 and dark_ratio > 0.05) or white_ratio > 0.03
    
    return has_structure


def has_pii(image_path, debug=False):
    """
    Main PII detection function with multiple validation layers
    """
    # Read image
    img = cv2.imread(image_path)
    if img is None:
        print(f"⚠️  Cannot read: {image_path}")
        return False
    
    h, w = img.shape[:2]
    
    # Extract ROI (top-left corner)
    roi_h = int(h * ROI_HEIGHT_RATIO)
    roi_w = int(w * ROI_WIDTH_RATIO)
    roi = img[0:roi_h, 0:roi_w]
    
    # Layer 1: Structural analysis
    has_text_structure = analyze_roi_structure(roi)
    
    # Layer 2: Multi-strategy text extraction
    detections = extract_text_multi_strategy(roi)
    
    # Filter for high-quality detections
    valid_detections = [
        d for d in detections 
        if d['conf'] > MIN_CONFIDENCE and len(d['text']) >= MIN_TEXT_LENGTH
    ]
    
    # Check for pattern matches
    pattern_matches = [d for d in valid_detections if d['matches_pattern']]
    
    # Decision logic
    has_text = len(valid_detections) >= MIN_VALID_DETECTIONS
    has_patterns = len(pattern_matches) > 0
    
    is_pii = (has_text_structure and has_text) or has_patterns
    
    if debug:
        print(f"\n--- Debug: {os.path.basename(image_path)} ---")
        print(f"Structure detected: {has_text_structure}")
        print(f"Valid detections: {len(valid_detections)}")
        print(f"Pattern matches: {len(pattern_matches)}")
        if valid_detections:
            print("Top detections:")
            for d in sorted(valid_detections, key=lambda x: x['conf'], reverse=True)[:5]:
                print(f"  '{d['text']}' (conf={d['conf']}, pattern={d['matches_pattern']})")
    
    return is_pii


def process_images(debug_mode=False):
    """
    Process all images in the input directory
    """
    input_path = Path(INPUT_DIR)
    
    if not input_path.exists():
        print(f"❌ Input directory not found: {INPUT_DIR}")
        return
    
    # Supported formats
    extensions = ('.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp')
    image_files = [f for f in input_path.iterdir() 
                   if f.suffix.lower() in extensions]
    
    if not image_files:
        print(f"❌ No images found in {INPUT_DIR}")
        return
    
    print(f"🔍 Processing {len(image_files)} images...\n")
    
    pii_count = 0
    clean_count = 0
    
    for img_file in image_files:
        try:
            if has_pii(str(img_file), debug=debug_mode):
                # Copy to PII folder
                shutil.copy(str(img_file), os.path.join(OUTPUT_DIR, img_file.name))
                print(f"🚨 PII DETECTED: {img_file.name}")
                pii_count += 1
            else:
                # Copy to clean folder
                shutil.copy(str(img_file), os.path.join(CLEAN_DIR, img_file.name))
                print(f"✅ Clean: {img_file.name}")
                clean_count += 1
        except Exception as e:
            print(f"❌ Error processing {img_file.name}: {e}")
    
    print(f"\n{'='*50}")
    print(f"📊 Summary:")
    print(f"   Total processed: {len(image_files)}")
    print(f"   🚨 PII detected: {pii_count}")
    print(f"   ✅ Clean images: {clean_count}")
    print(f"{'='*50}")


if __name__ == "__main__":
    # Set debug_mode=True to see detailed detection info
    process_images(debug_mode=False)