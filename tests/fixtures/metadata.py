"""
Fixtures for test metadata (Camera, Disease, Area).
"""
import pytest
from models import Camera, Disease, Area


@pytest.fixture(scope="session")
def test_metadata(test_engine):
    """
    Create basic metadata for images/tasks (Camera, Disease, Area).
    Session-scoped to persist across all tests.
    """
    from sqlalchemy.orm import sessionmaker
    
    Session = sessionmaker(bind=test_engine)
    session = Session()
    
    try:
        # Check if metadata already exists to avoid duplicates
        camera = session.query(Camera).filter_by(name="Test Camera").first()
        if not camera:
            camera = Camera(name="Test Camera")
            session.add(camera)
        
        disease = session.query(Disease).filter_by(name="Test Disease").first()
        if not disease:
            disease = Disease(name="Test Disease")
            session.add(disease)
        
        area = session.query(Area).filter_by(name="Test Area").first()
        if not area:
            area = Area(name="Test Area")
            session.add(area)
        
        session.commit()
        
        return {"camera": camera, "disease": disease, "area": area}
    finally:
        session.close()
