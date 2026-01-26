"""
S3 Configuration administration module.

Allows admin users to manage multi-tenant S3 storage configurations.
Provides hospital-scoped access control and RBAC enforcement.
"""

import logging
from datetime import datetime, timezone
from flask import render_template, request, redirect, url_for, flash, current_app, jsonify
from sqlalchemy import select, func
from flask_login import current_user
from auth.roles import roles_required
from utils.log_sanitize import sanitize_log_value
from utils.s3_encryption_nacl import generate_pepper, encrypt_secret
from utils.s3_url_signing import rotate_pepper
from utils.s3_validation import (
    validate_provider,
    validate_bucket_name,
    validate_s3_region,
    validate_endpoint_url,
    validate_s3_config_name,
    validate_fallback_policy,
    S3ValidationError,
)
from utils.s3_storage_backends import get_s3_client, check_s3_object_exists
from db_transaction_manager import get_db_session
from models import S3Config, Hospital, EncounterFile, EncounterFilePDF

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger('security.audit')


# ============================================================================
# Access Control Helpers
# ============================================================================

def _check_s3_config_access(s3_config: S3Config, user_hospitals: list[int]) -> bool:
    """
    Check if user can access S3 config.

    Access rules:
    - Master admin: Can access any config
    - Local admin: Can only access configs from their hospitals

    Args:
        s3_config: S3Config instance
        user_hospitals: List of hospital IDs user belongs to

    Returns:
        True if user can access config, False otherwise
    """
    if not user_hospitals:
        return False

    # Master admin check (all hospitals accessible)
    # This is based on the assumption that master admins have all hospitals
    # For now, we'll check if the user's hospitals include the config's hospital

    return s3_config.hospital_id in user_hospitals


def _get_user_hospitals() -> list[int]:
    """
    Get list of hospital IDs for current user for S3 config management.

    Hospital isolation: users can only manage S3 configs for their assigned hospital.
    Lab units from other hospitals allow data access but NOT config creation.
    """
    if not current_user or not current_user.is_authenticated:
        return []

    # Only return the user's assigned hospital (for isolation)
    # Lab units from other hospitals don't grant S3 config creation rights
    if hasattr(current_user, 'hospital_id') and current_user.hospital_id:
        return [current_user.hospital_id]

    return []


def _is_master_admin() -> bool:
    """
    Check if current user is master admin.

    Master admin has access to all hospitals and can set fallback policy.
    """
    if not current_user or not current_user.is_authenticated:
        return False

    # Check for master_admin role or access to all hospitals
    if hasattr(current_user, 'roles'):
        return "master_admin" in current_user.roles

    return False


# ============================================================================
# List and Create Routes
# ============================================================================

@roles_required("admin")
def s3_configs_list():
    """
    List S3 configurations (renders page template, data loaded via API).
    """
    # Get hospitals for the modal - convert to dict for JSON serialization
    with get_db_session() as db:
        user_hospitals = _get_user_hospitals()

        if not user_hospitals:
            hospitals_list = []
        else:
            hospitals = db.execute(
                select(Hospital)
                .where(Hospital.id.in_(user_hospitals))
                .order_by(Hospital.name)
            ).scalars().all()
            hospitals_list = [{'id': h.id, 'name': h.name} for h in hospitals]

    return render_template(
        "admin/s3_configs.html",
        configs_by_hospital={},  # Empty, data loaded via JS
        user_hospitals=hospitals_list,
        is_master_admin=_is_master_admin()
    )


@roles_required("admin")
def s3_config_create():
    """
    Create new S3 configuration.
    """
    with get_db_session() as db:
        user_hospitals = _get_user_hospitals()
        is_master = _is_master_admin()

        if request.method == "POST":
            # Get form data
            hospital_id = request.form.get("hospital_id", "").strip()
            provider = request.form.get("provider", "other").strip().lower()
            name = request.form.get("name", "").strip()
            bucket_name = request.form.get("bucket_name", "").strip()
            region = request.form.get("region", "").strip()
            endpoint_url = request.form.get("endpoint_url", "").strip() or None
            addressing_style = request.form.get("addressing_style", "auto").strip().lower()
            access_key = request.form.get("access_key", "").strip()
            secret_key = request.form.get("secret_key", "").strip()
            fallback_policy = request.form.get("fallback_policy", "never").strip().lower()

            # Auto-rotation settings
            auto_rotate_pepper = request.form.get("auto_rotate_pepper") == "on"
            rotation_time = request.form.get("rotation_time", "").strip() or None
            rotation_timezone = request.form.get("rotation_timezone", "").strip() or None

            # Validate
            errors = []

            # Hospital access check
            try:
                hospital_id = int(hospital_id)
                if hospital_id not in user_hospitals:
                    errors.append("You can only create configs for your hospitals.")
            except ValueError:
                errors.append("Invalid hospital selected.")

            # Provider validation
            if not validate_provider(provider):
                errors.append("Invalid storage provider.")

            # Name validation
            try:
                name = validate_s3_config_name(name)
            except S3ValidationError as e:
                errors.append(str(e))

            # Bucket name validation
            try:
                bucket_name = validate_bucket_name(bucket_name)
            except S3ValidationError as e:
                errors.append(str(e))

            # Region validation
            try:
                region = validate_s3_region(region)
            except S3ValidationError as e:
                errors.append(str(e))

            # Endpoint URL validation
            try:
                endpoint_url = validate_endpoint_url(endpoint_url)
            except S3ValidationError as e:
                errors.append(str(e))

            # Credentials validation
            if not access_key:
                errors.append("Access key is required.")
            if not secret_key:
                errors.append("Secret key is required.")

            # Addressing style validation
            if addressing_style not in ("auto", "virtual", "path"):
                errors.append("Invalid addressing style. Must be 'auto', 'virtual', or 'path'.")

            # Fallback policy (master admin only)
            try:
                if not validate_fallback_policy(fallback_policy):
                    errors.append("Invalid fallback policy.")
                if fallback_policy == "always" and not is_master:
                    errors.append("Only master admin can set fallback policy to 'always'.")
            except ValueError as e:
                errors.append(str(e))

            # Auto-rotation settings
            if auto_rotate_pepper:
                if not rotation_time:
                    errors.append("Rotation time is required when auto-rotation is enabled.")
                if not rotation_timezone:
                    errors.append("Rotation timezone is required when auto-rotation is enabled.")

            if errors:
                for error in errors:
                    flash(error, "danger")

                hospitals = db.execute(
                    select(Hospital)
                    .filter(Hospital.id.in_(user_hospitals))
                    .order_by(Hospital.name)
                ).scalars().all()

                return render_template(
                    "admin/s3_config_create.html",
                    hospitals=hospitals,
                    form_data=request.form,
                    providers=["r2", "hetzner", "aws", "gcp", "azure", "minio", "other"],
                    common_timezones=[
                        "Asia/Kolkata", "UTC", "America/New_York", "America/Chicago",
                        "America/Los_Angeles", "Europe/London", "Europe/Paris",
                        "Asia/Tokyo", "Asia/Shanghai", "Asia/Singapore"
                    ]
                )

            # Create S3 config
            try:
                # Encrypt credentials
                access_key_encrypted = encrypt_secret(access_key, hospital_id)
                secret_key_encrypted = encrypt_secret(secret_key, hospital_id)

                # Generate initial pepper
                pepper = generate_pepper()
                pepper_encrypted = encrypt_secret(pepper, hospital_id)

                # Create config
                s3_config = S3Config(
                    hospital_id=hospital_id,
                    provider=provider,
                    name=name,
                    bucket_name=bucket_name,
                    region=region,
                    endpoint_url=endpoint_url,
                    addressing_style=addressing_style,
                    access_key_encrypted=access_key_encrypted,
                    secret_key_encrypted=secret_key_encrypted,
                    url_signing_pepper=pepper_encrypted,
                    auto_rotate_pepper=auto_rotate_pepper,
                    rotation_time=rotation_time,
                    rotation_timezone=rotation_timezone,
                    fallback_policy=fallback_policy,
                    is_active=False,  # Requires activation
                    created_by_id=current_user.id,
                )

                db.add(s3_config)
                db.commit()

                audit_logger.info(
                    "S3_CONFIG_CREATED | s3_config_id=%d | hospital_id=%s | provider=%s | "
                    "bucket=%s | created_by=%s",
                    s3_config.id,
                    hospital_id,
                    provider,
                    sanitize_log_value(bucket_name),
                    getattr(current_user, 'username', 'unknown')
                )

                flash("S3 configuration created. Please test the connection before activating.", "success")
                return redirect(url_for("admin.s3_config_edit", s3_config_id=s3_config.id))

            except Exception as e:
                logger.error("Failed to create S3 config: %s", e)
                flash(f"Failed to create S3 config: {e}", "danger")

        # GET request - show form
        hospitals = db.execute(
            select(Hospital)
            .filter(Hospital.id.in_(user_hospitals))
            .order_by(Hospital.name)
        ).scalars().all()

        return render_template(
            "admin/s3_config_create.html",
            hospitals=hospitals,
            form_data={},
            providers=["r2", "hetzner", "aws", "gcp", "azure", "minio", "other"],
            common_timezones=[
                "Asia/Kolkata", "UTC", "America/New_York", "America/Chicago",
                "America/Los_Angeles", "Europe/London", "Europe/Paris",
                "Asia/Tokyo", "Asia/Shanghai", "Asia/Singapore"
            ]
        )


# ============================================================================
# Edit, Delete, Activate Routes
# ============================================================================

@roles_required("admin")
def s3_config_edit(s3_config_id: int):
    """
    Edit S3 configuration.
    """
    with get_db_session() as db:
        s3_config = db.query(S3Config).get(s3_config_id)
        if not s3_config:
            flash("S3 configuration not found.", "danger")
            return redirect(url_for("admin.s3_configs_list"))

        # Access check
        user_hospitals = _get_user_hospitals()
        if not _check_s3_config_access(s3_config, user_hospitals):
            audit_logger.warning(
                "S3_CONFIG_ACCESS_DENIED | s3_config_id=%d | user=%s | reason=wrong_hospital",
                s3_config_id,
                getattr(current_user, 'username', 'unknown')
            )
            flash("You don't have permission to access this configuration.", "danger")
            return redirect(url_for("admin.s3_configs_list"))

        is_master = _is_master_admin()

        if request.method == "POST":
            # Get form data
            name = request.form.get("name", "").strip()
            bucket_name = request.form.get("bucket_name", "").strip()
            region = request.form.get("region", "").strip()
            endpoint_url = request.form.get("endpoint_url", "").strip() or None
            addressing_style = request.form.get("addressing_style", "auto").strip().lower()
            access_key = request.form.get("access_key", "").strip()
            secret_key = request.form.get("secret_key", "").strip()

            # Auto-rotation settings
            auto_rotate_pepper = request.form.get("auto_rotate_pepper") == "on"
            rotation_time = request.form.get("rotation_time", "").strip() or None
            rotation_timezone = request.form.get("rotation_timezone", "").strip() or None

            # Validate
            errors = []

            try:
                name = validate_s3_config_name(name)
            except S3ValidationError as e:
                errors.append(str(e))

            try:
                bucket_name = validate_bucket_name(bucket_name)
            except S3ValidationError as e:
                errors.append(str(e))

            try:
                region = validate_s3_region(region)
            except S3ValidationError as e:
                errors.append(str(e))

            try:
                endpoint_url = validate_endpoint_url(endpoint_url)
            except S3ValidationError as e:
                errors.append(str(e))

            # Addressing style validation
            if addressing_style not in ("auto", "virtual", "path"):
                errors.append("Invalid addressing style. Must be 'auto', 'virtual', or 'path'.")

            if not access_key:
                errors.append("Access key is required.")
            if not secret_key:
                errors.append("Secret key is required.")

            if auto_rotate_pepper:
                if not rotation_time:
                    errors.append("Rotation time is required when auto-rotation is enabled.")
                if not rotation_timezone:
                    errors.append("Rotation timezone is required when auto-rotation is enabled.")

            if errors:
                for error in errors:
                    flash(error, "danger")
                return render_template(
                    "admin/s3_config_edit.html",
                    s3_config=s3_config,
                    hospital=db.query(Hospital).get(s3_config.hospital_id),
                    form_data=request.form,
                    providers=["r2", "hetzner", "aws", "gcp", "azure", "minio", "other"],
                    common_timezones=[
                        "Asia/Kolkata", "UTC", "America/New_York", "America/Chicago",
                        "America/Los_Angeles", "Europe/London", "Europe/Paris",
                        "Asia/Tokyo", "Asia/Shanghai", "Asia/Singapore"
                    ],
                    is_master_admin=is_master
                )

            # Update config
            try:
                # Re-encrypt credentials if changed
                if access_key and access_key != "***":
                    s3_config.access_key_encrypted = encrypt_secret(access_key, s3_config.hospital_id)
                if secret_key and secret_key != "***":
                    s3_config.secret_key_encrypted = encrypt_secret(secret_key, s3_config.hospital_id)

                s3_config.name = name
                s3_config.bucket_name = bucket_name
                s3_config.region = region
                s3_config.endpoint_url = endpoint_url
                s3_config.addressing_style = addressing_style
                s3_config.auto_rotate_pepper = auto_rotate_pepper
                s3_config.rotation_time = rotation_time
                s3_config.rotation_timezone = rotation_timezone
                s3_config.updated_at = datetime.now(timezone.utc)

                db.commit()

                audit_logger.info(
                    "S3_CONFIG_UPDATED | s3_config_id=%d | updated_by=%s",
                    s3_config_id,
                    getattr(current_user, 'username', 'unknown')
                )

                flash("S3 configuration updated.", "success")
                return redirect(url_for("admin.s3_config_edit", s3_config_id=s3_config_id))

            except Exception as e:
                logger.error("Failed to update S3 config: %s", e)
                flash(f"Failed to update S3 config: {e}", "danger")

        # GET request
        hospital = db.query(Hospital).get(s3_config.hospital_id)

        return render_template(
            "admin/s3_config_edit.html",
            s3_config=s3_config,
            hospital=hospital,
            form_data={},
            providers=["r2", "hetzner", "aws", "gcp", "azure", "minio", "other"],
            common_timezones=[
                "Asia/Kolkata", "UTC", "America/New_York", "America/Chicago",
                "America/Los_Angeles", "Europe/London", "Europe/Paris",
                "Asia/Tokyo", "Asia/Shanghai", "Asia/Singapore"
            ],
            is_master_admin=is_master
        )


@roles_required("admin")
def s3_config_delete(s3_config_id: int):
    """
    Delete S3 configuration (archive, don't actually delete).
    """
    with get_db_session() as db:
        s3_config = db.query(S3Config).get(s3_config_id)
        if not s3_config:
            flash("S3 configuration not found.", "danger")
            return redirect(url_for("admin.s3_configs_list"))

        # Access check
        user_hospitals = _get_user_hospitals()
        if not _check_s3_config_access(s3_config, user_hospitals):
            flash("You don't have permission to delete this configuration.", "danger")
            return redirect(url_for("admin.s3_configs_list"))

        # Archive instead of delete
        s3_config.is_active = False
        s3_config.is_archived = True
        s3_config.updated_at = datetime.now(timezone.utc)
        db.commit()

        audit_logger.info(
            "S3_CONFIG_ARCHIVED | s3_config_id=%d | hospital_id=%s | archived_by=%s",
            s3_config_id,
            s3_config.hospital_id,
            getattr(current_user, 'username', 'unknown')
        )

        flash("S3 configuration archived.", "success")
        return redirect(url_for("admin.s3_configs_list"))


@roles_required("admin")
def s3_config_activate(s3_config_id: int):
    """
    Activate or deactivate S3 configuration.
    """
    with get_db_session() as db:
        s3_config = db.query(S3Config).get(s3_config_id)
        if not s3_config:
            return jsonify({"success": False, "message": "Configuration not found"}), 404

        # Access check
        user_hospitals = _get_user_hospitals()
        if not _check_s3_config_access(s3_config, user_hospitals):
            return jsonify({"success": False, "message": "Access denied"}), 403

        # Toggle active status
        s3_config.is_active = not s3_config.is_active
        s3_config.updated_at = datetime.now(timezone.utc)
        db.commit()

        audit_logger.info(
            "S3_CONFIG_%s | s3_config_id=%d | hospital_id=%s | activated_by=%s",
            "ACTIVATED" if s3_config.is_active else "DEACTIVATED",
            s3_config_id,
            s3_config.hospital_id,
            getattr(current_user, 'username', 'unknown')
        )

        return jsonify({
            "success": True,
            "active": s3_config.is_active,
            "message": "Configuration activated" if s3_config.is_active else "Configuration deactivated"
        })


# ============================================================================
# Test Connection Route
# ============================================================================

@roles_required("admin")
def s3_config_test_connection(s3_config_id: int):
    """
    Test S3 connection by checking bucket access.
    """
    with get_db_session() as db:
        s3_config = db.query(S3Config).get(s3_config_id)
        if not s3_config:
            return jsonify({"success": False, "message": "Configuration not found"}), 404

        # Access check
        user_hospitals = _get_user_hospitals()
        if not _check_s3_config_access(s3_config, user_hospitals):
            return jsonify({"success": False, "message": "Access denied"}), 403

        try:
            # Create S3 client
            s3_client = get_s3_client(s3_config)

            # Test connection by checking bucket existence
            # We'll try to list objects (with max 1) to verify access
            response = s3_client.list_objects_v2(
                Bucket=s3_config.bucket_name,
                MaxKeys=1
            )

            audit_logger.info(
                "S3_CONNECTION_TEST_SUCCESS | s3_config_id=%d | hospital_id=%s | bucket=%s",
                s3_config_id,
                s3_config.hospital_id,
                sanitize_log_value(s3_config.bucket_name)
            )

            return jsonify({
                "success": True,
                "message": "Connection successful! Bucket is accessible."
            })

        except Exception as e:
            error_msg = str(e)
            logger.warning(
                "S3 connection test failed for s3_config_id=%d: %s",
                s3_config_id,
                sanitize_log_value(error_msg)
            )

            # User-friendly error messages
            if "NoSuchBucket" in error_msg:
                return jsonify({"success": False, "message": "Bucket not found. Check bucket name."})
            elif "AccessDenied" in error_msg or "403" in error_msg:
                return jsonify({"success": False, "message": "Access denied. Check credentials."})
            elif "NoCredentialsError" in error_msg:
                return jsonify({"success": False, "message": "Credentials not configured."})
            elif "EndpointConnectionError" in error_msg:
                return jsonify({"success": False, "message": "Cannot connect to endpoint. Check endpoint URL."})
            else:
                return jsonify({"success": False, "message": f"Connection failed: {error_msg}"})


# ============================================================================
# Pepper Rotation Route
# ============================================================================

@roles_required("admin")
def s3_config_rotate_pepper(s3_config_id: int):
    """
    Manually rotate URL signing pepper for S3 config.
    """
    with get_db_session() as db:
        s3_config = db.query(S3Config).get(s3_config_id)
        if not s3_config:
            return jsonify({"success": False, "message": "Configuration not found"}), 404

        # Access check
        user_hospitals = _get_user_hospitals()
        if not _check_s3_config_access(s3_config, user_hospitals):
            return jsonify({"success": False, "message": "Access denied"}), 403

        try:
            # Rotate pepper
            result = rotate_pepper(s3_config_id, auto=False)

            audit_logger.info(
                "S3_PEPPER_ROTATED_MANUAL | s3_config_id=%d | hospital_id=%s | rotated_by=%s",
                s3_config_id,
                s3_config.hospital_id,
                getattr(current_user, 'username', 'unknown')
            )

            return jsonify({
                "success": True,
                "message": "Pepper rotated successfully.",
                "pepper_rotated_at": result["pepper_rotated_at"]
            })

        except Exception as e:
            logger.error("Failed to rotate pepper for s3_config_id=%d: %s", s3_config_id, e)
            return jsonify({"success": False, "message": f"Failed to rotate pepper: {e}"}), 500


# ============================================================================
# Fallback Policy Route (Master Admin Only)
# ============================================================================

@roles_required("admin")
def s3_config_set_fallback(s3_config_id: int):
    """
    Set fallback policy for S3 config (master admin only).
    """
    # Master admin check
    if not _is_master_admin():
        return jsonify({"success": False, "message": "Only master admin can set fallback policy"}), 403

    with get_db_session() as db:
        s3_config = db.query(S3Config).get(s3_config_id)
        if not s3_config:
            return jsonify({"success": False, "message": "Configuration not found"}), 404

        if request.method == "POST":
            fallback_policy = request.form.get("fallback_policy", "").strip().lower()

            try:
                if not validate_fallback_policy(fallback_policy):
                    return jsonify({"success": False, "message": "Invalid fallback policy"}), 400

                s3_config.fallback_policy = fallback_policy
                s3_config.updated_at = datetime.now(timezone.utc)
                db.commit()

                audit_logger.info(
                    "S3_FALLBACK_POLICY_SET | s3_config_id=%d | hospital_id=%s | policy=%s | set_by=%s",
                    s3_config_id,
                    s3_config.hospital_id,
                    fallback_policy,
                    getattr(current_user, 'username', 'unknown')
                )

                flash("Fallback policy updated.", "success")
                return redirect(url_for("admin.s3_config_edit", s3_config_id=s3_config_id))

            except Exception as e:
                logger.error("Failed to set fallback policy: %s", e)
                return jsonify({"success": False, "message": f"Failed to set fallback policy: {e}"}), 500

        # GET request - show form
        return render_template(
            "admin/s3_config_fallback.html",
            s3_config=s3_config,
            hospital=db.query(Hospital).get(s3_config.hospital_id)
        )


# ============================================================================
# API Endpoints for JS-based UI
# ============================================================================

@roles_required("admin")
def s3_configs_api_list():
    """
    API endpoint to get S3 configurations as JSON for JS-based UI.
    """
    with get_db_session() as db:
        user_hospitals = _get_user_hospitals()
        is_master = _is_master_admin()

        # Query configs based on hospital access
        if is_master and len(user_hospitals) > 10:
            configs = db.execute(
                select(S3Config, Hospital)
                .join(Hospital, S3Config.hospital_id == Hospital.id)
                .order_by(S3Config.is_active.desc(), S3Config.created_at.desc())
            ).all()
        else:
            if not user_hospitals:
                configs = []
            else:
                configs = db.execute(
                    select(S3Config, Hospital)
                    .join(Hospital, S3Config.hospital_id == Hospital.id)
                    .filter(S3Config.hospital_id.in_(user_hospitals))
                    .order_by(S3Config.is_active.desc(), S3Config.created_at.desc())
                ).all()

        # Get config IDs for batch count queries
        config_ids = [config.id for config, _ in configs]

        # Batch query image counts
        image_counts = {}
        if config_ids:
            image_counts_result = db.execute(
                select(EncounterFile.s3_config_id, func.count(EncounterFile.id))
                .where(EncounterFile.s3_config_id.in_(config_ids))
                .group_by(EncounterFile.s3_config_id)
            ).all()
            image_counts = {s3_config_id: count for s3_config_id, count in image_counts_result}

        # Batch query PDF counts
        pdf_counts = {}
        if config_ids:
            pdf_counts_result = db.execute(
                select(EncounterFilePDF.s3_config_id, func.count(EncounterFilePDF.id))
                .where(EncounterFilePDF.s3_config_id.in_(config_ids))
                .group_by(EncounterFilePDF.s3_config_id)
            ).all()
            pdf_counts = {s3_config_id: count for s3_config_id, count in pdf_counts_result}

        # Build response
        configs_data = []
        for config, hospital in configs:
            configs_data.append({
                "id": config.id,
                "name": config.name,
                "provider": config.provider,
                "bucket_name": config.bucket_name,
                "region": config.region,
                "endpoint_url": config.endpoint_url,
                "is_active": config.is_active,
                "is_archived": config.is_archived,
                "fallback_policy": config.fallback_policy,
                "auto_rotate_pepper": config.auto_rotate_pepper,
                "pepper_rotated_at": config.pepper_rotated_at.isoformat() if config.pepper_rotated_at else None,
                "created_at": config.created_at.isoformat() if config.created_at else None,
                "updated_at": config.updated_at.isoformat() if config.updated_at else None,
                "hospital_id": config.hospital_id,
                "hospital_name": hospital.name,
                "image_count": image_counts.get(config.id, 0),
                "pdf_count": pdf_counts.get(config.id, 0),
                "can_delete": (image_counts.get(config.id, 0) == 0 and pdf_counts.get(config.id, 0) == 0)
            })

        return jsonify({"success": True, "configs": configs_data})


@roles_required("admin")
def s3_config_api_test_connection_modal():
    """
    Test S3 connection from modal form data (doesn't save).
    """
    hospital_id = request.form.get("hospital_id", "").strip()
    provider = request.form.get("provider", "other").strip().lower()
    bucket_name = request.form.get("bucket_name", "").strip()
    region = request.form.get("region", "").strip()
    endpoint_url = request.form.get("endpoint_url", "").strip() or None
    addressing_style = request.form.get("addressing_style", "auto").strip().lower() or "auto"
    access_key = request.form.get("access_key", "").strip()
    secret_key = request.form.get("secret_key", "").strip()

    # Validate
    errors = []
    try:
        hospital_id = int(hospital_id)
    except ValueError:
        errors.append("Invalid hospital selected.")

    if not bucket_name:
        errors.append("Bucket name is required.")
    if not region:
        errors.append("Region is required.")
    if not access_key:
        errors.append("Access key is required.")
    if not secret_key:
        errors.append("Secret key is required.")

    if errors:
        return jsonify({"success": False, "message": "; ".join(errors)})

    # Test connection by creating temporary S3 client
    try:
        from utils.s3_storage_backends import create_s3_client_from_creds
        
        s3_client = create_s3_client_from_creds(
            access_key=access_key,
            secret_key=secret_key,
            region=region,
            endpoint_url=endpoint_url,
            addressing_style=addressing_style
        )

        # Test connection by listing objects (max 1)
        response = s3_client.list_objects_v2(
            Bucket=bucket_name,
            MaxKeys=1
        )

        audit_logger.info(
            "S3_CONNECTION_TEST_MODAL | hospital_id=%s | bucket=%s | provider=%s | tested_by=%s",
            hospital_id,
            sanitize_log_value(bucket_name),
            provider,
            getattr(current_user, 'username', 'unknown')
        )

        return jsonify({"success": True, "message": "Connection successful! Bucket is accessible."})

    except Exception as e:
        error_msg = str(e)
        logger.warning("S3 connection test failed: %s", sanitize_log_value(error_msg))

        # User-friendly error messages
        if "NoSuchBucket" in error_msg:
            return jsonify({"success": False, "message": "Bucket not found. Check bucket name."})
        elif "AccessDenied" in error_msg or "403" in error_msg:
            return jsonify({"success": False, "message": "Access denied. Check credentials."})
        elif "NoCredentialsError" in error_msg:
            return jsonify({"success": False, "message": "Credentials not configured."})
        elif "EndpointConnectionError" in error_msg:
            return jsonify({"success": False, "message": "Cannot connect to endpoint. Check endpoint URL."})
        else:
            return jsonify({"success": False, "message": f"Connection failed: {error_msg}"})


@roles_required("admin")
def s3_config_api_create():
    """
    Create S3 config from modal (after successful test connection).
    """
    hospital_id = request.form.get("hospital_id", "").strip()
    provider = request.form.get("provider", "other").strip().lower()
    name = request.form.get("name", "").strip()
    bucket_name = request.form.get("bucket_name", "").strip()
    region = request.form.get("region", "").strip()
    endpoint_url = request.form.get("endpoint_url", "").strip() or None
    addressing_style = request.form.get("addressing_style", "auto").strip().lower() or "auto"
    access_key = request.form.get("access_key", "").strip()
    secret_key = request.form.get("secret_key", "").strip()

    # Validate
    errors = []
    try:
        hospital_id = int(hospital_id)
    except ValueError:
        errors.append("Invalid hospital selected.")

    if not validate_provider(provider):
        errors.append("Invalid storage provider.")

    try:
        name = validate_s3_config_name(name)
    except S3ValidationError as e:
        errors.append(str(e))

    try:
        bucket_name = validate_bucket_name(bucket_name)
    except S3ValidationError as e:
        errors.append(str(e))

    try:
        region = validate_s3_region(region)
    except S3ValidationError as e:
        errors.append(str(e))

    try:
        endpoint_url = validate_endpoint_url(endpoint_url)
    except S3ValidationError as e:
        errors.append(str(e))

    if not access_key:
        errors.append("Access key is required.")
    if not secret_key:
        errors.append("Secret key is required.")

    if errors:
        return jsonify({"success": False, "message": "; ".join(errors)})

    # Create S3 config
    with get_db_session() as db:
        try:
            # Encrypt credentials
            access_key_encrypted = encrypt_secret(access_key, hospital_id)
            secret_key_encrypted = encrypt_secret(secret_key, hospital_id)

            # Generate initial pepper
            pepper = generate_pepper()
            pepper_encrypted = encrypt_secret(pepper, hospital_id)

            # Create config
            s3_config = S3Config(
                hospital_id=hospital_id,
                provider=provider,
                name=name,
                bucket_name=bucket_name,
                region=region,
            endpoint_url=endpoint_url,
            addressing_style=addressing_style,
                access_key_encrypted=access_key_encrypted,
                secret_key_encrypted=secret_key_encrypted,
                url_signing_pepper=pepper_encrypted,
                auto_rotate_pepper=False,
                fallback_policy="never",
                is_active=False,
                created_by_id=current_user.id,
            )

            db.add(s3_config)
            db.commit()

            audit_logger.info(
                "S3_CONFIG_CREATED_MODAL | s3_config_id=%d | hospital_id=%s | provider=%s | bucket=%s | created_by=%s",
                s3_config.id,
                hospital_id,
                provider,
                sanitize_log_value(bucket_name),
                getattr(current_user, 'username', 'unknown')
            )

            return jsonify({
                "success": True,
                "message": "S3 configuration created successfully.",
                "config_id": s3_config.id
            })

        except Exception as e:
            logger.error("Failed to create S3 config: %s", e)
            return jsonify({"success": False, "message": f"Failed to create S3 config: {e}"}), 500
