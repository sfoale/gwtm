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
from server.utils.function import isFloat, isInt
from server.core.enums.wavelength_units import wavelength_units
from server.core.enums.frequency_units import frequency_units
from server.core.enums.energy_units import energy_units
from server.core.enums.bandpass import bandpass
from server.core.enums.depth_unit import depth_unit as depth_unit_enum
from server.core.enums.pointing_status import pointing_status
from server.db.models.users import Users
from sqlalchemy import or_

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
        # Basic filters
        graceid: Optional[str] = Query(None, description="Grace ID of the GW event"),
        graceids: Optional[str] = Query(None, description="Comma-separated list or JSON array of Grace IDs"),
        id: Optional[int] = Query(None, description="Filter by pointing ID"),
        ids: Optional[str] = Query(None, description="Comma-separated list or JSON array of pointing IDs"),

        # Status filters
        status: Optional[str] = Query(None, description="Filter by status (planned, completed, cancelled)"),
        statuses: Optional[str] = Query(None, description="Comma-separated list or JSON array of statuses"),

        # Time filters
        completed_after: Optional[str] = Query(None,
                                               description="Filter for pointings completed after this time (ISO format)"),
        completed_before: Optional[str] = Query(None,
                                                description="Filter for pointings completed before this time (ISO format)"),
        planned_after: Optional[str] = Query(None,
                                             description="Filter for pointings planned after this time (ISO format)"),
        planned_before: Optional[str] = Query(None,
                                              description="Filter for pointings planned before this time (ISO format)"),

        # User filters
        user: Optional[str] = Query(None, description="Filter by username, first name, or last name"),
        users: Optional[str] = Query(None, description="Comma-separated list or JSON array of usernames"),

        # Instrument filters
        instrument: Optional[str] = Query(None, description="Filter by instrument ID or name"),
        instruments: Optional[str] = Query(None,
                                           description="Comma-separated list or JSON array of instrument IDs or names"),

        # Band filters
        band: Optional[str] = Query(None, description="Filter by band"),
        bands: Optional[str] = Query(None, description="Comma-separated list or JSON array of bands"),

        # Spectral filters
        wavelength_regime: Optional[str] = Query(None, description="Filter by wavelength regime [min, max]"),
        wavelength_unit: Optional[str] = Query(None, description="Wavelength unit (angstrom, nanometer, micron)"),
        frequency_regime: Optional[str] = Query(None, description="Filter by frequency regime [min, max]"),
        frequency_unit: Optional[str] = Query(None, description="Frequency unit (Hz, kHz, MHz, GHz, THz)"),
        energy_regime: Optional[str] = Query(None, description="Filter by energy regime [min, max]"),
        energy_unit: Optional[str] = Query(None, description="Energy unit (eV, keV, MeV, GeV, TeV)"),

        # Depth filters
        depth_gt: Optional[float] = Query(None, description="Filter by depth greater than this value"),
        depth_lt: Optional[float] = Query(None, description="Filter by depth less than this value"),
        depth_unit: Optional[str] = Query(None, description="Depth unit (ab_mag, vega_mag, flux_erg, flux_jy)"),

        # DB access
        db: Session = Depends(get_db),
        user_auth=Depends(get_current_user)
):
    """
    Retrieve pointings from the database with optional filters.
    """


    try:
        # Build the filter conditions
        filter_conditions = []

        # Handle graceid
        if graceid:
            # Normalize the graceid
            graceid = GWAlert.graceidfromalternate(graceid)
            filter_conditions.append(PointingEvent.graceid == graceid)
            filter_conditions.append(PointingEvent.pointingid == Pointing.id)

        # Handle graceids
        if graceids:
            gids = []
            try:
                if isinstance(graceids, str):
                    if '[' in graceids and ']' in graceids:
                        # Parse as JSON array
                        gids = json.loads(graceids)
                    else:
                        # Parse as comma-separated list
                        gids = [g.strip() for g in graceids.split(',')]
                else:
                    gids = graceids  # Already a list

                normalized_gids = [GWAlert.graceidfromalternate(gid) for gid in gids]
                filter_conditions.append(PointingEvent.graceid.in_(normalized_gids))
                filter_conditions.append(PointingEvent.pointingid == Pointing.id)
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Error parsing 'graceids'. Required format is a list: '[graceid1, graceid2...]'"
                )

        # Handle ID filters
        if id:
            if isInt(id):
                filter_conditions.append(Pointing.id == int(id))
            else:
                raise HTTPException(status_code=400, detail="ID must be an integer")

        if ids:
            try:
                id_list = []
                if isinstance(ids, str):
                    if '[' in ids and ']' in ids:
                        # Parse as JSON array
                        id_list = json.loads(ids)
                    else:
                        # Parse as comma-separated list
                        id_list = [int(i.strip()) for i in ids.split(',') if isInt(i.strip())]
                else:
                    id_list = ids  # Already a list

                filter_conditions.append(Pointing.id.in_(id_list))
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Error parsing 'ids'. Required format is a list: '[id1, id2...]'"
                )

        # Handle band filters
        if band:
            for b in bandpass:
                if b.name == band:
                    filter_conditions.append(Pointing.band == b)
                    break
            else:
                raise HTTPException(status_code=400, detail=f"Invalid band: {band}")

        if bands:
            try:
                band_list = []
                if isinstance(bands, str):
                    if '[' in bands and ']' in bands:
                        # Parse as JSON array
                        band_list = json.loads(bands)
                    else:
                        # Parse as comma-separated list
                        band_list = [b.strip() for b in bands.split(',')]
                else:
                    band_list = bands  # Already a list

                valid_bands = []
                for b in bandpass:
                    if b.name in band_list:
                        valid_bands.append(b)

                if valid_bands:
                    filter_conditions.append(Pointing.band.in_(valid_bands))
                else:
                    raise HTTPException(status_code=400, detail="No valid bands specified")
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Error parsing 'bands'. Required format is a list: '[band1, band2...]'"
                )

        # Handle status filters
        if status:
            if status == "planned":
                filter_conditions.append(Pointing.status == pointing_status.planned)
            elif status == "completed":
                filter_conditions.append(Pointing.status == pointing_status.completed)
            elif status == "cancelled":
                filter_conditions.append(Pointing.status == pointing_status.cancelled)
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status: {status}. Only 'completed', 'planned', and 'cancelled' are valid."
                )

        if statuses:
            try:
                status_list = []
                if isinstance(statuses, str):
                    if '[' in statuses and ']' in statuses:
                        # Parse as JSON array
                        status_list = json.loads(statuses)
                    else:
                        # Parse as comma-separated list
                        status_list = [s.strip() for s in statuses.split(',')]
                else:
                    status_list = statuses  # Already a list

                valid_statuses = []
                if "planned" in status_list:
                    valid_statuses.append(pointing_status.planned)
                if "completed" in status_list:
                    valid_statuses.append(pointing_status.completed)
                if "cancelled" in status_list:
                    valid_statuses.append(pointing_status.cancelled)

                if valid_statuses:
                    filter_conditions.append(Pointing.status.in_(valid_statuses))
                else:
                    raise HTTPException(status_code=400, detail="No valid statuses specified")
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Error parsing 'statuses'. Required format is a list: '[status1, status2...]'"
                )

        # Handle time filters
        if completed_after:
            try:
                time = datetime.fromisoformat(completed_after.replace('Z', '+00:00'))
                filter_conditions.append(Pointing.status == pointing_status.completed)
                filter_conditions.append(Pointing.time >= time)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Error parsing date. Should be ISO format, e.g. 2019-05-01T12:00:00.00"
                )

        if completed_before:
            try:
                time = datetime.fromisoformat(completed_before.replace('Z', '+00:00'))
                filter_conditions.append(Pointing.status == pointing_status.completed)
                filter_conditions.append(Pointing.time <= time)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Error parsing date. Should be ISO format, e.g. 2019-05-01T12:00:00.00"
                )

        if planned_after:
            try:
                time = datetime.fromisoformat(planned_after.replace('Z', '+00:00'))
                filter_conditions.append(Pointing.status == pointing_status.planned)
                filter_conditions.append(Pointing.time >= time)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Error parsing date. Should be ISO format, e.g. 2019-05-01T12:00:00.00"
                )

        if planned_before:
            try:
                time = datetime.fromisoformat(planned_before.replace('Z', '+00:00'))
                filter_conditions.append(Pointing.status == pointing_status.planned)
                filter_conditions.append(Pointing.time <= time)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Error parsing date. Should be ISO format, e.g. 2019-05-01T12:00:00.00"
                )

        # Handle user filters
        if user:
            if isInt(user):
                filter_conditions.append(Pointing.submitterid == int(user))
            else:
                filter_conditions.append(or_(
                    Users.username.contains(user),
                    Users.firstname.contains(user),
                    Users.lastname.contains(user)
                ))
                filter_conditions.append(Users.id == Pointing.submitterid)

        if users:
            try:
                user_list = []
                if isinstance(users, str):
                    if '[' in users and ']' in users:
                        # Parse as JSON array
                        user_list = json.loads(users)
                    else:
                        # Parse as comma-separated list
                        user_list = [u.strip() for u in users.split(',')]
                else:
                    user_list = users  # Already a list

                or_conditions = []
                for u in user_list:
                    or_conditions.append(Users.username.contains(str(u).strip()))
                    or_conditions.append(Users.firstname.contains(str(u).strip()))
                    or_conditions.append(Users.lastname.contains(str(u).strip()))
                    if isInt(u):
                        or_conditions.append(Pointing.submitterid == int(u))

                filter_conditions.append(or_(*or_conditions))
                filter_conditions.append(Users.id == Pointing.submitterid)
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Error parsing 'users'. Required format is a list: '[user1, user2...]'"
                )

        # Handle instrument filters
        if instrument:
            if isInt(instrument):
                filter_conditions.append(Pointing.instrumentid == int(instrument))
            else:
                filter_conditions.append(Instrument.instrument_name.contains(instrument))
                filter_conditions.append(Pointing.instrumentid == Instrument.id)

        if instruments:
            try:
                inst_list = []
                if isinstance(instruments, str):
                    if '[' in instruments and ']' in instruments:
                        # Parse as JSON array
                        inst_list = json.loads(instruments)
                    else:
                        # Parse as comma-separated list
                        inst_list = [i.strip() for i in instruments.split(',')]
                else:
                    inst_list = instruments  # Already a list

                or_conditions = []
                for i in inst_list:
                    or_conditions.append(Instrument.instrument_name.contains(str(i).strip()))
                    or_conditions.append(Instrument.nickname.contains(str(i).strip()))
                    if isInt(i):
                        or_conditions.append(Pointing.instrumentid == int(i))

                filter_conditions.append(or_(*or_conditions))
                filter_conditions.append(Instrument.id == Pointing.instrumentid)
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Error parsing 'instruments'. Required format is a list: '[inst1, inst2...]'"
                )

        # Handle spectral filters
        if wavelength_regime and wavelength_unit:
            try:
                if isinstance(wavelength_regime, str):
                    if '[' in wavelength_regime and ']' in wavelength_regime:
                        # Parse range from string
                        wavelength_range = json.loads(wavelength_regime.replace('(', '[').replace(')', ']'))
                        specmin, specmax = float(wavelength_range[0]), float(wavelength_range[1])
                    else:
                        raise ValueError("Invalid wavelength_regime format")
                elif isinstance(wavelength_regime, list):
                    specmin, specmax = float(wavelength_regime[0]), float(wavelength_regime[1])
                else:
                    raise ValueError("Invalid wavelength_regime type")

                # Get unit and scale
                unit_value = wavelength_unit
                try:
                    unit = [w for w in wavelength_units if int(w) == unit_value or str(w.name) == unit_value][0]
                    scale = wavelength_units.get_scale(unit)
                    specmin = specmin * scale
                    specmax = specmax * scale

                    # Import the spectral handler
                    from server.db.models.pointing import SpectralRangeHandler
                    filter_conditions.append(Pointing.inSpectralRange(
                        specmin, specmax, SpectralRangeHandler.spectralrangetype.wavelength
                    ))
                except (IndexError, ValueError):
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid wavelength_unit. Valid units are 'angstrom', 'nanometer', and 'micron'"
                    )
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Error parsing 'wavelength_regime'. Required format is a list: '[low, high]'"
                )

        if frequency_regime and frequency_unit:
            try:
                if isinstance(frequency_regime, str):
                    if '[' in frequency_regime and ']' in frequency_regime:
                        # Parse range from string
                        frequency_range = json.loads(frequency_regime.replace('(', '[').replace(')', ']'))
                        specmin, specmax = float(frequency_range[0]), float(frequency_range[1])
                    else:
                        raise ValueError("Invalid frequency_regime format")
                elif isinstance(frequency_regime, list):
                    specmin, specmax = float(frequency_regime[0]), float(frequency_regime[1])
                else:
                    raise ValueError("Invalid frequency_regime type")

                # Get unit and scale
                unit_value = frequency_unit
                try:
                    unit = [f for f in frequency_units if int(f) == unit_value or str(f.name) == unit_value][0]
                    scale = frequency_units.get_scale(unit)
                    specmin = specmin * scale
                    specmax = specmax * scale

                    # Import the spectral handler
                    from server.db.models.pointing import SpectralRangeHandler
                    filter_conditions.append(Pointing.inSpectralRange(
                        specmin, specmax, SpectralRangeHandler.spectralrangetype.frequency
                    ))
                except (IndexError, ValueError):
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid frequency_unit. Valid units are 'Hz', 'kHz', 'MHz', 'GHz', and 'THz'"
                    )
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Error parsing 'frequency_regime'. Required format is a list: '[low, high]'"
                )

        if energy_regime and energy_unit:
            try:
                if isinstance(energy_regime, str):
                    if '[' in energy_regime and ']' in energy_regime:
                        # Parse range from string
                        energy_range = json.loads(energy_regime.replace('(', '[').replace(')', ']'))
                        specmin, specmax = float(energy_range[0]), float(energy_range[1])
                    else:
                        raise ValueError("Invalid energy_regime format")
                elif isinstance(energy_regime, list):
                    specmin, specmax = float(energy_regime[0]), float(energy_regime[1])
                else:
                    raise ValueError("Invalid energy_regime type")

                # Get unit and scale
                unit_value = energy_unit
                try:
                    unit = [e for e in energy_units if int(e) == unit_value or str(e.name) == unit_value][0]
                    scale = energy_units.get_scale(unit)
                    specmin = specmin * scale
                    specmax = specmax * scale

                    # Import the spectral handler
                    from server.db.models.pointing import SpectralRangeHandler
                    filter_conditions.append(Pointing.inSpectralRange(
                        specmin, specmax, SpectralRangeHandler.spectralrangetype.energy
                    ))
                except (IndexError, ValueError):
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid energy_unit. Valid units are 'eV', 'keV', 'MeV', 'GeV', and 'TeV'"
                    )
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Error parsing 'energy_regime'. Required format is a list: '[low, high]'"
                )

        # Handle depth filters
        if depth_gt is not None or depth_lt is not None:
            # Determine depth unit
            depth_unit_value = depth_unit or "ab_mag"  # Default to ab_mag if not specified
            try:
                depth_unit_enum_val = [d for d in depth_unit_enum if str(d.name) == depth_unit_value][0]
            except (IndexError, ValueError):
                depth_unit_enum_val = depth_unit_enum.ab_mag  # Default

            # Handle depth_gt (query for brighter things)
            if depth_gt is not None and isFloat(depth_gt):
                if 'mag' in depth_unit_enum_val.name:
                    # For magnitudes, lower values are brighter
                    filter_conditions.append(Pointing.depth <= float(depth_gt))
                elif 'flux' in depth_unit_enum_val.name:
                    # For flux, higher values are brighter
                    filter_conditions.append(Pointing.depth >= float(depth_gt))

            # Handle depth_lt (query for dimmer things)
            if depth_lt is not None and isFloat(depth_lt):
                if 'mag' in depth_unit_enum_val.name:
                    # For magnitudes, higher values are dimmer
                    filter_conditions.append(Pointing.depth >= float(depth_lt))
                elif 'flux' in depth_unit_enum_val.name:
                    # For flux, lower values are dimmer
                    filter_conditions.append(Pointing.depth <= float(depth_lt))

        # Query the database
        pointings = db.query(Pointing).filter(*filter_conditions).all()

        # Process the position field
        for pointing in pointings:
            if pointing.position:
                import shapely.wkb
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
