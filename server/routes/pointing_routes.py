from fastapi import APIRouter, HTTPException, Depends, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import func
import datetime
from typing import List, Optional, Dict, Any

from server.db.models.pointing import Pointing
from server.db.models.instrument import Instrument
from server.schemas.pointing import PointingSchema
from server.db.database import get_db
from server.auth.auth import get_current_user
from server.db.models.gw_alert import GWAlert
from server.db.models.pointing_event import PointingEvent
import shapely.wkb

router = APIRouter(tags=["pointings"])

@router.post("/pointings", response_model=List[PointingSchema])
def add_pointings(pointings: List[PointingSchema], db: Session = Depends(get_db)):
    """
    Add new pointings to the database.
    """
    try:
        new_pointings = []
        for pointing_data in pointings:
            pointing = Pointing(**pointing_data.dict())
            db.add(pointing)
            new_pointings.append(pointing)
        db.commit()
        return new_pointings
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/pointings", response_model=List[PointingSchema])
def get_pointings(
    graceid: Optional[str] = Query(None, description="Grace ID of the GW event"),
    instrumentid: Optional[int] = Query(None, description="Instrument ID"),
    status: Optional[str] = Query(None, description="Status of the pointings"),
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Retrieve pointings from the database with optional filters.
    """
    try:
        # Build the filter conditions
        filter_conditions = [Pointing.submitterid == user.id]
        
        if graceid:
            # Normalize the graceid
            graceid = GWAlert.graceidfromalternate(graceid)
            filter_conditions.append(Pointing.id == models.pointing_event.pointingid)
            filter_conditions.append(models.pointing_event.graceid == graceid)
        
        if instrumentid:
            filter_conditions.append(Pointing.instrumentid == instrumentid)
        
        if status:
            filter_conditions.append(Pointing.status == status)
        
        # Query the database
        pointings = db.query(Pointing).filter(*filter_conditions).all()
        
        # Process the position field
        for pointing in pointings:
            if pointing.position:
                position = shapely.wkb.loads(bytes(pointing.position.data))
                pointing.position = str(position)
        
        return pointings
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/update_pointings")
async def update_pointings(
    status: str, 
    ids: List[int], 
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Update the status of planned pointings.
    
    Parameters:
    - status: The new status for the pointings (only "cancelled" is currently supported)
    - ids: List of pointing IDs to update
    
    Returns:
    - Message with the number of updated pointings
    """
    if status != "cancelled":
        raise HTTPException(status_code=400, detail="Only 'cancelled' status is allowed.")
    try:
        # Add a filter to ensure user can only update their own pointings
        pointings = db.query(Pointing).filter(
            Pointing.id.in_(ids),
            Pointing.submitterid == user.id,
            Pointing.status == "planned"  # Only planned pointings can be cancelled
        ).all()
        
        for pointing in pointings:
            pointing.status = status
            pointing.dateupdated = datetime.datetime.now()
            
        db.commit()
        return {"message": f"Updated {len(pointings)} pointings successfully."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/cancel_all")
async def cancel_all(
    graceid: str = Body(..., description="Grace ID of the GW event"),
    instrumentid: int = Body(..., description="Instrument ID to cancel pointings for"),
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Cancel all planned pointings for a specific GW event and instrument.
    
    Parameters:
    - graceid: Grace ID of the GW event
    - instrumentid: Instrument ID to cancel pointings for
    
    Returns:
    - Message with the number of cancelled pointings
    """
    # Validate instrumentid
    instrument = db.query(Instrument).filter(Instrument.id == instrumentid).first()
    if not instrument:
        raise HTTPException(status_code=404, detail=f"Instrument with ID {instrumentid} not found")
    
    # Build the filter
    filter_conditions = [
        Pointing.status == "planned",
        Pointing.submitterid == user.id,
        Pointing.instrumentid == instrumentid
    ]
    
    # Add GW event filter using pointing_event relation
    if graceid:
        from server.db.models.gw_alert import GWAlert
        # Normalize the graceid
        graceid = GWAlert.graceidfromalternate(graceid)
        # Add the join condition
        filter_conditions.append(Pointing.id == models.pointing_event.pointingid)
        filter_conditions.append(models.pointing_event.graceid == graceid)
    
    # Query the pointings
    pointings = db.query(Pointing).filter(*filter_conditions)
    pointing_count = pointings.count()
    
    # Update the status
    for pointing in pointings:
        pointing.status = "cancelled"
        pointing.dateupdated = datetime.datetime.now()
    
    db.commit()
    
    return {"message": f"Updated {pointing_count} Pointings successfully"}

@router.post("/request_doi")
async def request_doi(
    graceid: Optional[str] = Body(None, description="Grace ID of the GW event"),
    id: Optional[int] = Body(None, description="Pointing ID"),
    ids: Optional[List[int]] = Body(None, description="List of pointing IDs"),
    doi_group_id: Optional[int] = Body(None, description="DOI author group ID"),
    creators: Optional[List[Dict[str, str]]] = Body(None, description="List of creators for the DOI"),
    doi_url: Optional[str] = Body(None, description="Optional DOI URL if already exists"),
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Request a DOI for completed pointings.
    
    Parameters:
    - graceid: Grace ID of the GW event
    - id: Single pointing ID
    - ids: List of pointing IDs
    - doi_group_id: DOI author group ID
    - creators: List of creators for the DOI
    - doi_url: Optional DOI URL if already exists
    
    Returns:
    - DOI URL and warnings
    """
    # Build the filter for pointings
    filter_conditions = [Pointing.submitterid == user.id]
    
    # Handle graceid
    if graceid:
        from server.db.models.gw_alert import GWAlert
        # Normalize the graceid
        graceid = GWAlert.graceidfromalternate(graceid)
        # Add the join condition
        filter_conditions.append(Pointing.id == models.pointing_event.pointingid)
        filter_conditions.append(models.pointing_event.graceid == graceid)
    
    # Handle id or ids
    if id:
        filter_conditions.append(Pointing.id == id)
    elif ids:
        filter_conditions.append(Pointing.id.in_(ids))
    
    if len(filter_conditions) == 1:
        raise HTTPException(status_code=400, detail="Insufficient filter parameters")
    
    # Query the pointings
    points = db.query(Pointing).filter(*filter_conditions).all()
    
    # Validate and prepare for DOI request
    warnings = []
    doi_points = []
    
    for p in points:
        if p.status == "completed" and p.submitterid == user.id and p.doi_id is None:
            doi_points.append(p)
        else:
            warnings.append(f"Invalid doi request for pointing: {p.id}")
    
    if len(doi_points) == 0:
        raise HTTPException(status_code=400, detail="No pointings to give DOI")
    
    # Get the instruments
    insts = db.query(Instrument).filter(Instrument.id.in_([x.instrumentid for x in doi_points]))
    inst_set = list(set([x.instrument_name for x in insts]))
    
    # Get the GW event IDs
    gids = list(set([x.graceid for x in db.query(models.pointing_event).filter(
        models.pointing_event.pointingid.in_([x.id for x in doi_points])
    )]))
    
    if len(gids) > 1:
        raise HTTPException(status_code=400, detail="Pointings must be only for a single GW event")
    
    gid = gids[0]
    
    # Handle DOI creators
    if not creators:
        if doi_group_id:
            # Using the construct_creators function from the user model
            valid, creators = models.users.construct_creators(doi_group_id, user.id)
            if not valid:
                raise HTTPException(
                    status_code=400, 
                    detail="Invalid doi_group_id. Make sure you are the User associated with the DOI group"
                )
        else:
            # Default to user as creator
            creators = [{"name": f"{user.firstname} {user.lastname}"}]
    else:
        # Validate creators
        for c in creators:
            if "name" not in c.keys() or "affiliation" not in c.keys():
                raise HTTPException(
                    status_code=400,
                    detail="name and affiliation are required for DOI creators json list"
                )
    
    # Create or use provided DOI
    if doi_url:
        doi_id, doi_url = 0, doi_url
    else:
        # Get the alternate form of the graceid
        gid = models.gw_alert.alternatefromgraceid(gid)
        # Create the DOI
        from server.utils.function import create_pointing_doi
        doi_id, doi_url = create_pointing_doi(doi_points, gid, creators, inst_set)
    
    # Update pointing records with DOI information
    if doi_id is not None:
        for p in doi_points:
            p.doi_url = doi_url
            p.doi_id = doi_id
        
        db.commit()
    
    return {"DOI URL": doi_url, "WARNINGS": warnings}
