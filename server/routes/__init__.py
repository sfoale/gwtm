from fastapi import APIRouter
from .admin_routes import router as admin_router
from .candidate_routes import router as candidate_router
from .doi_routes import router as doi_router
from .event_routes import router as event_router
from .galaxy_routes import router as galaxy_router
from .gw_alert_routes import router as gw_alert_router
from .icecube_routes import router as icecube_router
from .instrument_routes import router as instrument_router
from .pointing_routes import router as pointing_router
from .ui_routes import router as ui_router


router = APIRouter()

# Include all routers
router.include_router(pointing_router)
router.include_router(event_router)
router.include_router(doi_router)
router.include_router(gw_alert_router)
router.include_router(admin_router)
router.include_router(instrument_router)
router.include_router(galaxy_router)
router.include_router(icecube_router)
router.include_router(candidate_router)


# UI routes don't get the API prefix, they're handled separately in main.py
