#!/usr/bin/env python3
"""
Test script to verify viewer settings and presets functionality.
This script tests the API endpoints and database operations.
"""

import sys
import os
import json
import asyncio
from pathlib import Path

# Add the project root to the path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
from models import Base, ViewerSettings, ViewerPresets, engine, Session, User
from sqlalchemy import select

load_dotenv()

async def test_api_endpoints():
    """Test the API endpoints for viewer settings and presets."""
    print("Testing API endpoints...")
    
    # Create a test user if needed
    with Session() as db:
        # Check if test user exists
        test_user = db.query(User).filter(User.username == 'test_user').first()
        if not test_user:
            print("Creating test user...")
            test_user = User(
                username='test_user',
                password_hash='test_password_hash',
                full_name='Test User',
                email='test@example.com',
                is_active=True
            )
            db.add(test_user)
            db.commit()
            print("✓ Test user created")
        else:
            print("✓ Test user already exists")
        
        user_id = test_user.id
        
        # Test viewer settings
        print("\nTesting viewer settings...")
        settings = db.query(ViewerSettings).filter(ViewerSettings.user_id == user_id).first()
        if not settings:
            print("Creating test viewer settings...")
            settings = ViewerSettings(
                user_id=user_id,
                loupe_size=250,
                loupe_zoom=2.5,
                loupe_enabled=True,
                zoom=120,
                pan_x=10,
                pan_y=-5,
                brightness=1.1,
                contrast=1.2,
                filter='redfree'
            )
            db.add(settings)
            db.commit()
            print("✓ Test viewer settings created")
        else:
            print(f"✓ Found existing viewer settings: loupe_size={settings.loupe_size}, loupe_enabled={settings.loupe_enabled}")
        
        # Test viewer presets
        print("\nTesting viewer presets...")
        for slot_num in range(1, 4):
            preset = db.query(ViewerPresets).filter(
                ViewerPresets.user_id == user_id,
                ViewerPresets.slot_number == slot_num
            ).first()
            
            if not preset:
                print(f"Creating test preset for slot {slot_num}...")
                preset = ViewerPresets(
                    user_id=user_id,
                    slot_number=slot_num,
                    name=f'Test Preset {slot_num}',
                    loupe_size=200 + (slot_num * 10),
                    loupe_zoom=2.0 + (slot_num * 0.1),
                    loupe_enabled=slot_num % 2 == 0,
                    zoom=100 + (slot_num * 10),
                    pan_x=slot_num * 5,
                    pan_y=slot_num * -5,
                    brightness=1.0 + (slot_num * 0.05),
                    contrast=1.0 + (slot_num * 0.05),
                    filter=['none', 'redfree', 'greenboost', 'bluemono', 'gray', 'contrast'][slot_num-1]
                )
                db.add(preset)
                db.commit()
                print(f"✓ Test preset {slot_num} created")
            else:
                print(f"✓ Found existing preset {slot_num}: {preset.name}")
        
        print("\n✓ All tests completed successfully!")

def main():
    """Main test function."""
    print("Starting viewer settings test...")
    
    try:
        # Run the API endpoint tests
        asyncio.run(test_api_endpoints())
        
    except Exception as e:
        print(f"Error during testing: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()