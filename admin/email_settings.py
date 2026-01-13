"""
Email settings administration module.
Allows admin users to manage email configuration through the web interface.
"""

from flask import render_template, request, redirect, url_for, flash, current_app, jsonify
from sqlalchemy import select
from flask_login import current_user
from auth.roles import roles_required
from utils.email_config import EmailConfigService, EmailConfigError
from utils.log_sanitize import sanitize_log_value
from utils.email_connection import test_smtp_connection
from utils.emails import send_email_sync
from models import EmailSettings, User
from db_transaction_manager import transaction_scope, get_db_session
import logging

logger = logging.getLogger(__name__)


@roles_required("admin")
def email_settings_list():
    """
    List and manage email settings.
    """
    with get_db_session() as db:
        email_settings = db.execute(
            select(EmailSettings)
            .order_by(EmailSettings.created_at.desc())
        ).scalars().all()

        # Get current active configuration source
        try:
            current_config = EmailConfigService.get_email_config()
            config_source = current_config.get('source', 'unknown')
        except EmailConfigError:
            current_config = None
            config_source = 'none'

        return render_template(
            "admin/email_settings.html",
            email_settings=email_settings,
            current_config=current_config,
            config_source=config_source
        )


@roles_required("admin")
def create_email_settings():
    """
    Create new email settings.
    """
    if request.method == "POST":
        # Get form data
        smtp_server = request.form.get("smtp_server", "").strip()
        smtp_port = request.form.get("smtp_port", "").strip()
        smtp_username = request.form.get("smtp_username", "").strip()
        smtp_password = request.form.get("smtp_password", "").strip()
        from_email = request.form.get("from_email", "").strip()
        use_tls = request.form.get("use_tls") == "on"
        use_ssl = request.form.get("use_ssl") == "on"
        verify_certificates = True
        debug_logging = request.form.get("debug_logging") == "on"
        connection_timeout = request.form.get("connection_timeout", "30").strip()

        # Validation
        errors = []

        if not smtp_server:
            errors.append("SMTP server is required.")
        if not smtp_username:
            errors.append("SMTP username is required.")
        if not smtp_password:
            errors.append("SMTP password is required.")
        if not from_email:
            errors.append("From email is required.")

        # Validate email format
        if "@" not in from_email:
            errors.append("From email format is invalid.")

        # Validate port
        try:
            smtp_port = int(smtp_port)
            if smtp_port <= 0 or smtp_port > 65535:
                errors.append("SMTP port must be between 1 and 65535.")
        except ValueError:
            errors.append("SMTP port must be a valid number.")
            smtp_port = 587

        # Validate TLS/SSL mutual exclusivity
        if use_tls and use_ssl:
            errors.append("TLS and SSL cannot be enabled simultaneously.")

        # Validate timeout
        try:
            connection_timeout = int(connection_timeout)
            if connection_timeout <= 0 or connection_timeout > 300:
                errors.append("Connection timeout must be between 1 and 300 seconds.")
        except ValueError:
            errors.append("Connection timeout must be a valid number.")
            connection_timeout = 30

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "admin/email_settings_create.html",
                form_data=request.form
            )

        # Create email settings
        try:
            created_by = current_user.id if current_user and hasattr(current_user, 'id') else None
            email_settings = EmailConfigService.create_email_settings(
                smtp_server=smtp_server,
                smtp_port=smtp_port,
                smtp_username=smtp_username,
                smtp_password=smtp_password,
                from_email=from_email,
                use_tls=use_tls,
                use_ssl=use_ssl,
                verify_certificates=verify_certificates,
                debug_logging=debug_logging,
                connection_timeout=connection_timeout,
                created_by=created_by
            )

            # Log creation (without password)
            logger.info(
                "Admin '%s' created email settings ID %d for server %s:%d",
                getattr(current_user, 'username', 'unknown'),
                email_settings,
                smtp_server,
                smtp_port
            )

            flash("Email settings created successfully!", "success")
            return redirect(url_for("admin.email_settings_list"))

        except EmailConfigError as e:
            logger.warning(
                "Email configuration error (create): %s",
                sanitize_log_value(e),
            )
            flash(str(e), "danger")
            return render_template(
                "admin/email_settings_create.html",
                form_data=request.form
            )

        except Exception as e:
            logger.error(
                "Failed to create email settings: %s",
                sanitize_log_value(e),
            )
            flash("Failed to create email settings. Please check the logs.", "danger")
            return render_template(
                "admin/email_settings_create.html",
                form_data=request.form
            )

    # GET request
    return render_template("admin/email_settings_create.html", form_data={})


@roles_required("admin")
def edit_email_settings(settings_id: int):
    """
    Edit existing email settings.
    """
    with get_db_session() as db:
        email_settings = db.get(EmailSettings, settings_id)
        if not email_settings:
            flash("Email settings not found.", "danger")
            return redirect(url_for("admin.email_settings_list"))

        if request.method == "POST":
            # Get form data
            smtp_server = request.form.get("smtp_server", "").strip()
            smtp_port = request.form.get("smtp_port", "").strip()
            smtp_username = request.form.get("smtp_username", "").strip()
            smtp_password = request.form.get("smtp_password", "").strip()
            from_email = request.form.get("from_email", "").strip()
            use_tls = request.form.get("use_tls") == "on"
            use_ssl = request.form.get("use_ssl") == "on"
            verify_certificates = True
            debug_logging = request.form.get("debug_logging") == "on"
            connection_timeout = request.form.get("connection_timeout", "30").strip()
            is_active = request.form.get("is_active") == "on"

            # Validation (same as create)
            errors = []

            if not smtp_server:
                errors.append("SMTP server is required.")
            if not smtp_username:
                errors.append("SMTP username is required.")
            if not smtp_password:
                errors.append("SMTP password is required.")
            if not from_email:
                errors.append("From email is required.")

            if "@" not in from_email:
                errors.append("From email format is invalid.")

            try:
                smtp_port = int(smtp_port)
                if smtp_port <= 0 or smtp_port > 65535:
                    errors.append("SMTP port must be between 1 and 65535.")
            except ValueError:
                errors.append("SMTP port must be a valid number.")
                smtp_port = 587

            if use_tls and use_ssl:
                errors.append("TLS and SSL cannot be enabled simultaneously.")

            try:
                connection_timeout = int(connection_timeout)
                if connection_timeout <= 0 or connection_timeout > 300:
                    errors.append("Connection timeout must be between 1 and 300 seconds.")
            except ValueError:
                errors.append("Connection timeout must be a valid number.")
                connection_timeout = 30

            if errors:
                for error in errors:
                    flash(error, "danger")
                return render_template(
                    "admin/email_settings_edit.html",
                    email_settings=email_settings,
                    form_data=request.form
                )

            try:
                updated_by = current_user.id if current_user and hasattr(current_user, 'id') else None

                # If this settings is being activated, deactivate others
                if is_active and not email_settings.is_active:
                    with transaction_scope() as tx_db:
                        existing_active = tx_db.execute(
                            select(EmailSettings).where(EmailSettings.is_active == True)
                        ).scalar_one_or_none()
                        if existing_active and existing_active.id != settings_id:
                            existing_active.is_active = False

                # Update settings
                EmailConfigService.update_email_settings(
                    settings_id=settings_id,
                    updated_by=updated_by,
                    smtp_server=smtp_server,
                    smtp_port=smtp_port,
                    smtp_username=smtp_username,
                    smtp_password=smtp_password,
                    from_email=from_email,
                    use_tls=use_tls,
                    use_ssl=use_ssl,
                    verify_certificates=verify_certificates,
                    debug_logging=debug_logging,
                    connection_timeout=connection_timeout,
                    is_active=is_active
                )

                # Log update (without password)
                logger.info(
                    "Admin '%s' updated email settings ID %d",
                    getattr(current_user, 'username', 'unknown'),
                    settings_id
                )

                flash("Email settings updated successfully!", "success")
                return redirect(url_for("admin.email_settings_list"))

            except EmailConfigError as e:
                logger.warning(
                    "Email configuration error (update): %s",
                    sanitize_log_value(e),
                )
                flash(str(e), "danger")
                return render_template(
                    "admin/email_settings_edit.html",
                    email_settings=email_settings,
                    form_data=request.form
                )

            except Exception as e:
                logger.error(
                    "Failed to update email settings: %s",
                    sanitize_log_value(e),
                )
                flash("Failed to update email settings. Please check the logs.", "danger")
                return render_template(
                    "admin/email_settings_edit.html",
                    email_settings=email_settings,
                    form_data=request.form
                )

        # GET request - show edit form
        return render_template(
            "admin/email_settings_edit.html",
            email_settings=email_settings,
            form_data={}
        )


@roles_required("admin")
def test_email_settings(settings_id: int):
    """
    Test email settings connectivity.
    """
    with get_db_session() as db:
        email_settings = db.get(EmailSettings, settings_id)
        if not email_settings:
            return jsonify({"success": False, "message": "Email settings not found"}), 404

        try:
            success, message = test_smtp_connection(email_settings)

            # Log test result (without password)
            logger.info(
                "Admin '%s' tested email settings ID %d: %s",
                getattr(current_user, 'username', 'unknown'),
                settings_id,
                "SUCCESS" if success else "FAILED"
            )

            return jsonify({
                "success": success,
                "message": message
            })

        except EmailConfigError as e:
            logger.warning("Email test config error: %s", sanitize_log_value(e))
            return jsonify({
                "success": False,
                "message": f"Configuration error: {str(e)}"
            }), 400

        except Exception as e:
            logger.error(
                "Email settings test failed: %s",
                sanitize_log_value(e),
            )
            return jsonify({
                "success": False,
                "message": "Test failed due to an internal error. Please check the logs."
            }), 500


@roles_required("admin")
def delete_email_settings(settings_id: int):
    """
    Delete email settings.
    """
    with transaction_scope() as db:
        email_settings = db.get(EmailSettings, settings_id)
        if not email_settings:
            flash("Email settings not found.", "danger")
            return redirect(url_for("admin.email_settings_list"))

        # Prevent deletion of active settings
        if email_settings.is_active:
            flash("Cannot delete active email settings. Please activate another configuration first.", "danger")
            return redirect(url_for("admin.email_settings_list"))

        try:
            db.delete(email_settings)

            # Log deletion
            logger.info(
                "Admin '%s' deleted email settings ID %d",
                getattr(current_user, 'username', 'unknown'),
                settings_id
            )

            flash("Email settings deleted successfully!", "success")

        except Exception as e:
            logger.error(
                "Failed to delete email settings: %s",
                sanitize_log_value(e),
            )
            flash("Failed to delete email settings. Please check the logs.", "danger")

        return redirect(url_for("admin.email_settings_list"))


@roles_required("admin")
def activate_email_settings(settings_id: int):
    """
    Activate email settings.
    """
    with transaction_scope() as db:
        email_settings = db.get(EmailSettings, settings_id)
        if not email_settings:
            flash("Email settings not found.", "danger")
            return redirect(url_for("admin.email_settings_list"))

        try:
            # Deactivate all other settings
            existing_active = db.execute(
                select(EmailSettings).where(EmailSettings.is_active == True)
            ).scalar_one_or_none()
            if existing_active:
                existing_active.is_active = False

            # Activate this one
            email_settings.is_active = True
            updated_by = current_user.id if current_user and hasattr(current_user, 'id') else None
            email_settings.updated_by = updated_by

            # Log activation
            logger.info(
                "Admin '%s' activated email settings ID %d",
                getattr(current_user, 'username', 'unknown'),
                settings_id
            )

            flash("Email settings activated successfully!", "success")

        except Exception as e:
            logger.error(
                "Failed to activate email settings: %s",
                sanitize_log_value(e),
            )
            flash("Failed to activate email settings. Please check the logs.", "danger")

        return redirect(url_for("admin.email_settings_list"))


@roles_required("admin")
def api_test_current_email_config():
    """
    API endpoint to test current email configuration.
    """
    try:
        success, message = EmailConfigService.test_email_connection()

        return jsonify({
            "success": success,
            "message": message
        })

    except Exception as e:
        logger.error(
            "Current email config test failed: %s",
            sanitize_log_value(e),
        )
        return jsonify({
            "success": False,
            "message": "Test failed. Please check the logs."
        }), 500


@roles_required("admin")
def send_sample_email():
    """
    Send a sample test email using the current email configuration.
    """
    try:
        # Get form data
        recipient_email = request.form.get("recipient_email", "").strip()
        subject = request.form.get("subject", "Test Email from Fundus Image Manager").strip()
        message = request.form.get("message", "").strip()

        # Validate recipient email
        if not recipient_email:
            return jsonify({
                "success": False,
                "message": "Recipient email address is required."
            }), 400

        if "@" not in recipient_email:
            return jsonify({
                "success": False,
                "message": "Invalid recipient email address format."
            }), 400

        # Use default message if empty
        if not message:
            message = """
This is a test email sent from the Fundus Image Manager system.

If you receive this email, it confirms that your email configuration is working correctly.

System Configuration:
- SMTP Server: Configured and tested
- Email Sending: Functional
- Database Integration: Active

Thank you for testing the email system.

Fundus Image Manager Team
            """.strip()

        # Get current email configuration
        try:
            email_config = EmailConfigService.get_email_config()
            if not email_config.get('smtp_server'):
                return jsonify({
                    "success": False,
                    "message": "No email configuration found. Please create and activate email settings first."
                }), 400
        except EmailConfigError:
            return jsonify({
                "success": False,
                "message": "Email configuration not available. Please check your email settings."
            }), 400

        # Send the test email
        try:
            # Create email body with custom message
            email_body = f"""
TEST EMAIL FROM FUNDUS IMAGE MANAGER

This is a test email sent from the Fundus Image Manager system.

If you receive this email, it confirms that your email configuration is working correctly.

System Configuration:
- SMTP Server: Configured and tested
- Email Sending: Functional
- Database Integration: Active

Custom Message:
{message if message else "[No custom message provided]"}

Thank you for testing the email system.

Fundus Image Manager Team
            """

            success = send_email_sync(
                to_email=recipient_email,
                subject=subject,
                body=email_body
            )

            if not success:
                return jsonify({
                    "success": False,
                    "message": "Failed to send email. Please check your email configuration and try again."
                }), 500

            # Log successful email send
            logger.info(
                "Admin '%s' sent sample test email to '%s'",
                getattr(current_user, 'username', 'unknown'),
                recipient_email
            )

            return jsonify({
                "success": True,
                "message": f"Sample email sent successfully to {recipient_email}. Please check your inbox."
            })

        except Exception as email_error:
            logger.error(
                "Failed to send sample email: %s",
                sanitize_log_value(email_error),
            )
            return jsonify({
                "success": False,
                "message": "Failed to send email. Please check the logs."
            }), 500

    except Exception as e:
        logger.error(
            "Sample email send failed: %s",
            sanitize_log_value(e),
        )
        return jsonify({
            "success": False,
            "message": "An error occurred while sending the email. Please check the logs."
        }), 500
