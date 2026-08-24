"""
Secure sandbox service for executing Python code
"""

import os
import re
import json
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
import asyncio

from app.schemas.analysis import AnalysisResult

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
DOCKER_IMAGE = os.getenv("DOCKER_IMAGE", "datasays-python-sandbox")
SANDBOX_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT", "30"))  # seconds
USE_DOCKER = os.getenv("USE_DOCKER", "true").lower() == "true"
SANDBOX_WORK_DIR = Path(os.getenv("SANDBOX_WORK_DIR", tempfile.gettempdir()))
RESULT_MARKER = "__DATASAYS_RESULT__"


async def execute_code(
    code: str,
    file_ids: List[str],
    metadata_loader
) -> Dict[str, Any]:
    """
    Execute Python code in a secure sandbox
    
    Args:
        code: Python code to execute
        file_ids: List of file IDs to make available
        metadata_loader: Function to load file metadata
    
    Returns:
        Execution result with content, status, and optional output
    """
    temp_dir = None
    try:
        # Create temporary directory for execution
        SANDBOX_WORK_DIR.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="datasays-", dir=SANDBOX_WORK_DIR))
        
        # Copy CSV files to temp directory
        for file_id in file_ids:
            metadata = await metadata_loader(file_id)
            if not metadata:
                raise ValueError(f"File {file_id} not found")
            
            # Get file path and ensure it's absolute
            file_path_str = metadata.get("filePath")
            if not file_path_str:
                raise ValueError(f"File path not found in metadata for file {file_id}")
            
            # Convert to Path object
            source_path = Path(file_path_str)
            
            # If path is relative, resolve it relative to UPLOAD_DIR
            if not source_path.is_absolute():
                # If it's already relative to UPLOAD_DIR, use it directly
                if str(source_path).startswith(str(UPLOAD_DIR)):
                    source_path = source_path.resolve()
                else:
                    source_path = (UPLOAD_DIR / source_path).resolve()
            else:
                # If absolute, just resolve it
                source_path = source_path.resolve()
            
            # Check if file exists
            if not source_path.exists():
                # Try alternative: check if file exists in UPLOAD_DIR with just the filename
                alt_path = UPLOAD_DIR / source_path.name
                if alt_path.exists():
                    source_path = alt_path.resolve()
                else:
                    raise ValueError(f"File not found at path: {source_path} (tried: {alt_path}) for file ID: {file_id}. UPLOAD_DIR: {UPLOAD_DIR.resolve()}")
            
            # Copy CSV file to temp directory with fileId as filename
            dest_path = temp_dir / f"{file_id}.csv"
            shutil.copy2(source_path, dest_path)
        
        # Write Python code to temp file
        code_path = temp_dir / "script.py"
        code_path.write_text(code, encoding="utf-8")
        
        # Log available files for debugging
        available_files = [f.name for f in temp_dir.glob("*") if f.is_file()]
        
        # Verify files exist before execution
        for file_id in file_ids:
            expected_file = temp_dir / f"{file_id}.csv"
            if not expected_file.exists():
                # Check if file exists with different case or format
                matching_files = [f for f in available_files if file_id.lower() in f.lower()]
                error_msg = f"Expected file '{file_id}.csv' not found in temp directory."
                error_msg += f" Available files: {available_files}"
                if matching_files:
                    error_msg += f" Similar files found: {matching_files}"
                error_msg += f" File IDs requested: {file_ids}"
                raise ValueError(error_msg)
        
        if USE_DOCKER:
            # The API container writes these files as root, while the sandbox
            # deliberately runs as uid 1000. Grant read/execute access only.
            temp_dir.chmod(0o755)
            for path in temp_dir.iterdir():
                if path.is_file():
                    path.chmod(0o644)
            result = await _execute_in_docker(temp_dir)
        else:
            result = await _execute_directly(temp_dir)
        
        structured_result, display_stdout = _extract_structured_result(result["stdout"])
        output = _parse_execution_output(display_stdout, structured_result)
        
        # Check if stdout contains HTML table - if so, preserve it in content
        stdout_content = display_stdout.strip()
        if structured_result:
            # Structured rows are rendered by the frontend output component. Showing
            # diagnostic HTML/JSON here would duplicate the result and expose protocol.
            stdout_content = structured_result.get("summary", "Code executed successfully")
        stdout_content = stdout_content or "Code executed successfully"
        if "<table" in stdout_content.lower():
            # HTML table detected - keep as is for frontend rendering
            pass
        
        return {
            "content": stdout_content,
            "status": "success" if result["status"] == 0 else "error",
            "output": output,
            "structured_result": structured_result,
        }
    except subprocess.TimeoutExpired:
        return {
            "content": f"Code execution timed out after {SANDBOX_TIMEOUT} seconds",
            "status": "error"
        }
    except Exception as e:
        error_msg = str(e)
        if "Docker not found" in error_msg or "Docker daemon" in error_msg or "Docker image" in error_msg:
            return {
                "content": (
                    f"Sandbox configuration error: {error_msg} "
                    "For local development without Docker, set USE_DOCKER=false in server/.env and restart the backend."
                ),
                "status": "error"
            }
        # Add more context to error message
        if "not found" in error_msg.lower() or "FileNotFoundError" in error_msg or "[Errno 2]" in error_msg:
            # Provide helpful debugging information
            debug_info = ""
            if temp_dir and temp_dir.exists():
                available_files = list(temp_dir.glob("*"))
                debug_info = f" Available files in temp directory: {[f.name for f in available_files]}"
            return {
                "content": f"File not found error: {error_msg}.{debug_info} Please check that the code uses the correct file path (e.g., 'file-id.csv' in the current directory).",
                "status": "error"
            }
        return {
            "content": f"Execution error: {error_msg}",
            "status": "error"
        }
    finally:
        # Clean up temp directory
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


async def _execute_in_docker(temp_dir: Path) -> Dict[str, Any]:
    """Execute code in Docker container"""
    try:
        # Docker command with security constraints:
        # - --network none: No network access
        # - --memory=512m: Memory limit
        # - --cpus=1: CPU limit
        # - --user 1000:1000: Non-root user
        # - -v :ro: Read-only mount
        docker_cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--memory=512m",
            "--cpus=1",
            "-v", f"{temp_dir}:/sandbox:ro",
            "-w", "/sandbox",
            "--user", "1000:1000",
            DOCKER_IMAGE,
            "python3", "script.py"
        ]
        
        process = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(temp_dir)
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=SANDBOX_TIMEOUT
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise subprocess.TimeoutExpired(docker_cmd, SANDBOX_TIMEOUT)
        
        stdout_str = stdout.decode("utf-8", errors="ignore")
        stderr_str = stderr.decode("utf-8", errors="ignore")
        
        return {
            "stdout": stdout_str,
            "stderr": stderr_str,
            "status": process.returncode
        }
    except FileNotFoundError:
        raise ValueError("Docker not found. Please install Docker and ensure it is running.")
    except Exception as e:
        if "Cannot connect to the Docker daemon" in str(e):
            raise ValueError("Cannot connect to Docker daemon. Please ensure Docker is running.")
        if "No such image" in str(e):
            raise ValueError(f"Docker image '{DOCKER_IMAGE}' not found. Please build it first.")
        raise


async def _execute_directly(temp_dir: Path) -> Dict[str, Any]:
    """Execute code directly (fallback for development)"""
    python_path = os.getenv("PYTHON_PATH", sys.executable)
    code_path = temp_dir / "script.py"
    
    process = await asyncio.create_subprocess_exec(
        python_path, str(code_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(temp_dir)
    )
    
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=SANDBOX_TIMEOUT
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise subprocess.TimeoutExpired([python_path, str(code_path)], SANDBOX_TIMEOUT)
    
    stdout_str = stdout.decode("utf-8", errors="ignore")
    stderr_str = stderr.decode("utf-8", errors="ignore")
    
    if stderr_str:
        # Combine stderr with stdout for error display
        stdout_str = f"{stderr_str}\n{stdout_str}" if stdout_str else stderr_str
    
    return {
        "stdout": stdout_str,
        "stderr": stderr_str,
        "status": process.returncode
    }


def _extract_structured_result(output: str) -> tuple[Optional[Dict[str, Any]], str]:
    """Extract the final typed artifact while keeping other stdout readable."""
    if not output or RESULT_MARKER not in output:
        return None, output

    structured: Optional[Dict[str, Any]] = None
    display_lines = []
    for line in output.splitlines():
        if RESULT_MARKER not in line:
            display_lines.append(line)
            continue
        _, payload = line.split(RESULT_MARKER, 1)
        try:
            raw_result = json.loads(payload.strip())
            if isinstance(raw_result, dict):
                # Some models duplicate tabular rows into primary_value. Preserve the
                # useful rows while normalizing the artifact back to its typed contract.
                primary_value = raw_result.get("primary_value")
                if raw_result.get("answer_type") == "table" and isinstance(primary_value, list):
                    if not raw_result.get("rows") and all(isinstance(item, dict) for item in primary_value):
                        raw_result["rows"] = primary_value
                    raw_result["primary_value"] = None
            structured = AnalysisResult.model_validate(raw_result).model_dump(mode="json")
        except json.JSONDecodeError as error:
            display_lines.append(f"Structured result JSON error: {error}")
            continue
        except ValueError as error:
            # Marker payloads are machine protocol and should never be user-facing.
            # The concise schema error is retained so the repair loop can fix the
            # exact field instead of receiving only a generic contract failure.
            display_lines.append(f"Structured result validation error: {error}")
            continue
    return structured, "\n".join(display_lines)


def _parse_execution_output(
    output: str,
    structured_result: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Parse execution output to extract structured data"""
    if structured_result:
        answer_type = structured_result["answer_type"]
        if answer_type == "number":
            return {
                "type": "number",
                "data": {
                    "value": structured_result.get("primary_value"),
                    "unit": structured_result.get("unit"),
                },
                "analysis_result": structured_result,
            }
        if answer_type == "table":
            rows = structured_result.get("rows", [])
            headers = list(rows[0].keys()) if rows else []
            return {
                "type": "table",
                "data": {
                    "headers": headers,
                    "rows": [[row.get(header) for header in headers] for row in rows],
                },
                "analysis_result": structured_result,
            }
        return {
            "type": "text",
            "data": {"value": structured_result.get("primary_value")},
            "analysis_result": structured_result,
        }

    if not output:
        return None
    
    # Try to parse as JSON
    try:
        json_match = re.search(r"\{[\s\S]*\}", output)
        if json_match:
            parsed = json.loads(json_match.group(0))
            if parsed.get("type") and parsed.get("data"):
                return parsed
    except Exception:
        pass
    
    # Try to parse as table (CSV-like output)
    lines = [line.strip() for line in output.strip().split("\n") if line.strip()]
    if len(lines) >= 2:
        first_line = lines[0]
        second_line = lines[1]
        
        # Check if it looks like a table
        if ("," in first_line or "\t" in first_line) and ("," in second_line or "\t" in second_line):
            separator = "," if "," in first_line else "\t"
            headers = [h.strip() for h in first_line.split(separator)]
            rows = [[cell.strip() for cell in line.split(separator)] for line in lines[1:]]
            
            return {
                "type": "table",
                "data": {"headers": headers, "rows": rows}
            }
    
    # Try to extract number (single numeric value)
    number_match = re.search(r"[-+]?\d*\.?\d+", output)
    if number_match and len(lines) == 1:
        try:
            number = float(number_match.group(0))
            if not (number != number):  # Check for NaN
                return {
                    "type": "number",
                    "data": {"value": number}
                }
        except ValueError:
            pass
    
    return None
