from fastapi import APIRouter

router = APIRouter(prefix="/api/health", tags=["health"])

@router.get("/")
def health_check():
    # Placeholder for health check logic
    return {"status": "healthy"}

@router.get("/ready")
def readiness_check():
    from app.config.security import auth_enabled, public_origin
    from app.services.account_store import accounts
    from fastapi import HTTPException
    if auth_enabled():
        try:
            public_origin()
            if accounts.owner() is None:
                raise RuntimeError("Owner setup is incomplete.")
        except RuntimeError as error:
            raise HTTPException(503, "Owner setup or public URL configuration is incomplete.") from error
    return {"status": "ready"}
