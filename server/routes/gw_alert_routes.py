from fastapi import APIRouter, HTTPException, Depends, Query, Body, Response
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import json

from server.db.database import get_db
from server.db.models.gw_alert import GWAlert
from server.schemas.gw_alert import GWAlertSchema
from server.auth.auth import get_current_user, verify_admin

router = APIRouter(tags=["gw_alerts"])

@router.get("/query_alerts", response_model=List[GWAlertSchema])
async def query_alerts(
    graceid: Optional[str] = None,
    alert_type: Optional[str] = None,
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Query GW alerts with optional filters.
    
    Parameters:
    - graceid: Filter by Grace ID
    - alert_type: Filter by alert type
    
    Returns a list of GW Alert objects
    """
    filter_conditions = []
    
    if graceid:
        # Handle alternative GraceID format if needed
        # Implementation will depend on the graceidfromalternate function
        filter_conditions.append(GWAlert.graceid == graceid)
    
    if alert_type:
        filter_conditions.append(GWAlert.alert_type == alert_type)
    
    alerts = db.query(GWAlert).filter(*filter_conditions).order_by(GWAlert.datecreated.desc()).all()
    
    return alerts


@router.post("/post_alert", response_model=GWAlertSchema)
async def post_alert(
        alert_data: GWAlertSchema,
        db: Session = Depends(get_db),
        user=Depends(verify_admin)  # Only admin can post alerts
):
    """
    Post a new GW alert (admin only).

    Parameters:
    - Alert data in the request body

    Returns the created GW Alert object
    """
    alert_instance = GWAlert(**alert_data.dict())
    db.add(alert_instance)
    db.commit()
    db.refresh(alert_instance)

    return alert_instance

@router.get("/gw_skymap")
async def get_gw_skymap(
    graceid: str = Query(..., description="Grace ID of the GW event"),
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get the skymap for a GW alert.
    
    Parameters:
    - graceid: The Grace ID of the GW event
    
    Returns the skymap FITS file
    """
    # This implementation is a placeholder
    # The actual implementation will need to handle file retrieval from storage
    # Similar to the original Flask code
    
    # Get the latest alert for this graceid
    alerts = db.query(GWAlert).filter(GWAlert.graceid == graceid).order_by(GWAlert.datecreated.desc()).all()
    
    if not alerts:
        raise HTTPException(status_code=404, detail=f"No alert found with graceid: {graceid}")
    
    # Extract alert info
    alert = alerts[0]
    alert_types = [x.alert_type for x in alerts]
    latest_alert_type = alert.alert_type
    num = len([x for x in alert_types if x == latest_alert_type]) - 1
    alert_type = latest_alert_type if num < 1 else latest_alert_type + str(num)
    
    # Build path info
    path_info = f"{graceid}-{alert_type}"
    skymap_path = f"fit/{path_info}.fits.gz"
    
    # This would be where we'd retrieve and return the file
    # For now, returning a placeholder
    return {"status": "implementation_pending", "file_path": skymap_path}

@router.get("/gw_contour")
async def get_gw_contour(
    graceid: str = Query(..., description="Grace ID of the GW event"),
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get the contour for a GW alert.
    
    Parameters:
    - graceid: The Grace ID of the GW event
    
    Returns the contour JSON file
    """
    # Normalize the graceid
    graceid = GWAlert.graceidfromalternate(graceid)
    
    # Get the latest alert for this graceid
    alerts = db.query(GWAlert).filter(GWAlert.graceid == graceid).order_by(GWAlert.datecreated.desc()).all()
    
    if not alerts:
        raise HTTPException(status_code=404, detail=f"No alert found with graceid: {graceid}")
    
    # Extract alert info
    alert = alerts[0]
    alert_types = [x.alert_type for x in alerts]
    latest_alert_type = alert.alert_type
    num = len([x for x in alert_types if x == latest_alert_type]) - 1
    alert_type = latest_alert_type if num < 1 else latest_alert_type + str(num)
    
    # Build path info
    path_info = f"{graceid}-{alert_type}"
    contour_path = f"fit/{path_info}-contours-smooth.json"
    
    try:
        from server.utils.gwtm_io import download_gwtm_file
        from server.config import config
        file_content = download_gwtm_file(filename=contour_path, source=config.STORAGE_BUCKET_SOURCE, config=config)
        return Response(content=file_content, media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Error in retrieving Contour file: {contour_path}")

@router.get("/grb_moc_file")
async def get_grbmoc(
    graceid: str = Query(..., description="Grace ID of the GW event"),
    instrument: str = Query(..., description="Instrument name (gbm, lat, or bat)"),
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get the GRB MOC file for a GW alert.
    
    Parameters:
    - graceid: The Grace ID of the GW event
    - instrument: Instrument name (gbm, lat, or bat)
    
    Returns the MOC file
    """
    # Normalize the graceid
    graceid = GWAlert.graceidfromalternate(graceid)
    
    # Validate instrument
    instrument = instrument.lower()
    if instrument not in ['gbm', 'lat', 'bat']:
        raise HTTPException(
            status_code=400, 
            detail="Valid instruments are in ['gbm', 'lat', 'bat']"
        )
    
    # Map instrument names to their full names
    instrument_dictionary = {'gbm': 'Fermi', 'lat': 'LAT', 'bat': 'BAT'}
    
    # Build path
    moc_filepath = f"fit/{graceid}-{instrument_dictionary[instrument]}.json"
    
    try:
        from server.utils.gwtm_io import download_gwtm_file
        from server.config import config
        file_content = download_gwtm_file(filename=moc_filepath, source=config.STORAGE_BUCKET_SOURCE, config=config)
        return Response(content=file_content, media_type="application/json")
    except Exception as e:
        raise HTTPException(
            status_code=404, 
            detail=f"MOC file for GW-Alert: '{graceid}' and instrument: '{instrument}' does not exist!"
        )

@router.post("/del_test_alerts")
async def del_test_alerts(
    db: Session = Depends(get_db),
    user = Depends(verify_admin)  # Only admin can delete test alerts
):
    """
    Delete test alerts (admin only).
    
    This endpoint removes test alerts from the database.
    """
    # This implementation is a placeholder
    # The actual implementation will need to handle the complex deletion logic
    # from the original code
    
    return {"status": "implementation_pending", "message": "Test alert deletion will be implemented"}
