"""FastAPI entry point for the DataSays Agent API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
from datetime import datetime
from dotenv import load_dotenv

# Environment-dependent service constants are evaluated during route imports.
load_dotenv()

from app.routes import conversations, files, query
from app.services.conversation_service import initialize_database
from app.middleware.error_handler import setup_error_handlers

# Create FastAPI app
app = FastAPI(
    title="DataSays API",
    description="Evidence-first data analysis Agent API",
    version="2.0.0"
)

initialize_database()

# CORS middleware
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
# Allow origins - you can specify multiple frontend URLs separated by commas
allowed_origins_str = os.getenv("ALLOWED_ORIGINS", "")
if allowed_origins_str:
    allowed_origins = [origin.strip() for origin in allowed_origins_str.split(",")]
else:
    # Default origins
    allowed_origins = [
        frontend_url,
        "http://localhost:5173",  # Vite dev server
        "http://127.0.0.1:5173",  # Vite dev server (alternative)
    ]
    # Add Vercel URL if provided
    vercel_url = os.getenv("VERCEL_URL")
    if vercel_url:
        allowed_origins.append(f"https://{vercel_url}")
    
    # Add Railway public domain if provided (Railway automatically sets RAILWAY_PUBLIC_DOMAIN)
    railway_public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if railway_public_domain:
        allowed_origins.append(f"https://{railway_public_domain}")
    
    # Add RAILWAY_URL if provided (alternative Railway URL variable)
    railway_url = os.getenv("RAILWAY_URL")
    if railway_url:
        # Ensure URL has https:// prefix
        if not railway_url.startswith("http"):
            railway_url = f"https://{railway_url}"
        allowed_origins.append(railway_url)

# In production, you might want to allow all origins for flexibility
# Set ALLOW_ALL_ORIGINS=true to enable this (not recommended for production)
allow_all_origins = os.getenv("ALLOW_ALL_ORIGINS", "false").lower() == "true"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all_origins else allowed_origins,
    allow_origin_regex=(
        None
        if allow_all_origins
        else r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup error handlers
setup_error_handlers(app)

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat()
    }

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "DataSays API Server",
        "version": "2.0.0",
        "endpoints": {
            "health": "/health",
            "files": "/api/files",
            "query": "/api/query",
            "conversations": "/api/conversations"
        }
    }

# Include routers
app.include_router(files.router, prefix="/api/files", tags=["files"])
app.include_router(query.router, prefix="/api/query", tags=["query"])
app.include_router(conversations.router, prefix="/api/conversations", tags=["conversations"])

# 404 handler
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": f"Cannot {request.method} {request.url.path}",
            "availableEndpoints": {
                "health": "GET /health",
                "root": "GET /",
                "files": "POST /api/files/upload, GET /api/files/:fileId, DELETE /api/files/:fileId",
                "query": "POST /api/query or POST /api/query/stream (verified result with live Agent events)",
                "conversations": "GET/POST /api/conversations"
            }
        }
    )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
