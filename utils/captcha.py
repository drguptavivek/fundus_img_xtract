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
import hashlib

AUDIO_ENABLED = False  # Disabled - focusing on visual captcha


class CaptchaManager:
    """Manages CAPTCHA generation and validation."""
    
    def __init__(self):
        self.image_captcha = ImageCaptcha(width=180, height=50)
        self.session_key = 'captcha_text'
        self.session_expiry_key = 'captcha_expiry'
        self.captcha_length = 5
        self.expiry_minutes = 5
    
    
    def generate_captcha_text(self):
        """Generate a random CAPTCHA text with improved readability."""
        # Use characters that are less likely to be confused
        # Avoid: 0/O, 1/l/I, 2/Z, 5/S, etc.
        readable_chars = 'ACDEFGHJKLMNPQRSTUVWXY23456789'
        
        # Ensure we have a good mix of character types
        text_parts = []
        for i in range(self.captcha_length):
            if i < 2:  # First 2 characters: uppercase letters
                text_parts.append(random.choice('ACDEFGHJKLMNPQRSTUVWXY23456789'))
            elif i < 4:  # Next 2 characters: lowercase letters
                text_parts.append(random.choice('23456789'))
            else:  # Last character: digit
                text_parts.append(random.choice('ACDEFGHJKLMNPQRSTUVWXY23456789'))
        
        # Shuffle the positions to make it less predictable
        random.shuffle(text_parts)
        return ''.join(text_parts)
    
    def generate_captcha_image(self, text):
        """Generate CAPTCHA image as base64 string with improved accessibility."""
        # Create image with better contrast and readability
        image = self.image_captcha.generate_image(text)
        
        # Apply additional processing for better accessibility
        # Convert to RGB if needed for better processing
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Enhance contrast for better readability
        from PIL import ImageEnhance
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(1.5)  # Increase contrast by 50%
        
        # Slightly sharpen the image
        sharpener = ImageEnhance.Sharpness(image)
        image = sharpener.enhance(1.2)  # Slight sharpening
        
        # Convert image to base64 string
        buffer = io.BytesIO()
        image.save(buffer, format='PNG', optimize=True)
        image_str = base64.b64encode(buffer.getvalue()).decode()
        
        return f"data:image/png;base64,{image_str}"
    
    
    def generate_captcha(self):
        """Generate a new CAPTCHA and store it in session."""
        from datetime import datetime, timezone, timedelta
        import uuid
        import time
        import logging
        
        text = self.generate_captcha_text()
        image_data = self.generate_captcha_image(text)
        
        # Generate unique identifier for this captcha
        captcha_id = str(uuid.uuid4())
        timestamp = int(time.time() * 1000)  # Millisecond timestamp
        
        # Store in session with expiry time
        session[self.session_key] = text
        session[self.session_expiry_key] = (datetime.now(timezone.utc) + timedelta(minutes=self.expiry_minutes)).isoformat()
        session.modified = True
        
        # Log the generated CAPTCHA code for testing
        auth_logger = logging.getLogger("auth")
        auth_logger.info(f"Generated CAPTCHA - ID: {captcha_id}, Code: {text}")
        
        result = {
            'image': image_data,
            'audio_available': AUDIO_ENABLED,
            'captcha_id': captcha_id,
            'timestamp': timestamp
        }
        
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