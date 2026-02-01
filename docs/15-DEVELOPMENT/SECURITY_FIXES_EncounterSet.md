# EncounterSet Security Fixes - Implementation Guide

**Last Updated**: February 1, 2025
**Status**: Ready for Implementation

---

## Quick Reference: Critical Fixes

| Priority | Issue | Est. Time | File | Blocker? |
|----------|-------|-----------|------|----------|
| P0 | File extension validation | 1h | api/encounter_set.py | YES |
| P0 | CSRF protection | 2h | Multiple | YES |
| P0 | Hospital scoping | 2h | verify_encounter_set/ | YES |
| P0 | Type confusion fix | 1h | api/encounter_set.py | NO |
| P1 | Edit file feature | 3-5h | verify_encounter_set/ | YES |
| P1 | File size limits | 0.5h | api/encounter_set.py | NO |
| P1 | File content validation | 1.5h | api/encounter_set.py | NO |
| P1 | Input validation | 1h | verify_encounter_set/ | NO |

---

## Fix #1: File Extension Validation (CRITICAL)

**File**: `api/encounter_set.py`

**Current Code** (lines 198-210):
```python
# INSECURE - accepts any extension
ext = os.path.splitext(file.filename)[1]
img_uuid = str(uuid4())
filename = f"{img_uuid}{ext}"

# Store file with user-provided extension!
file.save(os.path.join(save_path, filename))
```

**Fixed Code**:
```python
# Whitelist allowed extensions
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp'}

# Get extension from user input
ext = os.path.splitext(file.filename)[1].lower()

# Validate it's allowed
if ext not in ALLOWED_IMAGE_EXTENSIONS:
    logger.warning(
        "Upload rejected: invalid file extension",
        extra={
            'extension': ext,
            'hospital_id': hospital_id,
            'ip': request.remote_addr,
        }
    )
    return jsonify({
        "error": "Invalid file format",
        "message": "Only JPG, PNG, GIF, BMP files are allowed"
    }), 400

# Store with a safe extension (always use jpg to prevent execution)
# This ensures files can't be executed even if uploaded to wrong directory
safe_filename = f"{uuid4()}.jpg"

# Construct path safely
folder_rel = f"files/encounter_sets/{date_str}/{encounter.id}"
save_path = os.path.join(current_app.root_path, folder_rel)

# Verify path is within base directory
real_path = os.path.realpath(save_path)
base_path = os.path.realpath(current_app.root_path)
if not real_path.startswith(base_path):
    return jsonify({"error": "Invalid storage path"}), 500

os.makedirs(save_path, exist_ok=True)
file.save(os.path.join(save_path, safe_filename))

# Store original filename separately for reference (not for serving)
img.original_filename = file.filename  # User-provided name only
img.uuid = uuid4()
```

**Testing**:
```python
def test_file_extension_validation():
    """Test that invalid file extensions are rejected"""
    token = generate_mobile_token(1, 5, [1])

    # Test valid extensions
    for ext in ['.jpg', '.jpeg', '.png', '.gif']:
        response = client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {token}'},
            data={
                'patient_id': 'TEST',
                'patient_name': 'Test',
                'spatial_position': '5',
                'file': (f'image{ext}', b'fake image data')
            }
        )
        assert response.status_code == 201, f"Valid extension {ext} should succeed"

    # Test invalid extensions
    for ext in ['.php', '.exe', '.sh', '.bat', '.aspx', '.jsp']:
        response = client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {token}'},
            data={
                'patient_id': 'TEST',
                'patient_name': 'Test',
                'spatial_position': '5',
                'file': (f'shell{ext}', b'<?php system($_GET["cmd"]); ?>')
            }
        )
        assert response.status_code == 400, f"Invalid extension {ext} should fail"
        assert 'Invalid file format' in response.json['error']
```

---

## Fix #2: CSRF Protection (CRITICAL)

**Files to Update**:
1. `api/encounter_set.py` - Lines 79 (position update)
2. `verify_encounter_set/routes.py` - Lines 49, 87, 127, 177 (all POST routes)
3. `grading/encounter_set_grading.py` - Line 92 (grade submit)

**Step 1: Add CSRF decorator to routes**

```python
# File: api/encounter_set.py - Line 79

from flask_wtf.csrf import csrf_protect  # Add import

@api_bp.route('/v1/encounter-set/image/<uuid>/position', methods=['POST'])
@login_required
@csrf_protect  # Add this line
def update_image_position(uuid):
    """Update the spatial position of an image."""
    # ... existing code ...
```

```python
# File: verify_encounter_set/routes.py - Lines 49, 87, 127, 177

from flask_wtf.csrf import csrf_protect  # Add import

@bp.route("/update_position", methods=["POST"])
@login_required
@csrf_protect
def update_position():
    # ... existing code ...

@bp.route("/finalize/<uuid>", methods=["POST"])
@login_required
@csrf_protect
def finalize(uuid):
    # ... existing code ...

@bp.route("/<uuid>", methods=["GET"])  # Don't protect GET
@login_required
def edit(uuid):
    # ... existing code ...

@bp.route("/save_edit/<uuid>", methods=["POST"])
@login_required
@csrf_protect
def save_edit(uuid):
    # ... existing code ...
```

```python
# File: grading/encounter_set_grading.py - Line 92

from flask_wtf.csrf import csrf_protect

@bp.route('/encounter_set/submit', methods=['POST'])
@login_required
@csrf_protect
def submit_encounter_set_grade():
    # ... existing code ...
```

**Step 2: Update HTML forms to include CSRF tokens**

```html
<!-- In verification template -->
<form method="POST" action="/verify-encounter-set/save_edit/{{ uuid }}">
    {{ csrf_token() }}  <!-- Add this line -->

    <div id="crop-container">
        <!-- crop UI elements -->
    </div>

    <button type="submit">Save Edit</button>
</form>

<!-- For API calls from JavaScript -->
<script>
const token = document.querySelector('meta[name="csrf-token"]').content;

// When making AJAX calls
fetch('/v1/encounter-set/image/uuid/position', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': token  // Add CSRF token
    },
    body: JSON.stringify({'spatial_position': 5})
});
</script>
```

**Testing**:
```python
def test_csrf_protection():
    """Test CSRF protection on POST routes"""
    user = create_user()
    encounter = create_encounter()
    image = create_encounter_image(encounter)

    # POST without CSRF token should fail
    response = client.post(
        f'/v1/encounter-set/image/{image.uuid}/position',
        json={'spatial_position': 7},
        headers={'Cookie': f'session={get_session_token(user)}'} # Session present but no CSRF
    )
    assert response.status_code == 403, "Should reject POST without CSRF token"

    # POST with CSRF token should succeed
    csrf_token = get_csrf_token(user)
    response = client.post(
        f'/v1/encounter-set/image/{image.uuid}/position',
        json={'spatial_position': 7},
        headers={
            'Cookie': f'session={get_session_token(user)}',
            'X-CSRFToken': csrf_token
        }
    )
    assert response.status_code == 200, "Should accept POST with CSRF token"
```

---

## Fix #3: Hospital Scoping (CRITICAL)

**File**: `verify_encounter_set/routes.py`

**Current Code** (lines 24-47):
```python
@bp.route("/<uuid>", methods=["GET"])
@login_required
@roles_required("admin", "local_admin", "optometrist")
def verify_encounter(uuid):
    with transaction_scope() as db:
        encounter = db.query(PatientEncounters).filter_by(uuid=uuid).first()  # ❌ NO SCOPING!
        # ... rest of code ...
```

**Fixed Code**:
```python
from sqlalchemy import select
from utils.hospital_scoping import apply_scoping

@bp.route("/<uuid>", methods=["GET"])
@login_required
@roles_required("admin", "local_admin", "optometrist")
def verify_encounter(uuid):
    with transaction_scope() as db:
        # Build scoped query
        query = select(PatientEncounters).where(PatientEncounters.uuid == uuid)
        query = apply_scoping(query, PatientEncounters, current_user, "view")

        # Execute scoped query
        encounter = db.execute(query).scalar_one_or_none()

        if not encounter:
            flash("Encounter not found", "error")
            return redirect(url_for("verify_encounter_set.index"))

        # ... rest of code ...
```

**Apply to ALL routes that fetch PatientEncounters**:

Lines to fix:
- Line 30: `verify_encounter()` - add scoping
- Line 69: `update_position()` - add scoping
- Line 127: `edit()` - add scoping
- Line 177: `save_edit()` - add scoping

**Example fix for update_position**:
```python
@bp.route("/update_position", methods=["POST"])
@login_required
@csrf_protect
def update_position():
    with transaction_scope() as db:
        image_uuid = request.json.get("image_uuid")
        new_position = request.json.get("position")

        # Get image with scoping
        image = db.query(EncounterSetImage).filter_by(uuid=image_uuid).first()
        if not image:
            return jsonify({"error": "Image not found"}), 404

        # Get encounter and apply scoping
        query = select(PatientEncounters).where(
            PatientEncounters.id == image.patient_encounter_id
        )
        query = apply_scoping(query, PatientEncounters, current_user, "edit")
        encounter = db.execute(query).scalar_one_or_none()

        if not encounter:
            return jsonify({"error": "Access denied"}), 403

        # Now safe to proceed
        # ... rest of code ...
```

**Testing**:
```python
def test_hospital_scoping_in_verify():
    """Test that users can't access encounters from other hospitals"""
    hospital_a_admin = create_user(hospital=1, role='admin')
    hospital_b_admin = create_user(hospital=2, role='admin')
    hospital_b_encounter = create_encounter(hospital=2, uuid='b-uuid')

    # Hospital A admin tries to access Hospital B encounter
    response = client.get(
        f'/verify-encounter-set/b-uuid',
        user=hospital_a_admin
    )

    # Should get 404, not be able to access
    assert response.status_code == 404, "Should deny cross-hospital access"
    assert "not found" in response.data.decode().lower()
```

---

## Fix #4: Type Confusion Validation (CRITICAL)

**File**: `api/encounter_set.py` - Lines 84-86

**Current Code**:
```python
pos_raw = request.json.get("spatial_position")
if pos_raw is None or not (1 <= int(pos_raw) <= 9):  # ❌ int() before validation!
    return jsonify({"error": "Invalid spatial_position"}), 400
```

**Fixed Code**:
```python
pos_raw = request.json.get("spatial_position")

# Null check first
if pos_raw is None:
    return jsonify({"error": "Missing spatial_position"}), 400

# Then type check
try:
    spatial_position = int(pos_raw)
except (ValueError, TypeError):
    return jsonify({
        "error": "Invalid spatial_position",
        "message": "Must be an integer between 1 and 9"
    }), 400

# Then range check
if not (1 <= spatial_position <= 9):
    return jsonify({
        "error": "Invalid spatial_position",
        "message": "Must be between 1 and 9"
    }), 400

# Use validated value
collision = db.query(EncounterSetImage).filter(
    and_(
        EncounterSetImage.patient_encounter_id == img.patient_encounter_id,
        EncounterSetImage.spatial_position == spatial_position,
        EncounterSetImage.id != img.id
    )
).first()
```

**Testing**:
```python
def test_spatial_position_validation():
    """Test position validation handles all types correctly"""
    token = generate_mobile_token(1, 5, [1])

    # Valid positions
    for pos in [1, 5, 9]:
        response = client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {token}'},
            data={...,'spatial_position': str(pos)}
        )
        assert response.status_code == 201

    # Invalid: string
    response = client.post(
        '/api/v1/encounter-set/upload',
        headers={'Authorization': f'Bearer {token}'},
        data={...,'spatial_position': 'invalid'}
    )
    assert response.status_code == 400
    assert 'integer' in response.json['message'].lower()

    # Invalid: out of range
    for pos in [0, 10, -1, 999]:
        response = client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {token}'},
            data={...,'spatial_position': str(pos)}
        )
        assert response.status_code == 400
        assert 'between 1 and 9' in response.json['message']

    # Invalid: missing
    response = client.post(
        '/api/v1/encounter-set/upload',
        headers={'Authorization': f'Bearer {token}'},
        data={...}  # No spatial_position
    )
    assert response.status_code == 400
    assert 'Missing' in response.json['error']
```

---

## Fix #5: Edited File Feature (CRITICAL)

**File**: `verify_encounter_set/routes.py` - Lines 177-214

### Option A: Implement Actual Image Processing

```python
from PIL import Image
import pytesseract
import logging
from io import BytesIO

logger = logging.getLogger('verify_encounter_set')

@bp.route("/save_edit/<uuid>", methods=["POST"])
@login_required
@csrf_protect
def save_edit(uuid):
    """Save edited (anonymized) version of encounter image"""
    with transaction_scope() as db:
        # Get image with authorization check
        img = db.query(EncounterSetImage).filter_by(uuid=uuid).first()
        if not img:
            return jsonify({"error": "Image not found"}), 404

        # Get encounter and verify access
        query = select(PatientEncounters).where(
            PatientEncounters.id == img.patient_encounter_id
        )
        query = apply_scoping(query, PatientEncounters, current_user, "edit")
        encounter = db.execute(query).scalar_one_or_none()
        if not encounter:
            return jsonify({"error": "Access denied"}), 403

        # Validate request data
        data = request.json or {}
        crop = data.get('crop')
        blur_regions = data.get('blur_regions', [])

        if not crop:
            return jsonify({"error": "Missing crop data"}), 400

        try:
            x = int(crop.get('x', 0))
            y = int(crop.get('y', 0))
            w = int(crop.get('width', 0))
            h = int(crop.get('height', 0))
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid crop coordinates"}), 400

        if x < 0 or y < 0 or w <= 0 or h <= 0:
            return jsonify({"error": "Invalid crop dimensions"}), 400

        try:
            # Load original image
            original_path = os.path.join(
                current_app.root_path,
                img.folder_rel,
                img.original_filename
            )

            if not os.path.exists(original_path):
                logger.error(f"Original file not found: {original_path}")
                return jsonify({"error": "Original file not found"}), 404

            with Image.open(original_path) as original_img:
                # Create edited copy
                edited = original_img.copy()

                # Apply crop
                edited = edited.crop((x, y, x + w, y + h))

                # Apply blur to specified regions (e.g., text areas with PII)
                from PIL import ImageFilter
                for region in blur_regions:
                    try:
                        rx = int(region['x'])
                        ry = int(region['y'])
                        rw = int(region['width'])
                        rh = int(region['height'])

                        # Extract and blur region
                        region_box = (rx, ry, rx + rw, ry + rh)
                        region_img = edited.crop(region_box)
                        region_img = region_img.filter(ImageFilter.GaussianBlur(radius=15))
                        edited.paste(region_img, region_box)
                    except (ValueError, KeyError):
                        logger.warning(f"Invalid blur region: {region}")
                        continue

                # Save edited image
                edited_filename = f"{img.uuid}_edited.jpg"
                edited_path = os.path.join(
                    current_app.root_path,
                    img.folder_rel,
                    edited_filename
                )

                edited.save(edited_path, 'JPEG', quality=95)

                # NOW mark as anonymized (after actually processing)
                img.edited_filename = edited_filename
                img.is_reviewed = True
                img.is_anonymized = True
                img.anonymized_at = utcnow()
                db.commit()

                audit_logger.info(
                    "Image anonymized",
                    extra={
                        'image_uuid': img.uuid,
                        'encounter_uuid': encounter.uuid,
                        'user_id': current_user.id,
                        'ip': request.remote_addr,
                    }
                )

                return jsonify({
                    "message": "Image anonymized successfully",
                    "edited_filename": edited_filename
                }), 200

        except Exception as e:
            logger.error(f"Error processing image: {str(e)}", exc_info=True)
            return jsonify({"error": "Failed to process image"}), 500
```

### Option B: Disable Feature (If Not Critical)

```python
@bp.route("/save_edit/<uuid>", methods=["POST"])
@login_required
@csrf_protect
def save_edit(uuid):
    """Image editing not yet implemented"""
    return jsonify({
        "error": "Not implemented",
        "message": "Image editing feature is not yet available"
    }), 501
```

---

## Fix #6: File Size Limits (HIGH)

**File**: `api/encounter_set.py` - Lines 195-210

```python
from werkzeug.utils import secure_filename

MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

@api_bp.route('/v1/encounter-set/upload', methods=['POST'])
@token_auth_required
@api_rate_limit("60 per minute")
def upload_encounter_set_image():
    """Upload a single image for an encounter set"""
    # ... existing code to get file ...

    # Check file size BEFORE processing
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Reset to beginning

    if file_size > MAX_FILE_SIZE_BYTES:
        logger.warning(
            f"Upload rejected: file too large ({file_size} bytes)",
            extra={'hospital_id': hospital_id, 'ip': request.remote_addr}
        )
        return jsonify({
            "error": "File too large",
            "message": f"Maximum file size is {MAX_FILE_SIZE_MB}MB",
            "max_size": MAX_FILE_SIZE_BYTES,
            "actual_size": file_size
        }), 413

    # ... rest of code ...
```

---

## Fix #7: File Content Validation (HIGH)

**File**: `api/encounter_set.py` - Lines 195-210

```python
from PIL import Image
from io import BytesIO

ALLOWED_IMAGE_FORMATS = {'JPEG', 'PNG', 'GIF', 'BMP'}
MAX_DIMENSION = 10000

@api_bp.route('/v1/encounter-set/upload', methods=['POST'])
@token_auth_required
@api_rate_limit("60 per minute")
def upload_encounter_set_image():
    """Upload a single image for an encounter set"""
    # ... existing code ...

    try:
        # Read file content
        file_content = file.read()
        file.seek(0)

        # Validate it's actually an image
        try:
            with Image.open(BytesIO(file_content)) as img:
                # Verify format
                if img.format.upper() not in ALLOWED_IMAGE_FORMATS:
                    return jsonify({
                        "error": "Invalid image format",
                        "message": f"Format {img.format} not supported"
                    }), 400

                # Check dimensions (prevent decompression bombs)
                width, height = img.size
                if width > MAX_DIMENSION or height > MAX_DIMENSION:
                    return jsonify({
                        "error": "Image too large",
                        "message": f"Max dimensions are {MAX_DIMENSION}x{MAX_DIMENSION}"
                    }), 400

                # Verify image is valid (will raise if corrupted)
                img.verify()

        except Exception as e:
            logger.warning(f"Invalid image file: {str(e)}")
            return jsonify({
                "error": "Invalid image file",
                "message": "File is not a valid image"
            }), 400

        # Now save validated content
        filename = f"{uuid4()}.jpg"
        file_obj = BytesIO(file_content)
        file_obj.save(os.path.join(save_path, filename))

    except Exception as e:
        logger.error(f"Error validating image: {str(e)}", exc_info=True)
        return jsonify({"error": "Failed to process image"}), 500
```

---

## Fix #8: Input Validation Schema (HIGH)

**File**: `verify_encounter_set/routes.py` - Lines 177-190

```python
from marshmallow import Schema, fields, validate, ValidationError, post_load

class CropCoordinates(Schema):
    x = fields.Int(required=True, validate=validate.Range(min=0))
    y = fields.Int(required=True, validate=validate.Range(min=0))
    width = fields.Int(required=True, validate=validate.Range(min=1))
    height = fields.Int(required=True, validate=validate.Range(min=1))

class ImageEditSchema(Schema):
    crop = fields.Nested(CropCoordinates, required=True)
    blur_regions = fields.List(fields.Nested(CropCoordinates), required=False)

@bp.route("/save_edit/<uuid>", methods=["POST"])
@login_required
@csrf_protect
def save_edit(uuid):
    """Save edited image"""
    schema = ImageEditSchema()

    # Validate request data
    try:
        data = schema.load(request.json or {})
    except ValidationError as err:
        return jsonify({
            "error": "Invalid request",
            "details": err.messages
        }), 400

    crop = data.get('crop')
    blur_regions = data.get('blur_regions', [])

    # Now all fields are guaranteed to be valid
    # ... rest of code ...
```

---

## Summary Checklist

- [ ] **Fix #1**: File extension validation (1h)
- [ ] **Fix #2**: CSRF protection (2h)
- [ ] **Fix #3**: Hospital scoping (2h)
- [ ] **Fix #4**: Type confusion (1h)
- [ ] **Fix #5**: Edited file feature (3-5h)
- [ ] **Fix #6**: File size limits (0.5h)
- [ ] **Fix #7**: File content validation (1.5h)
- [ ] **Fix #8**: Input validation (1h)

**Total Estimated Time**: 12-17 hours

---

## Testing Command

```bash
# Run all EncounterSet tests after fixes
docker-compose exec web uv run pytest \
    tests/unit/encounter_set/ \
    tests/integration/encounter_set/ \
    -v --cov=api/encounter_set.py \
    --cov=verify_encounter_set/ \
    --cov=grading/encounter_set_grading.py

# Run security tests specifically
docker-compose exec web uv run pytest \
    tests/security/test_encounter_set_security.py \
    -v
```

---

## Code Review Checklist (Post-Fix)

Before merging fixes:

- [ ] All 8 fixes implemented and tested
- [ ] No file extensions accepted except .jpg/.png/.gif/.bmp
- [ ] CSRF tokens required on all POST routes
- [ ] Hospital scoping applied to all encounter queries
- [ ] Type validation before type coercion
- [ ] File sizes validated before saving
- [ ] File content validated (PIL verification)
- [ ] Input validation schemas in place
- [ ] All tests passing
- [ ] Security tests added and passing

