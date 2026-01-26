# utils/paths.py

from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
from typing import Optional, Literal
from flask import Response, abort, send_file
from utils.filename_sanitizer import sanitize_storage_filename
from werkzeug.exceptions import NotFound
from models import ALLOWED_IMAGE_EXT, BASE_DIR, DIRECT_UPLOAD_DIR, IMAGE_DIR, PDF_DIR, EncounterFile, PatientEncounters, ZipFile, DirectImageUpload
from utils.fileUtils import abs_from_parts, _ensure_under_root
from utils.utils import get_db_session


# Type aliases for better readability
ImageType = Literal["encounter", "direct"]
ImageKind = Literal["orig", "edited"]
FileType = Literal["image", "pdf"]


def get_image_path_by_uuid(image_uuid: str) -> Optional[str]:
    """
    Get the full path for an image given its UUID.
    Searches in both EncounterFile (ZIP uploads) and DirectImageUpload tables.
    
    Args:
        image_uuid (str): The UUID of the image
        
    Returns:
        Optional[str]: The full path to the image file, or None if not found
    """
    with get_db_session() as db:
        # First try to find in EncounterFile (ZIP uploads)
        result = (
            db.query(EncounterFile, PatientEncounters, ZipFile)
            .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
            .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
            .filter(EncounterFile.uuid == image_uuid)
            .first()
        )
        
        if result and result[0].filename:
            # Extract the encounter file, patient encounter, and zip file objects
            encounter_file, patient_encounter, zip_file = result
            
            # Get the upload date and format it as YYYY_MM_DD
            upload_date = zip_file.upload_date
            upload_date_str = upload_date.strftime("%Y_%m_%d") if upload_date else ""
            
            # Construct the path to the dated subdirectory
            dated_dir = IMAGE_DIR / upload_date_str
            
            # Construct the full path to the image
            image_path = dated_dir / encounter_file.filename
            
            return str(image_path)
            
        # If not found in EncounterFile, try DirectImageUpload
        direct_image = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == image_uuid).first()
        if direct_image and direct_image.filename:
            # For direct uploads, prefer edited filename if present
            filename = direct_image.edited_filename or direct_image.filename
            
            # Determine the subdirectory (orig or edited)
            kind = "edited" if direct_image.edited_filename else "orig"
            
            # Construct the full path using abs_from_parts
            try:
                image_path = abs_from_parts(direct_image.folder_rel, filename, kind)
                return str(image_path)
            except Exception:
                return None
            
        return None


def get_encounter_image_path_by_uuid(image_uuid: str) -> Optional[str]:
    """
    Get the full path for an image from EncounterFile (ZIP uploads) given its UUID.
    
    Args:
        image_uuid (str): The UUID of the image from EncounterFile table
        
    Returns:
        Optional[str]: The full path to the image file, or None if not found
    """
    with get_db_session() as db:
        # Join with PatientEncounters and ZipFile to get the upload date
        result = (
            db.query(EncounterFile, PatientEncounters, ZipFile)
            .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
            .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
            .filter(EncounterFile.uuid == image_uuid)
            .first()
        )
        
        if not result or not result[0].filename:
            return None
            
        # Extract the encounter file, patient encounter, and zip file objects
        encounter_file, patient_encounter, zip_file = result
        
        # Get the upload date and format it as YYYY_MM_DD
        upload_date = zip_file.upload_date
        upload_date_str = upload_date.strftime("%Y_%m_%d") if upload_date else ""
        
        # Construct the path to the dated subdirectory
        dated_dir = IMAGE_DIR / upload_date_str
        
        # Construct the full path to the image
        image_path = dated_dir / encounter_file.filename
        
        return str(image_path)


def get_direct_image_path_by_uuid(image_uuid: str, prefer_edited: bool = True) -> Optional[str]:
    """
    Get the full path for an image from DirectImageUpload given its UUID.
    
    Args:
        image_uuid (str): The UUID of the image from DirectImageUpload table
        prefer_edited (bool): If True, prefer edited filename if present
        
    Returns:
        Optional[str]: The full path to the image file, or None if not found
    """
    with get_db_session() as db:
        direct_image = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == image_uuid).first()
        if not direct_image or not direct_image.filename:
            return None
            
        # For direct uploads, prefer edited filename if present and requested
        filename = direct_image.edited_filename or direct_image.filename
        if not prefer_edited:
            filename = direct_image.filename
            
        # Determine the subdirectory (orig or edited)
        kind = "edited" if (prefer_edited and direct_image.edited_filename) else "orig"
        
        # Construct the full path using abs_from_parts
        try:
            image_path = abs_from_parts(direct_image.folder_rel, filename, kind)
            return str(image_path)
        except Exception:
            return None


def get_image_folder_path_by_uuid(image_uuid: str) -> Optional[str]:
    """
    Get the folder path for an image given its UUID.
    
    Args:
        image_uuid (str): The UUID of the image
        
    Returns:
        Optional[str]: The folder path where the image is stored, or None if not found
    """
    with get_db_session() as db:
        # First try to find in EncounterFile (ZIP uploads)
        result = (
            db.query(EncounterFile, PatientEncounters, ZipFile)
            .join(PatientEncounters, EncounterFile.patient_encounter_id == PatientEncounters.id)
            .join(ZipFile, PatientEncounters.zip_file_id == ZipFile.id)
            .filter(EncounterFile.uuid == image_uuid)
            .first()
        )
        
        if result:
            # Extract the encounter file, patient encounter, and zip file objects
            encounter_file, patient_encounter, zip_file = result
            
            # Get the upload date and format it as YYYY_MM_DD
            upload_date = zip_file.upload_date
            upload_date_str = upload_date.strftime("%Y_%m_%d") if upload_date else ""
            
            # Construct the path to the dated subdirectory
            dated_dir = IMAGE_DIR / upload_date_str
            
            return str(dated_dir)
            
        # If not found in EncounterFile, try DirectImageUpload
        direct_image = db.query(DirectImageUpload).filter(DirectImageUpload.uuid == image_uuid).first()
        if direct_image:
            # Construct the folder path using abs_from_parts (base directory)
            try:
                base_path = abs_from_parts(direct_image.folder_rel, "", "orig").parent
                return str(base_path)
            except Exception:
                return None
            
        return None


def get_base_directory(image_type: ImageType, file_type: FileType = "image") -> Path:
    """
    Get the base directory for a specific image type and file type.
    
    Args:
        image_type (ImageType): Type of image ('encounter' or 'direct')
        file_type (FileType): Type of file ('image' or 'pdf')
        
    Returns:
        Path: Base directory path
    """
    if file_type == "pdf":
        return PDF_DIR
    return IMAGE_DIR


def get_dated_subdirectory(base_dir: Path, date: datetime) -> Path:
    """
    Get a dated subdirectory path based on a date.
    
    Args:
        base_dir (Path): Base directory
        date (datetime): Date to format
        
    Returns:
        Path: Dated subdirectory path in format YYYY_MM_DD
    """
    date_str = date.strftime("%Y_%m_%d")
    return base_dir / date_str


def construct_secure_path(base_dir: Path, filename: str) -> Path:
    """
    Construct a secure path that prevents path traversal attacks.
    
    Args:
        base_dir (Path): Base directory
        filename (str): Filename
        
    Returns:
        Path: Secure path
        
    Raises:
        ValueError: If path traversal is detected
    """
    # Use storage-safe filename sanitizer (ASCII-safe with hash on change)
    safe_filename = sanitize_storage_filename(filename)
    
    # Construct the full path
    full_path = base_dir / safe_filename
    
    # Ensure the path is under the base directory
    _ensure_under_root(full_path, base_dir)
    
    return full_path


def get_encounter_file_path(filename: str, upload_date: datetime, file_type: FileType = "image") -> Path:
    """
    Get the full path for an encounter file (ZIP upload).
    
    Args:
        filename (str): Original filename
        upload_date (datetime): Upload date for directory structure
        file_type (FileType): Type of file ('image' or 'pdf')
        
    Returns:
        Path: Full path to the file
    """
    # Get base directory
    base_dir = get_base_directory("encounter", file_type)
    
    # Get dated subdirectory
    dated_dir = get_dated_subdirectory(base_dir, upload_date)
    
    # Create secure path
    return construct_secure_path(dated_dir, filename)


def get_direct_file_path(folder_rel: str, filename: str, kind: ImageKind = "orig") -> Path:
    """
    Get the full path for a direct upload file.
    
    Args:
        folder_rel (str): Relative folder path from DirectImageUpload
        filename (str): Filename
        kind (ImageKind): Type of file ('orig' or 'edited')
        
    Returns:
        Path: Full path to the file
    """
    return abs_from_parts(folder_rel, filename, kind)


def get_file_path_by_record(
    image_type: ImageType,
    filename: str,
    upload_date: Optional[datetime] = None,
    folder_rel: Optional[str] = None,
    kind: ImageKind = "orig",
    file_type: FileType = "image"
) -> Optional[Path]:
    """
    Get the full path for a file based on its record details.
    
    Args:
        image_type (ImageType): Type of image ('encounter' or 'direct')
        filename (str): Filename
        upload_date (datetime, optional): Upload date for encounter files
        folder_rel (str, optional): Relative folder path for direct uploads
        kind (ImageKind): Type of file ('orig' or 'edited')
        file_type (FileType): Type of file ('image' or 'pdf')
        
    Returns:
        Optional[Path]: Full path to the file, or None if invalid
    """
    try:
        if image_type == "encounter":
            if not upload_date:
                return None
            return get_encounter_file_path(filename, upload_date, file_type)
        elif image_type == "direct":
            if not folder_rel:
                return None
            return get_direct_file_path(folder_rel, filename, kind)
        return None
    except Exception:
        return None


# Convenience functions for specific use cases


def get_encounter_image_path(filename: str, upload_date: datetime) -> Path:
    """
    Get the full path for an encounter image.
    
    Args:
        filename (str): Image filename
        upload_date (datetime): Upload date
        
    Returns:
        Path: Full path to the image
    """
    return get_encounter_file_path(filename, upload_date, "image")


def get_encounter_pdf_path(filename: str, upload_date: datetime) -> Path:
    """
    Get the full path for an encounter PDF.
    
    Args:
        filename (str): PDF filename
        upload_date (datetime): Upload date
        
    Returns:
        Path: Full path to the PDF
    """
    return get_encounter_file_path(filename, upload_date, "pdf")


def get_direct_image_path(folder_rel: str, filename: str, kind: ImageKind = "orig") -> Path:
    """
    Get the full path for a direct upload image.
    
    Args:
        folder_rel (str): Relative folder path
        filename (str): Image filename
        kind (ImageKind): Type of image ('orig' or 'edited')
        
    Returns:
        Path: Full path to the image
    """
    return get_direct_file_path(folder_rel, filename, kind)


def ensure_exists_rel(rel_path: str) -> Path:
    """
    Safely resolve and verify existence of a path relative to DIRECT_UPLOAD_DIR.
    
    Args:
        rel_path (str): Relative path to resolve
        
    Returns:
        Path: Absolute path if it exists and is within DIRECT_UPLOAD_DIR
        
    Raises:
        NotFound: If the path is outside the allowed directory
        FileNotFoundError: If the path doesn't exist
    """
    base = DIRECT_UPLOAD_DIR.resolve()
    abs_path = (base / rel_path).resolve()
    if base not in abs_path.parents and abs_path != base:
        raise NotFound("Forbidden path")
    if not abs_path.exists():
        raise FileNotFoundError(abs_path)
    return abs_path


# Example usage:
# if __name__ == "__main__":
#     # Test the functions with a sample UUID
#     test_uuid = "some-uuid-here"
#     path = get_image_path_by_uuid(test_uuid)
#     if path:
#         print(f"Image path: {path}")
#     else:
#         print("Image not found")




 
