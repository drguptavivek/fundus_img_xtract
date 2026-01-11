import os
import sys
import uuid
# Add project root to path
sys.path.append(os.getcwd())

from app import create_app
from models import User, Hospital, LabUnit, DirectImageUpload, Role, Camera, Disease, Area
from utils.hospital_scoping import apply_scoping
from db_transaction_manager import get_db_session
from sqlalchemy import text

def hotfix_db_schema():
    with get_db_session() as session:
        try:
            # Check hospital_id
            res = session.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='hospital_id'"))
            if not res.first():
                print("Hotfixing: Adding hospital_id to users...")
                session.execute(text("ALTER TABLE users ADD COLUMN hospital_id INTEGER REFERENCES hospitals(id)"))
                session.commit()
            
            # Check is_master_admin
            res = session.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='is_master_admin'"))
            if not res.first():
                print("Hotfixing: Adding is_master_admin to users...")
                session.execute(text("ALTER TABLE users ADD COLUMN is_master_admin BOOLEAN DEFAULT FALSE"))
                session.commit()
                
            print("Schema Hotfix Complete.")
        except Exception as e:
            print(f"Hotfix failed: {e}")

def run_verification():
    app = create_app()
    with app.app_context():
        hotfix_db_schema() # Attempt to fix DB
        
        print("Starting Scoping Verification...")
        
        with get_db_session() as session:
            # ... rest of code
            suffix = uuid.uuid4().hex[:6]
            
            # Create Hospitals
            ha = Hospital(name=f"Hosp A {suffix}")
            hb = Hospital(name=f"Hosp B {suffix}")
            session.add_all([ha, hb])
            session.flush()
            
            # Create Lab Unit
            la = LabUnit(name=f"Lab A {suffix}", hospital_id=ha.id)
            lb = LabUnit(name=f"Lab B {suffix}", hospital_id=hb.id)
            session.add_all([la, lb])
            session.flush()
            
            # Ensure Role
            role = session.query(Role).first()
            if not role:
                role = Role(name='optometrist')
                session.add(role)
            
            # Create Users
            ua = User(username=f"u_a_{suffix}", email=f"a_{suffix}@test.com", hospital_id=ha.id, password_hash='hashed_secret')
            ub = User(username=f"u_b_{suffix}", email=f"b_{suffix}@test.com", hospital_id=hb.id, password_hash='hashed_secret')
            # Assign Lab Units
            ua.lab_units.append(la)
            ub.lab_units.append(lb)
            ua.roles.append(role)
            ub.roles.append(role)
            
            session.add_all([ua, ub])
            session.commit() # Commit to get IDs and persist
            
            # Ensure Camera, Disease, Area
            cam = session.query(Camera).first()
            if not cam:
                cam = Camera(name='Test Cam')
                session.add(cam)
            
            dis = session.query(Disease).first()
            if not dis:
                dis = Disease(name='Test Disease')
                session.add(dis)
                
            area = session.query(Area).first()
            if not area:
                area = Area(name='Test Area')
                session.add(area)
            
            session.flush() # Get IDs
            
            # Create Images
            uuid_a = f"img_a_{suffix}"
            uuid_b = f"img_b_{suffix}"
            
            img_a = DirectImageUpload(
                uuid=uuid_a, 
                hospital_id=ha.id, 
                uploader_id=ua.id, 
                filename="test.jpg", 
                folder_rel="test",
                camera_id=cam.id,
                disease_id=dis.id,
                area_id=area.id,
                file_hash=f"hash_{uuid_a}",
                lab_unit_id=la.id # Assuming LA belongs to Hospital A
            )
            img_b = DirectImageUpload(
                uuid=uuid_b, 
                hospital_id=hb.id, 
                uploader_id=ub.id, 
                filename="test.jpg", 
                folder_rel="test",
                camera_id=cam.id,
                disease_id=dis.id,
                area_id=area.id,
                file_hash=f"hash_{uuid_b}",
                lab_unit_id=lb.id # Assuming LB belongs to Hospital B
            )
            session.add_all([img_a, img_b])
            session.commit()
            
            print(f"Setup Complete: User A (Hosp A), User B (Hosp B). Images A, B.")
            
            # Verify Scoping
            q = session.query(DirectImageUpload)
            
            # Test 1: User A - Default Strict Scoping (No Context)
            q_a = apply_scoping(q, DirectImageUpload, ua, 'upload')
            res_a = q_a.all()
            uuids_a = [i.uuid for i in res_a]
            
            print(f"User A (Strict) sees: {uuids_a}")
            if uuid_a in uuids_a and uuid_b not in uuids_a:
                print("PASS: User A Strict Scoping")
            else:
                print(f"FAIL: User A Strict Scoping. Expected {[uuid_a]}, Got {uuids_a}")

            # Test 2: User B - Strict Scoping
            q_b = apply_scoping(q, DirectImageUpload, ub, 'upload')
            res_b = q_b.all()
            uuids_b = [i.uuid for i in res_b]
            
            print(f"User B (Strict) sees: {uuids_b}")
            if uuid_b in uuids_b and uuid_a not in uuids_b:
                print("PASS: User B Strict Scoping")
            else:
                print(f"FAIL: User B Strict Scoping. Expected {[uuid_b]}, Got {uuids_b}")
                
            # Test 3: User A - Grading Context (Cross Hospital Allowed)
            from utils.hospital_scoping import determine_scoping_context
            with app.test_request_context('/?context=grading'):
                ctx = determine_scoping_context()
                print(f"Detected Context: {ctx}")
                
                # In Grading context, regular user sees ALL images (because is_cross_hospital_operation checks skip filter)
                # Wait, does apply_scoping return ALL for 'grading'? 
                # apply_scoping: if is_cross_hospital_operation(operation): return query (returns UNFILTERED query)
                q_grading = apply_scoping(q, DirectImageUpload, ua, ctx)
                res_grading = q_grading.all()
                uuids_grading = [i.uuid for i in res_grading]
                
                print(f"User A (Grading) sees: {uuids_grading}")
                if uuid_a in uuids_grading and uuid_b in uuids_grading:
                    print("PASS: User A Grading Scoping (Cross-Hospital)")
                else:
                    print(f"FAIL: User A Grading Scoping. Expected {[uuid_a, uuid_b]}, Got {uuids_grading}")

            # Test 3: User A - Grading Context (Cross Hospital Allowed)
            from utils.hospital_scoping import determine_scoping_context
            with app.test_request_context('/?context=grading'):
                ctx = determine_scoping_context()
                print(f"Detected Context: {ctx}")
                
                q_grading = apply_scoping(q, DirectImageUpload, ua, ctx)
                res_grading = q_grading.all()
                uuids_grading = [i.uuid for i in res_grading]
                
                print(f"User A (Grading) sees: {uuids_grading}")
                if uuid_a in uuids_grading and uuid_b in uuids_grading:
                    print("PASS: User A Grading Scoping (Cross-Hospital)")
                else:
                    print(f"FAIL: User A Grading Scoping. Expected {[uuid_a, uuid_b]}, Got {uuids_grading}")

if __name__ == "__main__":
    run_verification()
