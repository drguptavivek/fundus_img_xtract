# CAPTCHA Utility

## Overview

The `utils/captcha.py` module provides comprehensive CAPTCHA (Completely Automated Public Turing test to tell Computers and Humans Apart) functionality for the Fundus Image Manager application. It generates both visual and audio CAPTCHAs to enhance accessibility and security.

## Features

### Visual CAPTCHA
- Generates random alphanumeric codes with configurable length
- Excludes confusing characters (0, O, I, 1) for better readability
- Creates PNG images with customizable dimensions
- Base64 encoded for easy web integration

### Audio CAPTCHA
- Uses PiperTTS for high-quality text-to-speech synthesis
- Spells out characters individually for clarity
- Configurable speech parameters (rate, volume, etc.)
- WAV format output with base64 encoding
- Fallback handling if TTS is unavailable

### Security Features
- Session-based storage with expiration
- Configurable expiry time (default: 5 minutes)
- Case-insensitive validation
- Automatic cleanup of validated CAPTCHAs

## Dependencies

- `captcha`: For visual CAPTCHA generation
- `piper-tts`: For high-quality audio synthesis
- `flask`: For session management
- `PiperVoice`: English US Lessac Medium voice model

## Usage

### Basic CAPTCHA Generation

```python
from utils.captcha import captcha_manager

# Generate a new CAPTCHA
captcha_result = captcha_manager.generate_captcha()

# Access components
image_data = captcha_result['image']  # Base64 encoded PNG
audio_data = captcha_result.get('audio')  # Base64 encoded WAV (optional)
```

### CAPTCHA Validation

```python
# Validate user input
is_valid, message = captcha_manager.validate_captcha(user_input)

if is_valid:
    # CAPTCHA passed - proceed with action
    pass
else:
    # CAPTCHA failed - show error message
    flash(message, 'error')
```

### Manual Audio Generation

```python
# Generate audio for specific text
audio_data = captcha_manager.generate_captcha_audio("TEXT123")
```

## Configuration

### CaptchaManager Parameters

- `captcha_length`: Number of characters in CAPTCHA (default: 7)
- `expiry_minutes`: Time before CAPTCHA expires (default: 5)
- `width`: Image width in pixels (default: 160)
- `height`: Image height in pixels (default: 50)

### Audio Configuration

The audio synthesis uses PiperTTS with these settings:
- `length_scale`: 1.2 (slightly slower for clarity)
- `noise_scale`: 0.3 (less variation for consistency)
- `noise_w_scale`: 0.3 (less duration variation)
- `volume`: 0.9 (slightly lower volume)
- `normalize_audio`: True (scale to full dynamic range)

## Voice Model Setup

The system uses the `en_US-lessac-medium` PiperTTS voice model. To set up:

1. Download the voice model:
   ```bash
   uv run python -m piper.download_voices en_US-lessac-medium
   ```

2. Ensure the model files are in the project root:
   - `en_US-lessac-medium.onnx`
   - `en_US-lessac-medium.onnx.json`

### Downloading Additional Voices

PiperTTS supports various voice models for different languages and accents. To download additional voices:

1. **List available voices**:
   ```bash
   uv run python -m piper.download_voices --help
   ```

2. **Download specific voice**:
   ```bash
   # English accents
   uv run python -m piper.download_voices en_US-lessac-medium
   uv run python -m piper.download_voices en_US-lessac-low
   uv run python -m piper.download_voices en_GB-lessac-medium
   
   # Other languages
   uv run python -m piper.download_voices es_ES-lessac-medium
   uv run python -m piper.download_voices fr_FR-lessac-medium
   ```

3. **Voice model variants**:
   - **Low quality**: Smaller file size, faster synthesis
   - **Medium quality**: Balance between size and quality
   - **High quality**: Larger files, best audio quality

4. **Update configuration**:
   After downloading a new voice model, update the `model_path` in the `_init_piper_voice()` method in `utils/captcha.py`:
   ```python
   model_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'your-new-voice-model.onnx')
   ```

### Voice Model Locations

Voice models are typically downloaded to:
- **Current directory** (default): Project root where the script is run
- **Custom location**: Can be specified by modifying the `model_path` variable

The `CaptchaManager` automatically looks for the voice model in the project root directory during initialization.

## Integration with Flask Routes

```python
from flask import Blueprint, render_template, request, session
from utils.captcha import captcha_manager

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        # Generate new CAPTCHA for login form
        captcha_data = captcha_manager.generate_captcha()
        return render_template('login.html', captcha=captcha_data)
    
    # Handle login with CAPTCHA validation
    is_valid, message = captcha_manager.validate_captcha(request.form.get('captcha'))
    if not is_valid:
        flash(message, 'error')
        return redirect(url_for('auth.login'))
    
    # Continue with login process
    # ...
```

## Frontend Integration

### HTML Template Example

```html
<div class="captcha-container">
    <img src="{{ captcha.image }}" alt="CAPTCHA" class="captcha-image">
    {% if captcha.audio %}
    <audio controls class="captcha-audio">
        <source src="{{ captcha.audio }}" type="audio/wav">
        Your browser does not support the audio element.
    </audio>
    {% endif %}
    <input type="text" name="captcha" placeholder="Enter CAPTCHA code" required>
</div>
```

## Error Handling

The system includes comprehensive error handling:

- **Voice Model Loading**: Graceful fallback if PiperTTS model is unavailable
- **Audio Generation**: Returns None if synthesis fails, with detailed logging
- **File Operations**: Proper cleanup of temporary files
- **Session Management**: Handles expired or missing CAPTCHAs

## Testing

Use the provided test script to verify functionality:

```bash
uv run python test_piper_captcha.py
```

This tests:
- Voice model loading
- Audio generation
- Full CAPTCHA generation
- WAV file validation

## Migration from pyttsx3

This module was migrated from `pyttsx3` to `PiperTTS` for improved:

- **Audio Quality**: More natural speech synthesis
- **Performance**: Faster generation times
- **Reliability**: Better error handling and consistency
- **Format**: Standard WAV output instead of MP3

Key changes in the migration:
- Replaced `pyttsx3.init()` with `PiperVoice.load()`
- Changed from MP3 to WAV format
- Added synthesis configuration for clarity
- Improved error handling and logging