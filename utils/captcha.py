"""
CAPTCHA utility module for generating and validating CAPTCHAs. 
"""

import os
import io
import base64
import random
import string
import tempfile
import wave
from captcha.image import ImageCaptcha
from flask import session
from piper import PiperVoice, SynthesisConfig

AUDIO_ENABLED = True


class CaptchaManager:
    """Manages CAPTCHA generation and validation."""
    
    def __init__(self):
        self.image_captcha = ImageCaptcha(width=180, height=50)
        self.session_key = 'captcha_text'
        self.session_expiry_key = 'captcha_expiry'
        self.captcha_length = 5
        self.expiry_minutes = 5
        self.piper_voice = None
        self._init_piper_voice()
    
    def _init_piper_voice(self):
        """Initialize PiperTTS voice model."""
        try:
            # Path to the downloaded voice model
            model_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'en_US-lessac-medium.onnx')
            if os.path.exists(model_path):
                self.piper_voice = PiperVoice.load(model_path)
                print("PiperTTS voice model loaded successfully")
            else:
                print(f"PiperTTS voice model not found at {model_path}")
                self.piper_voice = None
        except Exception as e:
            print(f"Failed to initialize PiperTTS: {e}")
            self.piper_voice = None
    
    def generate_captcha_text(self):
        """Generate a random CAPTCHA text."""
        # Use uppercase letters and digits to avoid confusion
        chars = string.ascii_uppercase + string.digits
        # Remove confusing characters like 0, O, I, 1
        chars = chars.replace('0', '').replace('O', '').replace('I', '').replace('1', '')
        return ''.join(random.choice(chars) for _ in range(self.captcha_length))
    
    def generate_captcha_image(self, text):
        """Generate CAPTCHA image as base64 string."""
        image = self.image_captcha.generate_image(text)
        
        # Convert image to base64 string
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        image_str = base64.b64encode(buffer.getvalue()).decode()
        
        return f"data:image/png;base64,{image_str}"
    
    def generate_captcha_audio(self, text):
        """Generate CAPTCHA audio as base64 string using PiperTTS."""
        if not AUDIO_ENABLED or self.piper_voice is None:
            return None
            
        try:
            # Create temporary file for audio
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name
                
            # Convert text to speech-friendly format (spell out characters)
            speech_text = ' '.join(list(text))
            
            # Configure synthesis for clearer CAPTCHA audio
            syn_config = SynthesisConfig(
                length_scale=2,  # Slightly slower for clarity
                noise_scale=0.2,    # Less variation for consistency
                noise_w_scale=0.3,  # Less duration variation
                volume=0.6,         # Slightly lower volume
                normalize_audio=True
            )
            
            # Generate audio using PiperTTS
            with wave.open(temp_path, 'wb') as wav_file:
                self.piper_voice.synthesize_wav(speech_text, wav_file, syn_config=syn_config)
            
            # Check if file was created and has content
            if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
                print("Audio file was not created or is empty")
                return None
            
            # Read audio file and convert to base64
            with open(temp_path, 'rb') as audio_file:
                audio_data = audio_file.read()
                if len(audio_data) == 0:
                    print("Generated audio file is empty")
                    return None
                audio_str = base64.b64encode(audio_data).decode()
                
            # Clean up temporary file
            os.unlink(temp_path)
            
            return f"data:audio/wav;base64,{audio_str}"
            
        except Exception as e:
            print(f"Error generating audio CAPTCHA with PiperTTS: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def generate_captcha(self):
        """Generate a new CAPTCHA and store it in session."""
        from datetime import datetime, timezone, timedelta
        
        text = self.generate_captcha_text()
        image_data = self.generate_captcha_image(text)
        audio_data = self.generate_captcha_audio(text)
        
        # Store in session with expiry time
        session[self.session_key] = text
        session[self.session_expiry_key] = (datetime.now(timezone.utc) + timedelta(minutes=self.expiry_minutes)).isoformat()
        session.modified = True
        
        result = {
            'image': image_data,
            'audio_available': AUDIO_ENABLED
        }
        
        if audio_data:
            result['audio'] = audio_data
            
        return result
    
    def validate_captcha(self, user_input):
        """Validate user input against stored CAPTCHA."""
        from datetime import datetime, timezone
        
        if not user_input:
            return False, "Please enter the CAPTCHA code."
        
        # Get stored CAPTCHA from session
        stored_text = session.get(self.session_key)
        expiry_str = session.get(self.session_expiry_key)
        
        if not stored_text or not expiry_str:
            return False, "CAPTCHA has expired. Please try again."
        
        # Check if CAPTCHA has expired
        try:
            expiry_time = datetime.fromisoformat(expiry_str)
            current_time = datetime.now(timezone.utc)
            
            # Ensure both datetimes are timezone-aware
            if expiry_time.tzinfo is None:
                expiry_time = expiry_time.replace(tzinfo=timezone.utc)
            if current_time.tzinfo is None:
                current_time = current_time.replace(tzinfo=timezone.utc)
            
            if current_time > expiry_time:
                # Clear expired CAPTCHA
                self.clear_captcha()
                return False, "CAPTCHA has expired. Please try again."
        except (ValueError, TypeError):
            # Invalid expiry format
            self.clear_captcha()
            return False, "CAPTCHA has expired. Please try again."
        
        # Validate input (case insensitive)
        if user_input.upper() != stored_text.upper():
            return False, "Invalid CAPTCHA. Please try again."
        
        # Clear validated CAPTCHA to prevent reuse
        self.clear_captcha()
        return True, "CAPTCHA validated successfully."
    
    def clear_captcha(self):
        """Clear CAPTCHA from session."""
        session.pop(self.session_key, None)
        session.pop(self.session_expiry_key, None)
        session.modified = True


# Global CAPTCHA manager instance
captcha_manager = CaptchaManager()