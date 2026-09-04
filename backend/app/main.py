from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from backend.app.core.config import settings
from backend.app.core.database import Base, engine
from backend.app.schemas.contracts import StandardResponse, ErrorDetail

# Import routers
from backend.app.api.v1.payments import router as payments_router
from backend.app.api.v1.recovery import router as recovery_router
from backend.app.api.v1.dashboard import router as dashboard_router
from backend.app.api.v1.metrics import router as metrics_router
from backend.app.api.v1.webhooks import router as webhooks_router
from backend.app.api.v1.audit import router as audit_router
from backend.app.api.v1.health import router as health_router

# Initialize tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom Exception Handlers for Fintech-grade structured errors (13_API_CONTRACTS.md Section 51)
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    code = "HTTP_ERROR"
    message = str(detail)
    details = None
    
    if isinstance(detail, dict):
        code = detail.get("code", "ERROR")
        message = detail.get("message", "An error occurred")
        details = detail.get("details")
        
    return JSONResponse(
        status_code=exc.status_code,
        content=StandardResponse(
            success=False,
            error=ErrorDetail(code=code, message=message, details=details)
        ).model_dump()
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=StandardResponse(
            success=False,
            error=ErrorDetail(
                code="VALIDATION_ERROR",
                message="Request validation failed",
                details={"errors": errors}
            )
        ).model_dump()
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=StandardResponse(
            success=False,
            error=ErrorDetail(
                code="INTERNAL_ERROR",
                message="Internal server error"
            )
        ).model_dump()
    )

# Register routers
app.include_router(payments_router, prefix=settings.API_V1_STR)
app.include_router(recovery_router, prefix=settings.API_V1_STR)
app.include_router(dashboard_router, prefix=settings.API_V1_STR)
app.include_router(metrics_router, prefix=settings.API_V1_STR)
app.include_router(webhooks_router, prefix=settings.API_V1_STR)
app.include_router(audit_router, prefix=settings.API_V1_STR)
app.include_router(health_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "api_docs": f"{settings.API_V1_STR}/docs"
    }
