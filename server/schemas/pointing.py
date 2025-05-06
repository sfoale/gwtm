from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime
from server.core.enums.pointing_status import pointing_status
from server.core.enums.depth_unit import depth_unit as depth_unit_enum
from server.core.enums.bandpass import bandpass
from geoalchemy2.types import WKBElement
from typing_extensions import Annotated

class PointingSchema(BaseModel):
    id: int
    status: Optional[pointing_status] = None
    position: Annotated[str, WKBElement] = Field(None, description="WKT representation of the position")
    galaxy_catalog: Optional[int] = None
    galaxy_catalogid: Optional[int] = None
    instrumentid: Optional[int] = None
    depth: Optional[float] = None
    depth_err: Optional[float] = None
    depth_unit: Optional[depth_unit_enum] = None
    time: Optional[datetime] = None
    datecreated: Optional[datetime] = None
    dateupdated: Optional[datetime] = None
    submitterid: Optional[int] = None
    pos_angle: Optional[float] = None
    band: Optional[bandpass] = None
    doi_url: Optional[str] = None
    doi_id: Optional[int] = None
    central_wave: Optional[float] = None
    bandwidth: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)
