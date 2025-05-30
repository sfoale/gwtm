from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime

from server.db.database import get_db
from server.db.models.icecube import IceCubeNotice, IceCubeNoticeCoincEvent
from server.schemas.icecube import (
    IceCubeNoticeSchema, 
    IceCubeNoticeCoincEventSchema,
    PostIceCubeNoticeRequest,
    PostIceCubeNoticeResponse
)
from server.auth.auth import get_current_user, verify_admin

router = APIRouter(tags=["icecube"])

@router.post("/post_icecube_notice", response_model=PostIceCubeNoticeResponse)
async def post_icecube_notice(
    request: PostIceCubeNoticeRequest,
    db: Session = Depends(get_db),
    user = Depends(verify_admin)  # Only admin can post IceCube notices
):
    """
    Post an IceCube neutrino notice (admin only).
    
    Parameters:
    - request: Complete request with notice_data and events_data
    
    Returns the created notice and events
    """
    # Check if notice already exists
    existing_notice = db.query(IceCubeNotice).filter(
        IceCubeNotice.ref_id == request.notice_data.ref_id
    ).first()
    
    if existing_notice:
        return PostIceCubeNoticeResponse(
            icecube_notice=existing_notice,
            icecube_notice_events=[]
        )
    
    # Set required fields that might not be in the input data
    notice_dict = request.notice_data.model_dump()
    notice_dict["datecreated"] = datetime.now()
    
    # Create the notice object
    notice = IceCubeNotice(**notice_dict)
    db.add(notice)
    db.flush()  # Flush to get the generated ID
    
    # Process events
    events = []
    for event_data in request.events_data:
        # Get the event data
        event_dict = event_data.model_dump()
        
        # Set the notice ID and creation date
        event_dict["icecube_notice_id"] = notice.id
        event_dict["datecreated"] = datetime.now()
        
        # Create the event object
        event = IceCubeNoticeCoincEvent(**event_dict)
        db.add(event)
        events.append(event)
    
    db.commit()
    
    # Convert to response schemas
    notice_schema = IceCubeNoticeSchema.model_validate(notice)
    event_schemas = [IceCubeNoticeCoincEventSchema.model_validate(event) for event in events]
    
    # Return the created objects
    return PostIceCubeNoticeResponse(
        icecube_notice=notice_schema,
        icecube_notice_events=event_schemas
    )
