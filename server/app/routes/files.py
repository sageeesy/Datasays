"""
File upload and management routes
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List
import os
import uuid
import shutil
from pathlib import Path

from app.services.file_service import (
    extract_metadata,
    save_metadata,
    load_metadata,
    get_all_metadata,
    delete_file as delete_file_service,
)

router = APIRouter()

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/")
async def list_files():
    """List all uploaded files"""
    try:
        files = await get_all_metadata()
        return {
            "success": True,
            "count": len(files),
            "files": [
                {
                    "id": f["id"],
                    "name": f["originalName"],
                    "size": f"{round(f['size'] / 1024)} KB",
                    "rows": f["rows"],
                    "columns": f["columns"],
                    "headers": f.get("headers", []),
                    "preview": f.get("preview", []),
                    "uploadedAt": f["uploadedAt"]
                }
                for f in files
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a single CSV file"""
    try:
        if not file.filename or not file.filename.endswith(".csv"):
            raise HTTPException(status_code=400, detail="Only CSV files are supported")
        
        # Generate unique filename to avoid conflicts
        file_extension = Path(file.filename).suffix
        # Extract metadata will generate the UUID, so we save with a temp name first
        temp_filename = f"temp_{uuid.uuid4()}{file_extension}"
        temp_file_path = UPLOAD_DIR / temp_filename
        
        # Save file temporarily
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Extract metadata (this will generate the UUID)
        metadata = await extract_metadata(str(temp_file_path), file.filename, temp_filename)
        
        # Rename file to use the metadata ID
        file_path = UPLOAD_DIR / f"{metadata['id']}{file_extension}"
        temp_file_path.rename(file_path)
        metadata['filePath'] = str(file_path)
        metadata['fileName'] = f"{metadata['id']}{file_extension}"
        
        # Save metadata
        await save_metadata(metadata)
        
        return {
            "success": True,
            "message": "File uploaded successfully",
            "file": {
                "id": metadata["id"],
                "name": metadata["originalName"],
                "size": f"{round(metadata['size'] / 1024)} KB",
                "rows": metadata["rows"],
                "columns": metadata["columns"],
                "headers": metadata["headers"],
                "preview": metadata["preview"],
                "uploadedAt": metadata["uploadedAt"]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload/multiple")
async def upload_multiple_files(files: List[UploadFile] = File(...)):
    """Upload multiple CSV files"""
    try:
        if not files:
            raise HTTPException(status_code=400, detail="No files uploaded")
        
        results = []
        for file in files:
            if not file.filename or not file.filename.endswith(".csv"):
                continue
            
            # Generate unique filename
            file_extension = Path(file.filename).suffix
            # Extract metadata will generate the UUID, so we save with a temp name first
            temp_filename = f"temp_{uuid.uuid4()}{file_extension}"
            temp_file_path = UPLOAD_DIR / temp_filename
            
            # Save file temporarily
            with open(temp_file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # Extract metadata (this will generate the UUID)
            metadata = await extract_metadata(str(temp_file_path), file.filename, temp_filename)
            
            # Rename file to use the metadata ID
            file_path = UPLOAD_DIR / f"{metadata['id']}{file_extension}"
            temp_file_path.rename(file_path)
            metadata['filePath'] = str(file_path)
            metadata['fileName'] = f"{metadata['id']}{file_extension}"
            
            # Save metadata
            await save_metadata(metadata)
            
            results.append({
                "id": metadata["id"],
                "name": metadata["originalName"],
                "originalName": metadata["originalName"],
                "size": f"{round(metadata['size'] / 1024)} KB",
                "rows": metadata["rows"],
                "columns": metadata["columns"],
                "headers": metadata["headers"],
                "preview": metadata["preview"],
                "uploadedAt": metadata["uploadedAt"]
            })
        
        return {
            "success": True,
            "message": f"{len(results)} file(s) uploaded successfully",
            "files": results
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{file_id}")
async def get_file_info(file_id: str):
    """Get file information by ID"""
    try:
        metadata = await load_metadata(file_id)
        if not metadata:
            raise HTTPException(status_code=404, detail=f"File with ID {file_id} not found")
        
        return {
            "success": True,
            "file": {
                "id": metadata["id"],
                "name": metadata["originalName"],
                "size": f"{round(metadata['size'] / 1024)} KB",
                "rows": metadata["rows"],
                "columns": metadata["columns"],
                "headers": metadata["headers"],
                "preview": metadata["preview"],
                "uploadedAt": metadata["uploadedAt"]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{file_id}")
async def delete_file(file_id: str):
    """Delete a file by ID"""
    try:
        deleted = await delete_file_service(file_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"File with ID {file_id} not found")
        
        return {
            "success": True,
            "message": "File deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
