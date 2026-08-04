from flask import jsonify, request, current_app
from flask_login import current_user, login_required
from models import ViewerSettings, ViewerPresets
from auth.roles import roles_required
from utils.log_sanitize import sanitize_log_value
from . import api_bp

_VIEWER_SETTINGS_FILTERS = {
    "none",
    "redfree",
    "greenboost",
    "bluemono",
    "gray",
    "contrast",
    "enhance",
    "greenchannel",
    "blueonly",
    "redgreenfree",
    "greenfree",
}

_VIEWER_PRESET_FILTERS = {
    "none",
    "enhance",
    "redfree",
    "redfreeenhanced",
}


def _clamp_float(value, default, min_value, max_value):
    try:
        val = float(value)
    except (TypeError, ValueError):
        val = float(default)
    return max(min_value, min(max_value, val))


def _clamp_int(value, default, min_value, max_value):
    try:
        val = int(value)
    except (TypeError, ValueError):
        val = int(default)
    return max(min_value, min(max_value, val))

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
            settings.loupe_size = _clamp_int(data.get('loupe_size', 200), 200, 100, 500)
        if 'loupe_zoom' in data:
            settings.loupe_zoom = _clamp_float(data.get('loupe_zoom', 2.0), 2.0, 1.0, 4.0)
        if 'loupe_enabled' in data:
            settings.loupe_enabled = bool(data.get('loupe_enabled', False))
        if 'zoom' in data:
            settings.zoom = _clamp_int(data.get('zoom', 100), 100, 40, 500)
        if 'pan_x' in data:
            settings.pan_x = _clamp_int(data.get('pan_x', 0), 0, -600, 600)
        if 'pan_y' in data:
            settings.pan_y = _clamp_int(data.get('pan_y', 0), 0, -600, 600)
        if 'brightness' in data:
            settings.brightness = _clamp_float(data.get('brightness', 1.0), 1.0, 0.5, 5.0)
        if 'contrast' in data:
            settings.contrast = _clamp_float(data.get('contrast', 1.0), 1.0, 0.5, 5.0)
        if 'filter' in data:
            value = str(data.get('filter', 'none'))
            settings.filter = value if value in _VIEWER_SETTINGS_FILTERS else "none"

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
                'brightness': preset.brightness,
                'contrast': preset.contrast,
                'saturation': preset.saturation,
                'red_luminance': preset.red_luminance,
                'red_saturation': preset.red_saturation,
                'green_luminance': preset.green_luminance,
                'green_saturation': preset.green_saturation,
                'blue_luminance': preset.blue_luminance,
                'blue_saturation': preset.blue_saturation,
                'gamma': preset.gamma,
                'black_point': preset.black_point,
                'white_point': preset.white_point,
                'shadow_lift': preset.shadow_lift,
                'flattening': preset.flattening,
                'invert': preset.invert,
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
        preset.brightness = _clamp_float(data.get('brightness', 1.0), 1.0, 0.5, 5.0)
        preset.contrast = _clamp_float(data.get('contrast', 1.0), 1.0, 0.5, 5.0)
        preset.saturation = _clamp_float(data.get('saturation', 1.0), 1.0, 0.0, 3.0)
        preset.red_luminance = _clamp_float(data.get('red_luminance', 1.0), 1.0, 0.0, 3.0)
        preset.red_saturation = _clamp_float(data.get('red_saturation', 1.0), 1.0, 0.0, 3.0)
        preset.green_luminance = _clamp_float(data.get('green_luminance', 1.0), 1.0, 0.0, 3.0)
        preset.green_saturation = _clamp_float(data.get('green_saturation', 1.0), 1.0, 0.0, 3.0)
        preset.blue_luminance = _clamp_float(data.get('blue_luminance', 1.0), 1.0, 0.0, 3.0)
        preset.blue_saturation = _clamp_float(data.get('blue_saturation', 1.0), 1.0, 0.0, 3.0)
        preset.gamma = _clamp_float(data.get('gamma', 1.0), 1.0, 0.35, 2.5)
        preset.black_point = _clamp_float(data.get('black_point', 0.0), 0.0, -0.2, 0.25)
        preset.white_point = _clamp_float(data.get('white_point', 1.0), 1.0, 0.5, 1.2)
        preset.shadow_lift = _clamp_float(data.get('shadow_lift', 0.0), 0.0, 0.0, 1.0)
        preset.flattening = _clamp_float(data.get('flattening', 0.0), 0.0, 0.0, 1.0)
        preset.invert = data.get('invert') is True
        value = str(data.get('filter', 'none'))
        preset.filter = value if value in _VIEWER_PRESET_FILTERS else "none"

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
