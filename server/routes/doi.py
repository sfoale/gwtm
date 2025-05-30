import json

from fastapi import APIRouter, Depends, Request, Response, Body
from server.utils.error_handling import validation_exception, not_found_exception, permission_exception
from server.core.enums.pointing_status import pointing_status as pointing_status_enum
from sqlalchemy.orm import Session
from typing import List, Dict, Optional

from server.db.database import get_db
from server.db.models.pointing import Pointing
from server.db.models.instrument import Instrument
from server.db.models.pointing_event import PointingEvent
from server.db.models.gw_alert import GWAlert
from server.db.models.users import Users
from server.db.models.doi_author import DOIAuthor, DOIAuthorGroup
from server.auth.auth import get_current_user
from server.schemas.doi import (
    DOIAuthorSchema,
    DOIAuthorGroupSchema,
    DOIPointingInfo,
    DOIPointingsResponse,
    DOIRequestResponse
)
from server.utils.function import create_pointing_doi

router = APIRouter(tags=["DOI"])


# @router.post("/request_doi", response_model=DOIRequestResponse)
# async def request_doi(
#         graceid: Optional[str] = Body(None, description="Grace ID of the GW event"),
#         id: Optional[int] = Body(None, description="Pointing ID"),
#         ids: Optional[List[int]] = Body(None, description="List of pointing IDs"),
#         doi_group_id: Optional[str] = Body(None, description="DOI author group ID"),
#         creators: Optional[List[Dict[str, str]]] = Body(None, description="List of creators for the DOI"),
#         doi_url: Optional[str] = Body(None, description="Optional DOI URL if already exists"),
#         db: Session = Depends(get_db),
#         user=Depends(get_current_user)
# ):
#     """
#     Request a DOI for completed pointings.
#
#     Parameters:
#     - graceid: Grace ID of the GW event
#     - id: Single pointing ID
#     - ids: List of pointing IDs
#     - doi_group_id: DOI author group ID
#     - creators: List of creators for the DOI
#     - doi_url: Optional DOI URL if already exists
#
#     Returns:
#     - DOI URL and warnings
#     """
#     # Build the filter for pointings
#     filter_conditions = [Pointing.submitterid == user.id]
#
#     # Handle graceid
#     if graceid:
#         graceid = GWAlert.graceidfromalternate(graceid)
#         filter_conditions.append(PointingEvent.graceid == graceid)
#         filter_conditions.append(PointingEvent.pointingid == Pointing.id)
#
#     # Handle id or ids
#     if id:
#         filter_conditions.append(Pointing.id == id)
#     elif ids:
#         filter_conditions.append(Pointing.id.in_(ids))
#
#     if len(filter_conditions) == 1:  # Only the user filter
#         raise validation_exception(
#             message="Insufficient filter parameters",
#             errors=["Please provide either graceid, id, or ids parameter"]
#         )
#
#     # Query the pointings
#     points = db.query(Pointing).filter(*filter_conditions).all()
#
#     # Validate and prepare for DOI request
#     warnings = []
#     doi_points = []
#
#     print(f'Dump of points: {points}')
#     for p in points:
#         if p.status == pointing_status_enum.completed and p.submitterid == user.id and p.doi_id is None:
#             doi_points.append(p)
#         else:
#             warnings.append(f"Invalid doi request for pointing: {p.id}")
#
#     if len(doi_points) == 0:
#         raise validation_exception(
#             message="No valid pointings found for DOI request",
#             errors=["All pointings must be completed, owned by you, and not already have a DOI"]
#         )
#
#     # Get the instruments
#     insts = db.query(Instrument).filter(Instrument.id.in_([x.instrumentid for x in doi_points]))
#     inst_set = list(set([x.instrument_name for x in insts]))
#
#     # Get the GW event IDs
#     gids = list(set([x.graceid for x in db.query(PointingEvent).filter(
#         PointingEvent.pointingid.in_([x.id for x in doi_points])
#     )]))
#
#     if len(gids) > 1:
#         raise validation_exception(
#             message="Multiple events detected",
#             errors=["Pointings must be only for a single GW event for a DOI request"]
#         )
#
#     gid = gids[0]
#
#     # Handle DOI creators
#     if not creators:
#         if doi_group_id:
#             valid, creators_list = DOIAuthor.construct_creators(doi_group_id, user.id, db)
#             if not valid:
#                 raise validation_exception(
#                     message="Invalid DOI group ID",
#                     errors=["Make sure you are the User associated with the DOI group"]
#                 )
#             creators = creators_list
#         else:
#             # Default to user as creator
#             user_record = db.query(Users).filter(Users.id == user.id).first()
#             creators = [{"name": f"{user_record.firstname} {user_record.lastname}", "affiliation": ""}]
#     else:
#         # Validate creators
#         for c in creators:
#             if "name" not in c or "affiliation" not in c:
#                 raise validation_exception(
#                     message="Invalid DOI creator information",
#                     errors=["name and affiliation are required for each creator in the list"]
#                 )
#
#     # Create or use provided DOI
#     if doi_url:
#         doi_id, doi_url = 0, doi_url
#     else:
#         # Get the alternate form of the graceid
#         gid = GWAlert.alternatefromgraceid(gid)
#         # Create the DOI
#         doi_id, doi_url = create_pointing_doi(doi_points, gid, creators, inst_set)
#
#     # Update pointing records with DOI information
#     if doi_id is not None:
#         for p in doi_points:
#             p.doi_url = doi_url
#             p.doi_id = doi_id
#
#         db.commit()
#
#     return DOIRequestResponse(DOI_URL=doi_url, WARNINGS=warnings)


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
    # Query pointings with DOIs, ensuring we only get pointings that actually have DOI information
    pointings = db.query(Pointing).filter(
        Pointing.submitterid == user.id,
        Pointing.doi_id.isnot(None),  # Changed from != None to .isnot(None) for proper SQLAlchemy syntax
        Pointing.doi_url.isnot(None)   # Also check that doi_url is not None
    ).all()

    result = []
    for pointing in pointings:
        # Get event information - need to join with PointingEvent to get graceid
        pointing_events = db.query(PointingEvent).filter(PointingEvent.pointingid == pointing.id).all()
        graceid = pointing_events[0].graceid if pointing_events else "Unknown"

        # Get instrument information
        instrument = db.query(Instrument).filter(Instrument.id == pointing.instrumentid).first()
        instrument_name = instrument.instrument_name if instrument else "Unknown"

        # Convert status enum to string if needed
        status_str = pointing.status.name if hasattr(pointing.status, 'name') else str(pointing.status)

        result.append(DOIPointingInfo(
            id=pointing.id,
            graceid=graceid,
            instrument_name=instrument_name,
            status=status_str,
            doi_url=pointing.doi_url,
            doi_id=pointing.doi_id
        ))

    return DOIPointingsResponse(pointings=result)

@router.get("/doi_author_groups", response_model=List[DOIAuthorGroupSchema])
async def get_doi_author_groups(
        db: Session = Depends(get_db),
        user=Depends(get_current_user)
):
    """
    Get all DOI author groups for the current user.

    Returns:
    - List of DOI author groups
    """
    groups = db.query(DOIAuthorGroup).filter(DOIAuthorGroup.userid == user.id).all()
    return groups


@router.get("/doi_authors/{group_id}", response_model=List[DOIAuthorSchema])
async def get_doi_authors(
        group_id: int,
        db: Session = Depends(get_db),
        user=Depends(get_current_user)
):
    """
    Get all DOI authors for a specific group.

    Parameters:
    - group_id: DOI author group ID

    Returns:
    - List of DOI authors
    """
    # First check if the group belongs to the user
    group = db.query(DOIAuthorGroup).filter(
        DOIAuthorGroup.id == group_id,
        DOIAuthorGroup.userid == user.id
    ).first()

    if not group:
        raise permission_exception("You don't have permission to access this DOI author group")

    authors = db.query(DOIAuthor).filter(DOIAuthor.author_groupid == group_id).all()
    return authors
