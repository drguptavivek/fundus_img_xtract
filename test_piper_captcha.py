#!/usr/bin/env python3
"""Test script to verify PiperTTS integration with CAPTCHA."""

import os
import sys
import base64
import tempfile
import wave

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.captcha import CaptchaManager
from flask import Flask

def test_piper_captcha():
    """Test the PiperTTS CAPTCHA audio generation."""
    print("=== Testing PiperTTS CAPTCHA Audio Generation ===")
    
    # Initialize CAPTCHA manager
    captcha_manager = CaptchaManager()
    
    # Check if PiperTTS voice was loaded
    if captcha_manager.piper_voice is None:
        print("✗ PiperTTS voice model not loaded")
        return False
    
    print("✓ PiperTTS voice model loaded successfully")
    
    # Test audio generation
    test_text = "TEST123"
    print(f"Testing audio generation for: {test_text}")
    
    audio_data = captcha_manager.generate_captcha_audio(test_text)
    
    if audio_data is None:
        print("✗ Failed to generate audio")
        return False
    
    print(f"✓ Audio generated successfully")
    print(f"  Audio data length: {len(audio_data)} characters")
    print(f"  Audio data preview: {audio_data[:50]}...")
    
    # Test full CAPTCHA generation (with Flask app context)
    print("\n=== Testing Full CAPTCHA Generation ===")
    
    # Create Flask app context for session access
    app = Flask(__name__)
    app.secret_key = 'test-secret-key'
    
    with app.test_request_context():
        captcha_result = captcha_manager.generate_captcha()
    
    if 'audio' not in captcha_result:
        print("✗ No audio in CAPTCHA result")
        return False
    
    print("✓ Full CAPTCHA generation with audio successful")
    print(f"  Image data length: {len(captcha_result['image'])} characters")
    print(f"  Audio data length: {len(captcha_result['audio'])} characters")
    print(f"  Audio available: {captcha_result['audio_available']}")
    
    # Save test audio file for manual verification
    try:
        # Extract base64 data
        audio_base64 = captcha_result['audio'].split(',')[1]
        audio_bytes = base64.b64decode(audio_base64)
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
            temp_path = temp_file.name
            temp_file.write(audio_bytes)
        
        print(f"✓ Test audio saved to: {temp_path}")
        
        # Verify it's a valid WAV file
        with wave.open(temp_path, 'rb') as wav_file:
            frames = wav_file.getnframes()
            sample_rate = wav_file.getframerate()
            duration = frames / float(sample_rate)
            print(f"  Audio duration: {duration:.2f} seconds")
            print(f"  Sample rate: {sample_rate} Hz")
        
        # Clean up
        os.unlink(temp_path)
        
    except Exception as e:
        print(f"✗ Error saving/verifying audio file: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = test_piper_captcha()
    
    if success:
        print("\n✓ All PiperTTS CAPTCHA tests PASSED")
        sys.exit(0)
    else:
        print("\n✗ PiperTTS CAPTCHA tests FAILED")
        sys.exit(1)