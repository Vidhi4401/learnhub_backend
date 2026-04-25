import cloudinary
import cloudinary.uploader
from config import CLOUDINARY_URL
from fastapi import UploadFile
import os
import io

# Configure Cloudinary using the URL from .env
if CLOUDINARY_URL:
    cloudinary.config(cloudinary_url=CLOUDINARY_URL)

# File types that Cloudinary treats as "image" or "video"
IMAGE_EXTS  = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"}
VIDEO_EXTS  = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def upload_to_cloudinary(file: UploadFile, folder: str = "learnhub", resource_type: str = "auto"):
    """
    Uploads a file to Cloudinary and returns the secure URL.
    For document/raw files (pdf, txt, docx, etc.) we force resource_type='raw'
    and use access_mode='public' so the file is publicly accessible without a
    signed URL (fixes the 401 on View).
    """
    try:
        file_content = file.file.read()

        ext = os.path.splitext(file.filename or "")[1].lower()
        fname = os.path.splitext(file.filename)[0] if file.filename else None

        # Determine the real resource type — never use "auto" for documents
        if resource_type == "auto":
            if ext in IMAGE_EXTS:
                resolved_type = "image"
            elif ext in VIDEO_EXTS:
                resolved_type = "video"
            else:
                resolved_type = "raw"   # pdf, txt, docx, pptx, xlsx, etc.
        else:
            resolved_type = resource_type

        upload_params = dict(
            folder=folder,
            resource_type=resolved_type,
            use_filename=True,
            unique_filename=True,
            public_id=fname,
        )

        # Raw files must be explicitly set to public; Cloudinary doesn't expose
        # them by default and transformations (like fl_attachment) don't apply.
        if resolved_type == "raw":
            upload_params["access_mode"] = "public"

        result = cloudinary.uploader.upload(file_content, **upload_params)
        return result.get("secure_url")

    except Exception as e:
        print(f"[Cloudinary Error] {e}")
        return None

def upload_buffer_to_cloudinary(buffer: io.BytesIO, filename: str, folder: str = "learnhub", resource_type: str = "auto"):
    """
    Uploads a BytesIO buffer to Cloudinary and returns the secure URL.
    """
    try:
        buffer.seek(0)
        result = cloudinary.uploader.upload(
            buffer,
            folder=folder,
            resource_type=resource_type,
            public_id=filename,
            use_filename=True,
            unique_filename=True
        )
        return result.get("secure_url")
    except Exception as e:
        print(f"[Cloudinary Buffer Error] {e}")
        return None
