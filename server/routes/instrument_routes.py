from fastapi import APIRouter, HTTPException, Depends, Query, Body
from sqlalchemy.orm import Session
from typing import List, Optional
import json
import datetime
from sqlalchemy import or_

from server.core.enums.instrument_type import instrument_type
from server.db.database import get_db
from server.db.models.instrument import Instrument, FootprintCCD
from server.db.models.pointing import Pointing
from server.schemas.instrument import (
    InstrumentSchema, 
    FootprintCCDSchema, 
    InstrumentWithFootprints,
    InstrumentCreate,
    InstrumentUpdate,
    FootprintCCDCreate
)
from server.auth.auth import get_current_user

router = APIRouter(tags=["instruments"])

@router.get("/instruments", response_model=List[InstrumentSchema])
async def get_instruments(
    id: Optional[int] = None,
    ids: Optional[str] = None,
    name: Optional[str] = None,
    names: Optional[str] = None,
    type: Optional[instrument_type] = None,
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get instruments with optional filters.
    
    Parameters:
    - id: Filter by instrument ID
    - ids: Filter by list of instrument IDs
    - name: Filter by instrument name (fuzzy match)
    - names: Filter by list of instrument names (fuzzy match)
    - type: Filter by instrument type
    
    Returns a list of instrument objects
    """
    filter_conditions = []
    
    if id:
        filter_conditions.append(Instrument.id == id)
    
    if ids:
        try:
            if isinstance(ids, str):
                ids_list = json.loads(ids)
            else:
                ids_list = ids
            filter_conditions.append(Instrument.id.in_(ids_list))
        except:
            raise HTTPException(status_code=400, detail="Invalid ids format. Must be a JSON array.")
    
    if name:
        filter_conditions.append(Instrument.instrument_name.contains(name))
    
    if names:
        try:
            if isinstance(names, str):
                insts = json.loads(names)
            else:
                insts = names
            
            or_conditions = []
            for i in insts:
                or_conditions.append(Instrument.instrument_name.contains(i.strip()))
            
            filter_conditions.append(or_(*or_conditions))
            filter_conditions.append(Instrument.id == Pointing.instrumentid)
        except:
            raise HTTPException(status_code=400, detail="Invalid names format. Must be a JSON array.")
    
    if type:
        filter_conditions.append(Instrument.instrument_type == type)
    
    instruments = db.query(Instrument).filter(*filter_conditions).all()
    
    # FastAPI will automatically convert SQLAlchemy models to Pydantic models
    return instruments

@router.get("/footprints", response_model=List[FootprintCCDSchema])
async def get_footprints(
    id: Optional[int] = None,
    name: Optional[str] = None,
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get instrument footprints with optional filters.
    
    Parameters:
    - id: Filter by instrument ID
    - name: Filter by instrument name (fuzzy match)
    
    Returns a list of footprint objects
    """
    filter_conditions = []
    
    if id:
        filter_conditions.append(FootprintCCD.instrumentid == id)
    
    if name:
        filter_conditions.append(FootprintCCD.instrumentid == Instrument.id)
        
        or_conditions = []
        or_conditions.append(Instrument.instrument_name.contains(name.strip()))
        or_conditions.append(Instrument.nickname.contains(name.strip()))
        
        filter_conditions.append(or_(*or_conditions))
    
    footprints = db.query(FootprintCCD).filter(*filter_conditions).all()
    
    # FastAPI will automatically convert SQLAlchemy models to Pydantic models
    return footprints

@router.get("/instrument_details/{instrument_id}", response_model=InstrumentWithFootprints)
async def get_instrument_details(
    instrument_id: int,
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Get detailed information about a specific instrument, including its footprints.
    
    Parameters:
    - instrument_id: The ID of the instrument
    
    Returns an instrument object with its associated footprints
    """
    # Get the instrument
    instrument = db.query(Instrument).filter(Instrument.id == instrument_id).first()
    if not instrument:
        raise HTTPException(status_code=404, detail=f"Instrument with ID {instrument_id} not found")
    
    # Get the instrument's footprints
    footprints = db.query(FootprintCCD).filter(FootprintCCD.instrumentid == instrument_id).all()
    
    # Create the response with the nested object
    instrument_with_footprints = InstrumentWithFootprints(
        id=instrument.id,
        instrument_name=instrument.instrument_name,
        nickname=instrument.nickname,
        instrument_type=instrument.instrument_type,
        datecreated=instrument.datecreated,
        submitterid=instrument.submitterid,
        footprints=footprints  # FastAPI will convert the SQLAlchemy models to Pydantic models
    )
    
    return instrument_with_footprints

@router.post("/instruments", response_model=InstrumentSchema)
async def create_instrument(
    instrument: InstrumentCreate,
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Create a new instrument.
    
    Parameters:
    - instrument: Instrument data
    
    Returns the created instrument
    """
    # Create a new instrument
    new_instrument = Instrument(
        instrument_name=instrument.instrument_name,
        nickname=instrument.nickname,
        instrument_type=instrument.instrument_type,
        submitterid=user.id,
        datecreated=datetime.datetime.now()
    )
    
    db.add(new_instrument)
    db.commit()
    db.refresh(new_instrument)
    
    return new_instrument

@router.post("/footprints", response_model=FootprintCCDSchema)
async def create_footprint(
    footprint: FootprintCCDCreate,
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Create a new footprint for an instrument.
    
    Parameters:
    - footprint: Footprint data
    
    Returns the created footprint
    """
    # Check if the instrument exists
    instrument = db.query(Instrument).filter(Instrument.id == footprint.instrumentid).first()
    if not instrument:
        raise HTTPException(status_code=404, detail=f"Instrument with ID {footprint.instrumentid} not found")
    
    # Check permissions (only the instrument submitter can add footprints)
    if instrument.submitterid != user.id:
        raise HTTPException(
            status_code=403, 
            detail="You don't have permission to add footprints to this instrument"
        )
    
    # Create a new footprint
    new_footprint = FootprintCCD(
        instrumentid=footprint.instrumentid,
        footprint=footprint.footprint  # WKT format
    )
    
    db.add(new_footprint)
    db.commit()
    db.refresh(new_footprint)
    
    return new_footprint
