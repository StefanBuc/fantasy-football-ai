from fastapi import APIRouter

router = APIRouter(prefix="/api/health", tags=["health"])

@router.get("/")
def health_check():
    # Placeholder for health check logic
    return {"status": "healthy"}

@router.get("/ready")
def readiness_check():
    # Placeholder for readiness check logic
    return {"status": "ready"}