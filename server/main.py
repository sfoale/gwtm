from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import datetime
import uvicorn
import logging

from server.config import settings

from server.routes.pointing_routes import router as pointing_router
from server.routes.gw_alert_routes import router as gw_alert_router
from server.routes.candidate_routes import router as candidate_router
from server.routes.instrument_routes import router as instrument_router
from server.routes.galaxy_routes import router as galaxy_router
from server.routes.icecube_routes import router as icecube_router
from server.routes.admin_routes import router as admin_router
from server.routes.ui_routes import router as ui_router
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


app = FastAPI(
    title=settings.APP_NAME,
    description="Gravitational-Wave Treasure Map API",
    version="1.0.0",
    debug=settings.DEBUG,
)

# Define API version prefix
API_V1_PREFIX = "/api/v1"

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=settings.CORS_METHODS,
    allow_headers=settings.CORS_HEADERS,
)


@app.middleware("http")
async def lifespan_middleware(request: Request, call_next):
    async with lifespan_context():
        response = await call_next(request)
    return response

@asynccontextmanager
async def lifespan_context():
    logger.info("Application is starting up...")
    try:
        yield
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        logger.info("Application is shutting down...")
    

    
# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_detail = str(exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": error_detail},
    )

# API health check
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "time": datetime.datetime.now().isoformat(),
    }

# Include routers with the API prefix
app.include_router(pointing_router, prefix=API_V1_PREFIX)
app.include_router(gw_alert_router, prefix=API_V1_PREFIX)
app.include_router(candidate_router, prefix=API_V1_PREFIX) 
app.include_router(instrument_router, prefix=API_V1_PREFIX)
app.include_router(galaxy_router, prefix=API_V1_PREFIX)
app.include_router(icecube_router, prefix=API_V1_PREFIX)

# Include admin router without API prefix (matches original endpoint)
app.include_router(admin_router)

# Include UI-specific routes without the API prefix
app.include_router(ui_router)

if __name__ == "__main__":
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)