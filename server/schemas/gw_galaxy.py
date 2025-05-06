from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Any


class GWGalaxyEntrySchema(BaseModel):
    id: int
    listid: int
    name: Optional[str]
    score: Optional[float]
    position: Optional[dict]
    rank: Optional[int]
    info: Optional[dict]

    model_config = ConfigDict(from_attributes=True)


class PostEventGalaxiesRequest(BaseModel):
    graceid: str = Field(..., description="Grace ID of the GW event")
    timesent_stamp: str = Field(..., description="Timestamp of the event in ISO format")
    groupname: Optional[str] = Field(None, description="Group name for the galaxy list")
    reference: Optional[str] = Field(None, description="Reference for the galaxy list")
    request_doi: Optional[bool] = Field(False, description="Whether to request a DOI")
    creators: Optional[List[dict]] = Field(
        None, description="List of creators with 'name' and 'affiliation'"
    )
    doi_group_id: Optional[int] = Field(None, description="ID of the DOI group")
    galaxies: List[GWGalaxyEntrySchema] = Field(..., description="List of galaxy entries")

class PostEventGalaxiesResponse(BaseModel):
    message: str = Field(..., description="Success message")
    errors: List[Any] = Field(..., description="List of errors encountered")
    warnings: List[Any] = Field(..., description="List of warnings encountered")
