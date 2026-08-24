"""
File service for handling file operations
"""

import os
import json
import csv
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from app.services.profile_service import build_dataset_profile

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
METADATA_DIR = UPLOAD_DIR / ".metadata"

# Ensure directories exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
METADATA_DIR.mkdir(parents=True, exist_ok=True)


def inspect_csv(file_path: str) -> Tuple[List[str], int, List[List[str]]]:
    """Read CSV headers, row count, and a short preview without retaining all rows."""
    with open(file_path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        headers = next(reader, [])
        preview: List[List[str]] = [headers] if headers else []
        row_count = 0
        for row in reader:
            row_count += 1
            if len(preview) < 4:
                preview.append(row)
    return headers, row_count, preview


async def extract_metadata(file_path: str, original_name: str, file_name: str) -> Dict[str, Any]:
    """Extract metadata from CSV file"""
    file_stat = os.stat(file_path)
    headers, num_rows, preview = inspect_csv(file_path)
    num_columns = len(headers)
    profile = build_dataset_profile(file_path, original_name)
    
    return {
        "id": str(uuid.uuid4()),
        "originalName": original_name,
        "fileName": file_name,
        "filePath": file_path,
        "size": file_stat.st_size,
        "uploadedAt": datetime.now().isoformat(),
        "rows": num_rows,
        "columns": num_columns,
        "headers": headers,
        "preview": preview,
        "profile": profile,
    }


async def save_metadata(metadata: Dict[str, Any]) -> None:
    """Save file metadata to JSON file"""
    metadata_path = METADATA_DIR / f"{metadata['id']}.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


async def load_metadata(file_id: str) -> Optional[Dict[str, Any]]:
    """Load file metadata by ID"""
    try:
        metadata_path = METADATA_DIR / f"{file_id}.json"
        if not metadata_path.exists():
            return None
        with open(metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


async def get_all_metadata() -> List[Dict[str, Any]]:
    """Get all file metadata"""
    metadata_list = []
    try:
        for file in METADATA_DIR.glob("*.json"):
            file_id = file.stem
            metadata = await load_metadata(file_id)
            if metadata:
                metadata_list.append(metadata)
    except Exception:
        pass
    return metadata_list


async def delete_file(file_id: str) -> bool:
    """Delete file and its metadata"""
    try:
        metadata = await load_metadata(file_id)
        if not metadata:
            return False
        
        # Delete the actual file
        file_path = Path(metadata["filePath"])
        if file_path.exists():
            file_path.unlink()
        
        # Delete metadata file
        metadata_path = METADATA_DIR / f"{file_id}.json"
        if metadata_path.exists():
            metadata_path.unlink()
        
        return True
    except Exception:
        return False


async def get_file_content(file_id: str) -> Optional[str]:
    """Get file content by ID"""
    try:
        metadata = await load_metadata(file_id)
        if not metadata:
            return None
        
        file_path = Path(metadata["filePath"])
        if not file_path.exists():
            return None
        
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None
