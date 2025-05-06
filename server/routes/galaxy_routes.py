from fastapi import APIRouter, HTTPException, Depends, Query, Body
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from sqlalchemy import func, or_
import json

from server.db.database import get_db
from server.db.models.gw_alert import GWAlert
from server.db.models.gw_galaxy import GWGalaxyEntry
from server.db.models.users import Users
from server.auth.auth import get_current_user
from server.schemas.gw_galaxy import PostEventGalaxiesRequest, PostEventGalaxiesResponse
from server.schemas.gw_galaxy import GWGalaxyEntrySchema

router = APIRouter(tags=["galaxies"])


@router.get("/event_galaxies", response_model=List[GWGalaxyEntrySchema])
async def get_event_galaxies(
        graceid: str = Query(..., description="Grace ID of the GW event"),
        timesent_stamp: Optional[str] = None,
        listid: Optional[int] = None,
        groupname: Optional[str] = None,
        score_gt: Optional[float] = None,
        score_lt: Optional[float] = None,
        db: Session = Depends(get_db),
        user=Depends(get_current_user)
):
    """
    Get galaxies associated with a GW event.
    """
    filter_conditions = [GWGalaxyEntry.listid == GWGalaxyEntry.id]
    graceid = GWAlert.graceidfromalternate(graceid)
    filter_conditions.append(GWGalaxyEntry.graceid == graceid)

    if timesent_stamp:
        from datetime import datetime, timedelta
        try:
            time = datetime.strptime(timesent_stamp, "%Y-%m-%dT%H:%M:%S.%f")
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Error parsing date. Should be %Y-%m-%dT%H:%M:%S.%f format. e.g. 2019-05-01T12:00:00.00"
            )
        alert = db.query(GWAlert).filter(
            GWAlert.timesent < time + timedelta(seconds=15),
            GWAlert.timesent > time - timedelta(seconds=15),
            GWAlert.graceid == graceid
        ).first()
        if not alert:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid 'timesent_stamp' for event\n Please visit http://treasuremap.space/alerts?graceids={graceid} for valid timesent stamps for this event"
            )
        filter_conditions.append(GWGalaxyEntry.alertid == alert.id)

    if listid:
        filter_conditions.append(GWGalaxyEntry.id == listid)
    if groupname:
        filter_conditions.append(GWGalaxyEntry.groupname == groupname)
    if score_gt is not None:
        filter_conditions.append(GWGalaxyEntry.score >= score_gt)
    if score_lt is not None:
        filter_conditions.append(GWGalaxyEntry.score <= score_lt)

    galaxy_entries = db.query(GWGalaxyEntry).filter(*filter_conditions).all()

    # Convert GeoAlchemy2 Geography to a dictionary for Pydantic
    for entry in galaxy_entries:
        if entry.position:
            shape = to_shape(entry.position)
            entry.position = {"latitude": shape.y, "longitude": shape.x}

    return galaxy_entries


@router.post("/event_galaxies", response_model=PostEventGalaxiesResponse)
async def post_event_galaxies(
        request: PostEventGalaxiesRequest,
        db: Session = Depends(get_db),
        user=Depends(get_current_user)
):
    """
    Post galaxies associated with a GW event.
    """
    # Process graceid
    graceid = GWAlert.graceidfromalternate(request.graceid)

    # Parse timesent_stamp
    from datetime import datetime, timedelta
    try:
        time = datetime.strptime(request.timesent_stamp, "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Error parsing date. Should be %Y-%m-%dT%H:%M:%S.%f format. e.g. 2019-05-01T12:00:00.00"
        )

    # Find the alert
    alert = db.query(GWAlert).filter(
        GWAlert.timesent < time + timedelta(seconds=15),
        GWAlert.timesent > time - timedelta(seconds=15),
        GWAlert.graceid == graceid
    ).first()

    if not alert:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid 'timesent_stamp' for event\n Please visit http://treasuremap.space/alerts?graceids={graceid} for valid timesent stamps for this event"
        )

    # Handle groupname
    groupname = request.groupname or user.username

    # Handle DOI creators
    post_doi = request.request_doi
    doi_string = ". "

    if post_doi:
        if request.creators:
            for c in request.creators:
                if 'name' not in c or 'affiliation' not in c:
                    raise HTTPException(
                        status_code=400,
                        detail="name and affiliation are required for DOI creators json list"
                    )
        elif request.doi_group_id:
            valid, creators = Users.construct_creators(request.doi_group_id, user.id)
            if not valid:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid doi_group_id. Make sure you are the User associated with the DOI group"
                )
        else:
            creators = [{'name': f"{user.firstname} {user.lastname}"}]

    # Create galaxy list
    gw_galaxy_list = GWGalaxyEntry(
        submitterid=user.id,
        graceid=graceid,
        alertid=alert.id,
        groupname=groupname,
        reference=request.reference,
    )
    db.add(gw_galaxy_list)
    db.flush()

    # Process galaxies
    valid_galaxies = []
    errors = []
    warnings = []

    for g in request.galaxies:
        gw_galaxy_entry = GWGalaxyEntry()
        validation_result = gw_galaxy_entry.from_json(g)

        if validation_result.valid:
            gw_galaxy_entry.listid = gw_galaxy_list.id
            db.add(gw_galaxy_entry)
            valid_galaxies.append(gw_galaxy_entry)

            if validation_result.warnings:
                warnings.append(["Object: " + json.dumps(g), validation_result.warnings])
        else:
            errors.append(["Object: " + json.dumps(g), validation_result.errors])

    db.flush()

    # Handle DOI if requested
    if post_doi:
        from server.utils import function
        doi_id, url = function.create_galaxy_score_doi(valid_galaxies, creators, request.reference, graceid,
                                                       alert.alert_type)

        if url is None and doi_id is not None:
            errors.append(
                "There was an error with the DOI request. Please ensure that author group's ORIC/GND values are accurate")
        else:
            gw_galaxy_list.doi_id = doi_id
            gw_galaxy_list.doi_url = url
            doi_string = f". DOI url: {url}."

    db.commit()

    return PostEventGalaxiesResponse(
        message=f"Successful adding of {len(valid_galaxies)} galaxies for event {graceid}{doi_string} List ID: {gw_galaxy_list.id}",
        errors=errors,
        warnings=warnings
    )


@router.post("/remove_event_galaxies", response_model=Dict[str, Any])
async def remove_event_galaxies(
        listid: int = Body(...),
        db: Session = Depends(get_db),
        user=Depends(get_current_user)
):
    """
    Remove galaxies associated with a GW event.
    """
    # Find galaxy list
    galaxy_list = db.query(GWGalaxyList).filter(GWGalaxyList.id == listid).first()

    if not galaxy_list:
        raise HTTPException(
            status_code=404,
            detail='No galaxies with that listid'
        )

    # Check permissions
    if user.id != galaxy_list.submitterid:
        raise HTTPException(
            status_code=403,
            detail='You can only delete information related to your api_token! shame shame'
        )

    # Find and delete galaxy entries
    galaxy_entries = db.query(GWGalaxyEntry).filter(GWGalaxyEntry.listid == listid).all()

    db.delete(galaxy_list)
    for entry in galaxy_entries:
        db.delete(entry)

    db.commit()

    return {"message": "Successfully deleted your galaxy list"}


@router.get("/glade", response_model=List[Dict[str, Any]])
async def get_galaxies(
        ra: Optional[float] = None,
        dec: Optional[float] = None,
        name: Optional[str] = None,
        db: Session = Depends(get_db),
        user=Depends(get_current_user)
):
    """
    Get galaxies from the GLADE catalog.
    """
    from server.utils.function import isFloat

    filter_conditions = []
    filter1 = []
    filter1.append(models.glade_2p3.pgc_number != -1)
    filter1.append(models.glade_2p3.distance > 0)
    filter1.append(models.glade_2p3.distance < 100)

    # Create base query
    trim = db.query(models.glade_2p3).filter(*filter1)

    # Handle orderby
    orderby = []

    # Handle ra and dec
    if ra and dec and isFloat(ra) and isFloat(dec):
        geom = f"SRID=4326;POINT({ra} {dec})"
        orderby.append(func.ST_Distance(models.glade_2p3.position, geom))

    # Handle name search
    if name:
        or_conditions = []
        or_conditions.append(models.glade_2p3._2mass_name.contains(name.strip()))
        or_conditions.append(models.glade_2p3.gwgc_name.contains(name.strip()))
        or_conditions.append(models.glade_2p3.hyperleda_name.contains(name.strip()))
        or_conditions.append(models.glade_2p3.sdssdr12_name.contains(name.strip()))
        filter_conditions.append(or_(*or_conditions))

    # Execute query
    galaxies = trim.filter(*filter_conditions).order_by(*orderby).limit(15).all()

    # Parse galaxies to the expected format
    galaxies_parsed = [galaxy.parse for galaxy in galaxies]

    return galaxies_parsed
