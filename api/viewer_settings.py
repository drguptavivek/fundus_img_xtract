from flask import jsonify, request, current_app
from flask_login import current_user, login_required
from models import ViewerSettings, ViewerPresets
from auth.roles import roles_required
from utils.log_sanitize import sanitize_log_value
from . import api_bp

@api_bp.route("/viewer/settings", methods=["GET"])
@login_required
def get_viewer_settings():
    """Get current user's viewer settings."""
    from db_transaction_manager import get_db_session
    with get_db_session() as db:
        return get_viewer_settings_impl(db)

def get_viewer_settings_impl(db):
    """Implementation of get_viewer_settings with database session."""
    try:
        # Get or create viewer settings for current user
        settings = db.query(ViewerSettings).filter(ViewerSettings.user_id == current_user.id).first()
        
        if not settings:
            # Return default settings if none exist
            return jsonify({
                'loupe_size': 200,
                'loupe_zoom': 2.0,
                'loupe_enabled': False,
                'zoom': 100,
                'pan_x': 0,
                'pan_y': 0,
                'brightness': 1.0,
                'contrast': 1.0,
                'filter': 'none'
            })
        
        return jsonify({
            'loupe_size': settings.loupe_size,
            'loupe_zoom': settings.loupe_zoom,
            'loupe_enabled': settings.loupe_enabled,
            'zoom': settings.zoom,
            'pan_x': settings.pan_x,
            'pan_y': settings.pan_y,
            'brightness': settings.brightness,
            'contrast': settings.contrast,
            'filter': settings.filter
        })
    except Exception as e:
        current_app.logger.error("Failed to get viewer settings: %s", sanitize_log_value(e))
        return jsonify({'error': 'Internal server error'}), 500

@api_bp.route("/viewer/settings", methods=["POST"])
@login_required
def save_viewer_settings():
    """Save current user's viewer settings."""
    from db_transaction_manager import get_db_session
    with get_db_session() as db:
        return save_viewer_settings_impl(db)

def save_viewer_settings_impl(db):
    """Implementation of save_viewer_settings with database session."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Get or create viewer settings for current user
        settings = db.query(ViewerSettings).filter(ViewerSettings.user_id == current_user.id).first()
        
        if not settings:
            # Create new settings if none exist
            settings = ViewerSettings(user_id=current_user.id)
            db.add(settings)
        
        # Only update settings that are explicitly provided
        if 'loupe_size' in data:
            settings.loupe_size = int(data.get('loupe_size', 200))
        if 'loupe_zoom' in data:
            settings.loupe_zoom = float(data.get('loupe_zoom', 2.0))
        if 'loupe_enabled' in data:
            settings.loupe_enabled = bool(data.get('loupe_enabled', False))
        if 'zoom' in data:
            settings.zoom = int(data.get('zoom', 100))
        if 'pan_x' in data:
            settings.pan_x = int(data.get('pan_x', 0))
        if 'pan_y' in data:
            settings.pan_y = int(data.get('pan_y', 0))
        if 'brightness' in data:
            settings.brightness = float(data.get('brightness', 1.0))
        if 'contrast' in data:
            settings.contrast = float(data.get('contrast', 1.0))
        if 'filter' in data:
            settings.filter = str(data.get('filter', 'none'))

        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error("Failed to save viewer settings: %s", sanitize_log_value(e))
        return jsonify({'error': 'Internal server error'}), 500

@api_bp.route("/viewer/presets", methods=["GET"])
@login_required
def get_viewer_presets():
    """Get current user's viewer presets."""
    from db_transaction_manager import get_db_session
    with get_db_session() as db:
        return get_viewer_presets_impl(db)

def get_viewer_presets_impl(db):
    """Implementation of get_viewer_presets with database session."""
    try:
        # Get all presets for current user
        presets = db.query(ViewerPresets).filter(ViewerPresets.user_id == current_user.id).all()
        
        # Format as a dictionary with slot numbers as keys
        presets_dict = {}
        for preset in presets:
            presets_dict[preset.slot_number] = {
                'id': preset.id,
                'name': preset.name,
                'loupe_size': preset.loupe_size,
                'loupe_zoom': preset.loupe_zoom,
                'loupe_enabled': preset.loupe_enabled,
                'zoom': preset.zoom,
                'pan_x': preset.pan_x,
                'pan_y': preset.pan_y,
                'brightness': preset.brightness,
                'contrast': preset.contrast,
                'filter': preset.filter
            }
        
        return jsonify(presets_dict)
    except Exception as e:
        current_app.logger.error("Failed to get viewer presets: %s", sanitize_log_value(e))
        return jsonify({'error': 'Internal server error'}), 500

@api_bp.route("/viewer/presets/<int:slot_number>", methods=["POST"])
@login_required
def save_viewer_preset(slot_number):
    """Save a viewer preset for the current user in the specified slot (1-5)."""
    from db_transaction_manager import get_db_session
    with get_db_session() as db:
        return save_viewer_preset_impl(db, slot_number)

def save_viewer_preset_impl(db, slot_number):
    """Implementation of save_viewer_preset with database session."""
    try:
        if slot_number < 1 or slot_number > 5:
            return jsonify({'error': 'Slot number must be between 1 and 5'}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Get or create preset for the specified slot
        preset = db.query(ViewerPresets).filter(
            ViewerPresets.user_id == current_user.id,
            ViewerPresets.slot_number == slot_number
        ).first()
        
        if not preset:
            # Create new preset if none exists
            preset = ViewerPresets(
                user_id=current_user.id,
                slot_number=slot_number
            )
            db.add(preset)
        
        # Update preset with provided data
        preset.name = data.get('name')
        preset.loupe_size = int(data.get('loupe_size', 200))
        preset.loupe_zoom = float(data.get('loupe_zoom', 2.0))
        preset.loupe_enabled = bool(data.get('loupe_enabled', False))
        preset.zoom = int(data.get('zoom', 100))
        preset.pan_x = int(data.get('pan_x', 0))
        preset.pan_y = int(data.get('pan_y', 0))
        preset.brightness = float(data.get('brightness', 1.0))
        preset.contrast = float(data.get('contrast', 1.0))
        preset.filter = str(data.get('filter', 'none'))

        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error("Failed to save viewer preset: %s", sanitize_log_value(e))
        return jsonify({'error': 'Internal server error'}), 500

@api_bp.route("/viewer/presets/<int:slot_number>", methods=["DELETE"])
@login_required
def delete_viewer_preset(slot_number):
    """Delete a viewer preset for the current user in the specified slot (1-5)."""
    from db_transaction_manager import get_db_session
    with get_db_session() as db:
        return delete_viewer_preset_impl(db, slot_number)

def delete_viewer_preset_impl(db, slot_number):
    """Implementation of delete_viewer_preset with database session."""
    try:
        if slot_number < 1 or slot_number > 5:
            return jsonify({'error': 'Slot number must be between 1 and 5'}), 400
        
        # Find and delete the preset
        preset = db.query(ViewerPresets).filter(
            ViewerPresets.user_id == current_user.id,
            ViewerPresets.slot_number == slot_number
        ).first()
        
        if preset:
            db.delete(preset)
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Preset not found'}), 404
    except Exception as e:
        current_app.logger.error("Failed to delete viewer preset: %s", sanitize_log_value(e))
        return jsonify({'error': 'Internal server error'}), 500