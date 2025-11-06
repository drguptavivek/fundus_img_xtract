#!/usr/bin/env python3
"""Test script to debug audio CAPTCHA generation."""

import os
import io
import base64
import tempfile
import signal
import threading
import time
import subprocess
from captcha.image import ImageCaptcha

# Try to import pyttsx3, but don't fail if it's not available
try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False
    print("Note: pyttsx3 not available, will test alternative methods only")

class AudioTimeoutError(Exception):
    """Exception raised when audio generation times out."""
    pass

def timeout_handler(signum, frame):
    """Handle timeout signal."""
    raise AudioTimeoutError("Audio generation timed out")

def test_audio_generation():
    """Test audio generation step by step."""
    print("Starting audio generation test...")
    
    # Test 1: Initialize pyttsx3
    try:
        engine = pyttsx3.init()
        print("✓ pyttsx3 initialized successfully")
    except Exception as e:
        print(f"✗ Failed to initialize pyttsx3: {e}")
        return False
    
    # Test 2: Configure engine
    try:
        engine.setProperty('rate', 150)
        engine.setProperty('volume', 0.9)
        print("✓ Engine configured successfully")
    except Exception as e:
        print(f"✗ Failed to configure engine: {e}")
        return False
    
    # Test 3: Create temporary file
    try:
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
            temp_path = temp_file.name
        print(f"✓ Temporary file created: {temp_path}")
    except Exception as e:
        print(f"✗ Failed to create temporary file: {e}")
        return False
    
    # Test 4: Generate speech with timeout
    try:
        text = "TEST123"
        speech_text = ' '.join(list(text))
        print(f"Generating speech for: {speech_text}")
        
        # Set up timeout
        def generate_with_timeout():
            engine.save_to_file(speech_text, temp_path)
            engine.runAndWait()
        
        # Run in a separate thread with timeout
        thread = threading.Thread(target=generate_with_timeout)
        thread.daemon = True
        thread.start()
        thread.join(timeout=10)  # 10 second timeout
        
        if thread.is_alive():
            print("✗ Audio generation timed out after 10 seconds")
            # Try to stop the engine
            try:
                engine.stop()
            except:
                pass
            return False
            
        print("✓ Speech generation completed")
    except Exception as e:
        print(f"✗ Failed to generate speech: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 5: Check file exists and has content
    try:
        if not os.path.exists(temp_path):
            print("✗ Audio file was not created")
            return False
        
        file_size = os.path.getsize(temp_path)
        print(f"✓ Audio file exists, size: {file_size} bytes")
        
        if file_size == 0:
            print("✗ Audio file is empty")
            return False
            
    except Exception as e:
        print(f"✗ Failed to check audio file: {e}")
        return False
    
    # Test 6: Read and encode file
    try:
        with open(temp_path, 'rb') as audio_file:
            audio_data = audio_file.read()
            if len(audio_data) == 0:
                print("✗ Failed to read audio data - empty")
                return False
                
            audio_str = base64.b64encode(audio_data).decode()
            print(f"✓ Audio data encoded, length: {len(audio_str)}")
            
    except Exception as e:
        print(f"✗ Failed to read/encode audio file: {e}")
        return False
    
    # Test 7: Clean up
    try:
        os.unlink(temp_path)
        print("✓ Temporary file cleaned up")
    except Exception as e:
        print(f"✗ Failed to clean up temporary file: {e}")
    
    # Test 8: Return result
    result = f"data:audio/mpeg;base64,{audio_str}"
    print(f"✓ Final result length: {len(result)}")
    return result

def test_alternative_audio():
    """Test alternative audio generation using macOS say command."""
    print("\n--- Testing alternative audio generation ---")
    
    try:
        text = "TEST123"
        speech_text = ' '.join(list(text))
        print(f"Generating speech using macOS say for: {speech_text}")
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(suffix='.aiff', delete=False) as temp_file:
            temp_path = temp_file.name
        
        # Use macOS say command
        import subprocess
        cmd = ['say', '-v', 'Alex', '-o', temp_path, '--data-format=LEF32@16000', speech_text]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            print(f"✗ say command failed: {result.stderr}")
            return False
        
        # Convert to mp3 using ffmpeg if available
        try:
            mp3_path = temp_path.replace('.aiff', '.mp3')
            cmd = ['ffmpeg', '-y', '-i', temp_path, mp3_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                os.unlink(temp_path)  # Remove aiff file
                temp_path = mp3_path
            else:
                print(f"ffmpeg conversion failed, using aiff: {result.stderr}")
        except FileNotFoundError:
            print("ffmpeg not found, using aiff format")
        
        # Read and encode
        with open(temp_path, 'rb') as audio_file:
            audio_data = audio_file.read()
            if len(audio_data) == 0:
                print("✗ Failed to read audio data - empty")
                return False
                
            audio_str = base64.b64encode(audio_data).decode()
            
        # Clean up
        os.unlink(temp_path)
        
        # Determine MIME type
        mime_type = 'audio/mpeg' if temp_path.endswith('.mp3') else 'audio/aiff'
        result = f"data:{mime_type};base64,{audio_str}"
        print(f"✓ Alternative audio generation successful, length: {len(result)}")
        return result
        
    except subprocess.TimeoutExpired:
        print("✗ Alternative audio generation timed out")
        return False
    except Exception as e:
        print(f"✗ Alternative audio generation failed: {e}")
        return False

if __name__ == "__main__":
    print("=== Testing pyttsx3 audio generation ===")
    result = test_audio_generation()
    if result:
        print("\n✓ Audio generation test PASSED")
        print(f"Result preview: {result[:50]}...")
    else:
        print("\n✗ Audio generation test FAILED")
        
        # Try alternative method
        alt_result = test_alternative_audio()
        if alt_result:
            print("\n✓ Alternative audio generation PASSED")
            print(f"Alternative result preview: {alt_result[:50]}...")
        else:
            print("\n✗ All audio generation methods FAILED")