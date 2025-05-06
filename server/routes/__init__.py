from fastapi import APIRouter
from .pointing_routes import router as pointing_router
from .ui_routes import router as ui_router
from .event_routes import router as event_router
from .doi_routes import router as doi_router

router = APIRouter()

# Include all routers
router.include_router(pointing_router)
router.include_router(event_router)
router.include_router(doi_router)
# UI routes don't get the API prefix, they're handled separately in main.py