from fastapi import APIRouter, HTTPException, Depends, Query, Body
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
from dateutil.parser import parse as date_parse
import shapely.wkb
import json

from server.db.database import get_db
from server.db.models.gw_alert import GWAlert
from server.db.models.candidate import GWCandidate
from server.schemas.candidate import (
    CandidateSchema,
    GetCandidateQueryParams,
    CandidateRequest,
    PostCandidateRequest,
    CandidateResponse,
    CandidateUpdateField,
    PutCandidateRequest,
    PutCandidateResponse,
    DeleteCandidateParams,
    DeleteCandidateResponse
)
from server.auth.auth import get_current_user

router = APIRouter(tags=["candidates"])

@router.get("/candidate", response_model=List[CandidateSchema])
async def get_candidates(
    query_params: GetCandidateQueryParams = Depends(),
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get candidates with optional filters.
    """
    filter_conditions = []
    
    if query_params.id:
        filter_conditions.append(GWCandidate.id == query_params.id)
    
    if query_params.ids:
        try:
            ids_list = None
            if isinstance(query_params.ids, str):
                ids_list = query_params.ids.split('[')[1].split(']')[0].split(',')
            elif isinstance(query_params.ids, list):
                ids_list = query_params.ids
            if ids_list:
                filter_conditions.append(GWCandidate.id.in_(ids_list))
        except:
            pass
    
    if query_params.graceid:
        graceid = GWAlert.graceidfromalternate(query_params.graceid)
        filter_conditions.append(GWCandidate.graceid == graceid)
    
    if query_params.userid:
        filter_conditions.append(GWCandidate.submitterid == query_params.userid)
    
    if query_params.submitted_date_after:
        try:
            parsed_date_after = date_parse(query_params.submitted_date_after)
            filter_conditions.append(GWCandidate.datecreated >= parsed_date_after)
        except:
            pass
    
    if query_params.submitted_date_before:
        try:
            parsed_date_before = date_parse(query_params.submitted_date_before)
            filter_conditions.append(GWCandidate.datecreated <= parsed_date_before)
        except:
            pass
    
    if query_params.discovery_magnitude_gt is not None:
        filter_conditions.append(GWCandidate.discovery_magnitude >= query_params.discovery_magnitude_gt)
    
    if query_params.discovery_magnitude_lt is not None:
        filter_conditions.append(GWCandidate.discovery_magnitude <= query_params.discovery_magnitude_lt)
    
    if query_params.discovery_date_after:
        try:
            parsed_date_after = date_parse(query_params.discovery_date_after)
            filter_conditions.append(GWCandidate.discovery_date >= parsed_date_after)
        except:
            pass
    
    if query_params.discovery_date_before:
        try:
            parsed_date_before = date_parse(query_params.discovery_date_before)
            filter_conditions.append(GWCandidate.discovery_date <= parsed_date_before)
        except:
            pass
    
    if query_params.associated_galaxy_name:
        filter_conditions.append(GWCandidate.associated_galaxy.contains(query_params.associated_galaxy_name))
    
    if query_params.associated_galaxy_redshift_gt is not None:
        filter_conditions.append(GWCandidate.associated_galaxy_redshift >= query_params.associated_galaxy_redshift_gt)
    
    if query_params.associated_galaxy_redshift_lt is not None:
        filter_conditions.append(GWCandidate.associated_galaxy_redshift <= query_params.associated_galaxy_redshift_lt)
    
    if query_params.associated_galaxy_distance_gt is not None:
        filter_conditions.append(GWCandidate.associated_galaxy_distance >= query_params.associated_galaxy_distance_gt)
    
    if query_params.associated_galaxy_distance_lt is not None:
        filter_conditions.append(GWCandidate.associated_galaxy_distance <= query_params.associated_galaxy_distance_lt)
    
    candidates = db.query(GWCandidate).filter(*filter_conditions).all()

    for candidate in candidates:
        # Convert position from WKB to WKT
        if candidate.position:
            position = shapely.wkb.loads(bytes(candidate.position.data))
            candidate.position = str(position)

    return candidates


@router.post("/candidate", response_model=CandidateResponse)
async def post_gw_candidates(
        request: CandidateRequest,
        db: Session = Depends(get_db),
        user=Depends(get_current_user)
):
    """
    Post new candidate(s) for a GW event.

    This endpoint accepts either a single candidate or multiple candidates
    for a gravitational wave event.
    """
    # Try to parse the request both ways - as a Pydantic model or as raw JSON
    try:
        # First try to parse as raw JSON to maintain compatibility
        data = await request.json()

        # Try to validate using our Pydantic model
        post_request = PostCandidateRequest.parse_obj(data)
        graceid = post_request.graceid
        candidate = post_request.candidate
        candidates = post_request.candidates

    except JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Whoaaaa that JSON is a little wonky"
        )
    except ValueError as e:
        # Handle Pydantic validation errors
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    # Validate that the graceid exists
    valid_alerts = db.query(GWAlert).filter(GWAlert.graceid == graceid).all()
    if len(valid_alerts) == 0:
        raise HTTPException(
            status_code=400,
            detail="Invalid 'graceid'. Visit https://treasuremap.space/alert_select for valid alerts"
        )

    errors = []
    warnings = []
    valid_candidates = []

    # Process single candidate
    if candidate:
        gwc = GWCandidate()
        # Convert Pydantic model to dict for the from_json method
        candidate_dict = candidate.dict()
        validation_result = gwc.from_json(candidate_dict, graceid, user.id)

        if validation_result.valid:
            valid_candidates.append(gwc)
            if len(validation_result.warnings) > 0:
                warnings.append(["Object: " + json.dumps(candidate_dict), validation_result.warnings])
            db.add(gwc)
        else:
            errors.append(["Object: " + json.dumps(candidate_dict), validation_result.errors])

    # Process multiple candidates
    elif candidates:
        for candidate_item in candidates:
            gwc = GWCandidate()
            # Convert Pydantic model to dict for the from_json method
            candidate_dict = candidate_item.dict()
            validation_result = gwc.from_json(candidate_dict, graceid, user.id)

            if validation_result.valid:
                valid_candidates.append(gwc)
                if len(validation_result.warnings) > 0:
                    warnings.append(["Object: " + json.dumps(candidate_dict), validation_result.warnings])
                db.add(gwc)
            else:
                errors.append(["Object: " + json.dumps(candidate_dict), validation_result.errors])

    db.flush()
    db.commit()

    return CandidateResponse(
        candidate_ids=[x.id for x in valid_candidates],
        ERRORS=errors,
        WARNINGS=warnings
    )


@router.put("/candidate", response_model=PutCandidateRequest)
async def update_candidate(
        request: PutCandidateRequest = Body(..., description="Fields to update"),
        db: Session = Depends(get_db),
        user=Depends(get_current_user)
):
    """
    Update an existing candidate.

    Only the owner of the candidate can update it.
    Returns either a success response with the updated candidate or a failure response with errors.
    """
    # Find the candidate
    candidate = db.query(GWCandidate).filter(GWCandidate.id == request.id).first()

    if not candidate:
        raise HTTPException(
            status_code=404,
            detail=f"No candidate found with 'id': {id}"
        )

    # Check permissions
    if candidate.submitterid != user.id:
        raise HTTPException(
            status_code=403,
            detail="Error: Unauthorized. Unable to alter other user's records"
        )

    # Get the current candidate data
    position = None
    if candidate.position:
        position = shapely.wkb.loads(bytes(candidate.position.data))

    # Convert to dictionary for updating
    candidate_dict = candidate.parse  # Get the dictionary representation of the candidate

    # Convert Pydantic model to dict and update the candidate dict
    payload_dict = payload.dict(exclude_unset=True)  # Only include fields that were explicitly set

    # Update the candidate dictionary
    candidate_dict.update(
        (str(key).lower(), value) for key, value in payload_dict.items()
        if value is not None  # Only update non-None values
    )

    # Special handling for position/ra/dec fields
    if "ra" in payload_dict or "dec" in payload_dict:
        # If ra or dec are updated, remove the position field to regenerate it
        if "position" in candidate_dict:
            del candidate_dict["position"]
    elif "position" not in payload_dict and position is not None:
        # If position is not being updated, keep the original position
        candidate_dict["position"] = str(position)

    # Validate the updated data
    gwc = GWCandidate()
    validation_result = gwc.from_json(candidate_dict, candidate_dict["graceid"], candidate.submitterid)

    if validation_result.valid:
        # List of editable columns - make sure this matches what your model accepts
        editable_columns = [
            "graceid", "candidate_name", "tns_name", "tns_url", "position", "discovery_date",
            "discovery_magnitude", "magnitude_central_wave", "magnitude_bandwidth", "magnitude_unit",
            "magnitude_bandpass", "associated_galaxy", "associated_galaxy_redshift", "associated_galaxy_distance"
        ]

        # Update the candidate with validated values
        updated_model = gwc.__dict__
        for key, value in updated_model.items():
            if key in editable_columns and key in payload_dict:
                setattr(candidate, key, value)

        db.commit()
        db.refresh(candidate)

        # Convert to schema instance
        return CandidateUpdateSuccessResponse(
            message="success",
            candidate=CandidateSchema.from_orm(candidate)
        )
    else:
        # Return failure with errors
        return CandidateUpdateFailureResponse(
            message="failure",
            errors=[validation_result.errors]
        )




@router.delete("/candidate", response_model=DeleteCandidateResponse)
async def delete_candidates(
        delete_params: DeleteCandidateParams = Depends(),
        db: Session = Depends(get_db),
        user=Depends(get_current_user)
):
    """
    Delete candidate(s).

    Provide either:
    - A single candidate ID to delete
    - A list of candidate IDs to delete

    Only the owner of a candidate can delete it.
    Returns information about deleted candidates and any warnings.
    """
    warnings = []
    candidates_to_delete = []

    # Handle single ID
    if delete_params.id is not None:
        candidate = db.query(GWCandidate).filter(GWCandidate.id == delete_params.id).first()
        if not candidate:
            raise HTTPException(
                status_code=404,
                detail=f"No candidate found with 'id': {delete_params.id}"
            )

        if candidate.submitterid != user.id:
            raise HTTPException(
                status_code=403,
                detail="Error: Unauthorized. Unable to alter other user's records"
            )

        candidates_to_delete.append(candidate)

    # Handle multiple IDs
    elif delete_params.ids is not None:
        query_ids = delete_params.ids
        candidates = db.query(GWCandidate).filter(GWCandidate.id.in_(query_ids)).all()

        if len(candidates) == 0:
            raise HTTPException(
                status_code=404,
                detail="No candidates found with input 'ids'"
            )

        # Filter candidates the user is allowed to delete
        candidates_to_delete.extend([x for x in candidates if x.submitterid == user.id])
        if len(candidates_to_delete) < len(candidates):
            warnings.append("Some entries were not deleted. You cannot delete candidates you didn't submit")

    else:
        raise HTTPException(
            status_code=400,
            detail="Either 'id' or 'ids' parameter is required"
        )

    # Delete the candidates
    if len(candidates_to_delete):
        del_ids = []
        for ctd in candidates_to_delete:
            del_ids.append(ctd.id)
            db.delete(ctd)

        db.commit()

        return DeleteCandidateResponse(
            message=f"Successfully deleted {len(candidates_to_delete)} candidate(s)",
            deleted_ids=del_ids,
            warnings=warnings
        )
    else:
        return DeleteCandidateResponse(
            message="No candidates found with input parameters",
            warnings=warnings
        )
