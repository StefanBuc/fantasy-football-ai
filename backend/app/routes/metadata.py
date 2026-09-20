from fastapi import APIRouter

router = APIRouter(prefix="/api/metadata", tags=["metadata"])

@router.get("/")
def get_metadata():
    # Placeholder for fetching metadata from a database or service
    metadata = {
        "app_name": "Fantasy Football AI",
        "version": "1.0.0",
        "description": "An AI-powered fantasy football application.",
    }
    return {"metadata": metadata}