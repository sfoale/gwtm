from fastapi import APIRouter, HTTPException, Depends, Request, Response, Body
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import json

from server.db.database import get_db
from server.db.models.pointing import Pointing
from server.db.models.instrument import Instrument
from server.db.models.pointing_event import PointingEvent
from server.db.models.gw_alert import GWAlert
from server.db.models.users import Users
from server.auth.auth import get_current_user
from server.schemas.doi import DOIRequestResponse, DOIPointingsResponse, DOIPointingInfo


router = APIRouter(tags=["DOI"])


@router.post("/request_doi", response_model=DOIRequestResponse)
async def request_doi(
        graceid: Optional[str] = Body(None, description="Grace ID of the GW event"),
        id: Optional[int] = Body(None, description="Pointing ID"),
        ids: Optional[List[int]] = Body(None, description="List of pointing IDs"),
        doi_group_id: Optional[int] = Body(None, description="DOI author group ID"),
        creators: Optional[List[Dict[str, str]]] = Body(None, description="List of creators for the DOI"),
        doi_url: Optional[str] = Body(None, description="Optional DOI URL if already exists"),
        db: Session = Depends(get_db),
        user=Depends(get_current_user)
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
        graceid = GWAlert.graceidfromalternate(graceid)
        filter_conditions.append(PointingEvent.graceid == graceid)
        filter_conditions.append(PointingEvent.pointingid == Pointing.id)

    # Handle id or ids
    if id:
        filter_conditions.append(Pointing.id == id)
    elif ids:
        filter_conditions.append(Pointing.id.in_(ids))

    if len(filter_conditions) == 1:  # Only the user filter
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
    gids = list(set([x.graceid for x in db.query(PointingEvent).filter(
        PointingEvent.pointingid.in_([x.id for x in doi_points])
    )]))

    if len(gids) > 1:
        raise HTTPException(status_code=400, detail="Pointings must be only for a single GW event")

    gid = gids[0]

    # Handle DOI creators
    if not creators:
        if doi_group_id:
            # Import the DOI author model here to avoid circular imports
            from server.db.models.doi_author import doi_author
            valid, creators = doi_author.construct_creators(doi_group_id, user.id)
            if not valid:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid doi_group_id. Make sure you are the User associated with the DOI group"
                )
        else:
            # Default to user as creator
            creators = [{"name": f"{user.firstname} {user.lastname}", "affiliation": ""}]
    else:
        # Validate creators
        for c in creators:
            if "name" not in c or "affiliation" not in c:
                raise HTTPException(
                    status_code=400,
                    detail="name and affiliation are required for DOI creators json list"
                )

    # Create or use provided DOI
    if doi_url:
        doi_id, doi_url = 0, doi_url
    else:
        # Get the alternate form of the graceid
        gid = GWAlert.alternatefromgraceid(gid)
        # Create the DOI
        from server.utils.function import create_pointing_doi
        doi_id, doi_url = create_pointing_doi(doi_points, gid, creators, inst_set)

    # Update pointing records with DOI information
    if doi_id is not None:
        for p in doi_points:
            p.doi_url = doi_url
            p.doi_id = doi_id

        db.commit()

    return DOIRequestResponse(DOI_URL=doi_url, WARNINGS=warnings)


@router.get("/doi_pointings", response_model=DOIPointingsResponse)
async def get_doi_pointings(
        db: Session = Depends(get_db),
        user=Depends(get_current_user)
):
    """
    Get all pointings with DOIs requested by the current user.

    Returns:
    - List of pointings with DOI information
    """
    # Query pointings with DOIs
    pointings = db.query(Pointing).filter(
        Pointing.submitterid == user.id,
        Pointing.doi_id != None  # Pointings that have a DOI
    ).all()

    result = []
    for pointing in pointings:
        # Get event information
        pointing_events = db.query(PointingEvent).filter(PointingEvent.pointingid == pointing.id).all()
        graceid = pointing_events[0].graceid if pointing_events else "Unknown"

        # Get instrument information
        instrument = db.query(Instrument).filter(Instrument.id == pointing.instrumentid).first()
        instrument_name = instrument.instrument_name if instrument else "Unknown"

        result.append(DOIPointingInfo(
            id=pointing.id,
            graceid=graceid,
            instrument_name=instrument_name,
            status=pointing.status,
            doi_url=pointing.doi_url,
            doi_id=pointing.doi_id
        ))

    return DOIPointingsResponse(pointings=result)


@router.post("/ajax_request_doi", response_model=str)
async def ajax_request_doi(
        graceid: str = Body(..., description="Grace ID of the GW event"),
        ids: str = Body(..., description="Comma-separated list of pointing IDs"),
        doi_group_id: Optional[str] = Body(None, description="DOI author group ID"),
        doi_url: Optional[str] = Body(None, description="Optional DOI URL if already exists"),
        db: Session = Depends(get_db),
        user=Depends(get_current_user)
):
    """
    AJAX endpoint for requesting a DOI for a set of pointings.
    This endpoint maintains backward compatibility with the Flask implementation.

    Parameters:
    - graceid: Grace ID of the GW event
    - ids: Comma-separated list of pointing IDs
    - doi_group_id: DOI author group ID
    - doi_url: Optional DOI URL if already exists

    Returns:
    - DOI URL as a string
    """
    # Parse IDs from comma-separated string
    pointing_ids = [int(x) for x in ids.split(',') if x.strip()]

    if not pointing_ids:
        raise HTTPException(status_code=400, detail="No pointing IDs provided")

    # Normalize graceid
    graceid = GWAlert.graceidfromalternate(graceid)

    # Get all pointings with these IDs that belong to this event
    points = db.query(Pointing).filter(
        Pointing.id.in_(pointing_ids),
        Pointing.id == PointingEvent.pointingid,
        PointingEvent.graceid == graceid
    ).all()

    if not points:
        raise HTTPException(status_code=404, detail="No valid pointings found")

    # Ensure user owns these pointings
    for p in points:
        if p.submitterid != user.id:
            raise HTTPException(
                status_code=403,
                detail=f"Not authorized to request DOI for pointing {p.id}"
            )

    # Get user information
    user_record = db.query(Users).filter(Users.id == user.id).first()

    # Handle DOI creators
    if doi_group_id:
        # Using DOI author model from database
        from server.db.models.doi_author import doi_author
        valid, creators = doi_author.construct_creators(doi_group_id, user.id)
        if not valid:
            creators = [{"name": f"{user_record.firstname} {user_record.lastname}", "affiliation": ""}]
    else:
        creators = [{"name": f"{user_record.firstname} {user_record.lastname}", "affiliation": ""}]

    # Get instrument names
    insts = db.query(Instrument).filter(Instrument.id.in_([p.instrumentid for p in points]))
    inst_set = list(set([i.instrument_name for i in insts]))

    # Create DOI or use existing URL
    if doi_url:
        doi_id, doi_url = 0, doi_url
    else:
        # Get the alternate form of the graceid
        gid = GWAlert.alternatefromgraceid(graceid)
        # Create the DOI
        from server.utils.function import create_pointing_doi
        doi_id, doi_url = create_pointing_doi(points, gid, creators, inst_set)

    # Update pointing records with DOI information
    if doi_id is not None:
        for p in points:
            p.doi_url = doi_url
            p.doi_id = doi_id

        db.commit()

    return doi_url

# Note: The API prefix is handled in main.py, so we don't need to include it here
