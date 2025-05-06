from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime
import json

from server.db.database import get_db
from server.db.models.pointing import Pointing
from server.db.models.users import Users
from server.db.models.gw_alert import GWAlert
from server.db.models.instrument import Instrument
from server.auth.auth import get_current_user

router = APIRouter(tags=["DOI"])

@router.post("/doi/request")
async def request_doi(
    pointings: List[int],
    doi_group_id: Optional[int] = None,
    doi_url: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Request a DOI for a set of pointings."""
    from server.utils.function import create_pointing_doi
    
    if not pointings:
        raise HTTPException(status_code=400, detail="No pointings specified")
    
    # Get all pointings by their IDs, along with the GW alert info
    db_pointings = db.query(Pointing).filter(Pointing.id.in_(pointings)).all()
    
    if not db_pointings:
        raise HTTPException(status_code=404, detail="No valid pointings found")
    
    # Check if user is authorized to request DOI for these pointings
    for pointing in db_pointings:
        if pointing.user_id != current_user.id and not current_user.adminuser:
            raise HTTPException(
                status_code=403, 
                detail=f"Not authorized to request DOI for pointing {pointing.id}"
            )
    
    # Get the alert ID from the first pointing
    alert_id = db_pointings[0].alert_id
    
    # Make sure all pointings are for the same alert
    if not all(p.alert_id == alert_id for p in db_pointings):
        raise HTTPException(
            status_code=400,
            detail="All pointings must be for the same GW alert"
        )
    
    # Get the alert graceid
    alert = db.query(GWAlert).filter(GWAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    graceid = alert.graceid
    
    # Get user details for DOI creators
    user = db.query(User).filter(User.id == current_user.id).first()
    
    # Set up creators list - either from DOI group or from the current user
    if doi_group_id:
        # This would normally fetch author information from a DOI group table
        # For now, we'll use a placeholder
        creators = [{"name": f"{user.firstname} {user.lastname}"}]
        
        # In a real implementation, you might do something like:
        # doi_group = db.query(DOIAuthorGroup).filter(DOIAuthorGroup.id == doi_group_id).first()
        # creators = json.loads(doi_group.creators) if doi_group else [{"name": f"{user.firstname} {user.lastname}"}]
    else:
        creators = [{"name": f"{user.firstname} {user.lastname}"}]
    
    # Get instrument names
    instrument_ids = [p.instrument_id for p in db_pointings]
    instruments = db.query(Instrument).filter(Instrument.id.in_(instrument_ids)).all()
    instrument_names = list(set(i.instrument_name for i in instruments))
    
    # If a DOI URL is provided, use it; otherwise, create a new DOI
    if doi_url:
        doi_id = 0  # Placeholder ID when using an existing DOI
    else:
        doi_id, doi_url = create_pointing_doi(db_pointings, graceid, creators, instrument_names)
    
    # Update pointings with DOI information
    for pointing in db_pointings:
        pointing.doi_requested = True
        pointing.doi_url = doi_url
        pointing.doi_id = doi_id
        # Ensure the submitter ID matches the user ID for DOI purposes
        pointing.submitter_id = current_user.id
    
    db.commit()
    
    return {
        "message": "DOI requested successfully", 
        "pointing_count": len(db_pointings),
        "doi_url": doi_url
    }

@router.get("/doi/pointings")
async def get_doi_pointings(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get all pointings with requested DOIs for the current user."""
    pointings = db.query(Pointing).filter(
        Pointing.user_id == current_user.id,
        Pointing.doi_requested == True
    ).all()
    
    result = []
    for pointing in pointings:
        # Get alert details
        alert = db.query(GWAlert).filter(GWAlert.id == pointing.alert_id).first()
        
        result.append({
            "id": pointing.id,
            "alert_name": alert.alert_name if alert else "Unknown",
            "instrument_name": pointing.instrument.instrument_name if pointing.instrument else "Unknown",
            "status": pointing.status,
            "doi_status": "Requested"
        })
    
    return result
