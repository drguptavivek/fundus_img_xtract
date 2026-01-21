import cv2
import numpy as np
import os

ROI_HEIGHT_RATIO = 0.25
ROI_WIDTH_RATIO  = 0.35
BLACK_V_THRESHOLD = 38
MIN_REGION_AREA  = 200
RETINA_SAFETY_PX = 20

CONTRAST   = 36
BRIGHTNESS = 50
GAMMA      = 0.7

OUTPUT_DIR = "/home/aiims/Desktop/Yash/OPTHA/DR/Phase_1/anonymized"

def adjust_gamma(image, gamma):
    inv_gamma = 1.0 / gamma
    table = np.array([(i / 255.0) ** inv_gamma * 255 for i in range(256)]).astype("uint8")
    return cv2.LUT(image, table)

def preprocess_image(img):
    alpha = 1 + (CONTRAST / 100)
    img = cv2.convertScaleAbs(img, alpha=alpha, beta=BRIGHTNESS)
    img = adjust_gamma(img, GAMMA)
    return img

def anonymize_fundus(image_path):
    img_original = cv2.imread(image_path)
    if img_original is None:
        return None

    img_enhanced = preprocess_image(img_original.copy())

    h, w = img_enhanced.shape[:2]
    roi_h = int(h * ROI_HEIGHT_RATIO)
    roi_w = int(w * ROI_WIDTH_RATIO)

    roi = img_enhanced[0:roi_h, 0:roi_w]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    black_mask = hsv[:, :, 2] < BLACK_V_THRESHOLD

    retina_mask = (
        ((hsv[:, :, 0] >= 0) & (hsv[:, :, 0] <= 35)) &
        (hsv[:, :, 1] > 35) &
        (hsv[:, :, 2] > 50)
    ).astype(np.uint8) * 255

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (RETINA_SAFETY_PX, RETINA_SAFETY_PX))
    retina_mask = cv2.dilate(retina_mask, kernel)

    safe_mask = black_mask & (~(retina_mask > 0))
    safe_mask = safe_mask.astype(np.uint8) * 255
    safe_mask = cv2.morphologyEx(safe_mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

    # Expand mask to full image
    full_mask = np.zeros(img_original.shape[:2], dtype=np.uint8)
    full_mask[0:roi_h, 0:roi_w] = safe_mask

    # Apply only on original
    img_final = img_original.copy()
    img_final[full_mask == 255] = (0, 0, 0)

    return img_final

def process_folder(input_dir):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for f in os.listdir(input_dir):
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):
            img = anonymize_fundus(os.path.join(input_dir, f))
            if img is not None:
                cv2.imwrite(os.path.join(OUTPUT_DIR, f), img)
                print(f"✅ Anonymized: {f}")

if __name__ == "__main__":
    process_folder("/home/aiims/Desktop/Yash/DR/Phase_1/mild dr/")
