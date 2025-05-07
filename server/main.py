from fastapi import FastAPI, Request, status, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

import datetime
import uvicorn
import logging

from server.config import settings
from server.db.database import get_db

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


@app.get("/service-status")
async def service_status(db: Session = Depends(get_db)):
    """
    Detailed service status endpoint that checks database and Redis connections.

    Returns:
        Dict with status of database and Redis connections, plus detailed info
    """
    status = {
        "database_status": "unknown",
        "redis_status": "unknown",
        "details": {
            "database": {},
            "redis": {}
        }
    }

    # Check database connection with detailed info
    try:
        # Get connection parameters from settings
        db_host = settings.DB_HOST
        db_port = settings.DB_PORT
        db_name = settings.DB_NAME

        # Store connection info
        status["details"]["database"] = {
            "host": db_host,
            "port": db_port,
            "name": db_name
        }

        # Test actual connection
        result = db.execute("SELECT 1").first()
        if result and result[0] == 1:
            status["database_status"] = "connected"
        else:
            status["database_status"] = "disconnected"
    except Exception as e:
        status["database_status"] = "disconnected"
        status["details"]["database"]["error"] = str(e)

    # Check Redis connection with detailed info
    try:
        # Get Redis connection parameters
        redis_url = os.environ.get('REDIS_URL', 'redis://redis:6379/0')

        # Parse the URL for debug info
        if redis_url.startswith('redis://'):
            redis_host = redis_url.split('redis://')[1].split(':')[0]
            redis_port = redis_url.split(':')[-1].split('/')[0]
        else:
            redis_host = 'unknown'
            redis_port = 'unknown'

        # Store connection info
        status["details"]["redis"] = {
            "host": redis_host,
            "port": redis_port,
            "url": redis_url
        }

        # Test actual connection
        redis_client = redis.from_url(redis_url)
        if redis_client.ping():
            status["redis_status"] = "connected"
        else:
            status["redis_status"] = "disconnected"
    except Exception as e:
        status["redis_status"] = "disconnected"
        status["details"]["redis"]["error"] = str(e)

    return status

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
