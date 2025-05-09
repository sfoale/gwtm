from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List, Any, Literal, Dict, Union
from datetime import datetime
from geoalchemy2.types import WKBElement
from typing_extensions import Annotated

class CandidateSchema(BaseModel):
    id: int
    graceid: str
    submitterid: int
    candidate_name: str
    datecreated: Optional[datetime] = None
    tns_name: Optional[str] = None
    tns_url: Optional[str] = None
    position: Annotated[str, WKBElement] = Field(None, description="WKT representation of the position")
    discovery_date: Optional[datetime] = None
    discovery_magnitude: Optional[float] = None
    magnitude_central_wave: Optional[float] = None
    magnitude_bandwidth: Optional[float] = None
    magnitude_unit: Optional[str] = None
    magnitude_bandpass: Optional[str] = None
    associated_galaxy: Optional[str] = None
    associated_galaxy_redshift: Optional[float] = None
    associated_galaxy_distance: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class GetCandidateQueryParams(BaseModel):
    id: Optional[int] = Field(None, description="Filter by candidate ID")
    ids: Optional[List[int]] = Field(None, description="Filter by a list of candidate IDs")
    graceid: Optional[str] = Field(None, description="Filter by Grace ID")
    userid: Optional[int] = Field(None, description="Filter by user ID")
    submitted_date_after: Optional[datetime] = Field(None, description="Filter by submission date after this timestamp")
    submitted_date_before: Optional[datetime] = Field(None, description="Filter by submission date before this timestamp")
    discovery_magnitude_gt: Optional[float] = Field(None, description="Filter by discovery magnitude greater than this value")
    discovery_magnitude_lt: Optional[float] = Field(None, description="Filter by discovery magnitude less than this value")
    discovery_date_after: Optional[datetime] = Field(None, description="Filter by discovery date after this timestamp")
    discovery_date_before: Optional[datetime] = Field(None, description="Filter by discovery date before this timestamp")
    associated_galaxy_name: Optional[str] = Field(None, description="Filter by associated galaxy name")
    associated_galaxy_redshift_gt: Optional[float] = Field(None, description="Filter by associated galaxy redshift greater than this value")
    associated_galaxy_redshift_lt: Optional[float] = Field(None, description="Filter by associated galaxy redshift less than this value")
    associated_galaxy_distance_gt: Optional[float] = Field(None, description="Filter by associated galaxy distance greater than this value")
    associated_galaxy_distance_lt: Optional[float] = Field(None, description="Filter by associated galaxy distance less than this value")


class CandidateRequest(BaseModel):
    """Single candidate submission model"""
    candidate_name: str
    position: Optional[str] = None
    ra: Optional[float] = None
    dec: Optional[float] = None
    tns_name: Optional[str] = None
    tns_url: Optional[str] = None
    discovery_date: str
    discovery_magnitude: float
    magnitude_unit: str
    magnitude_bandpass: Optional[str] = None
    magnitude_central_wave: Optional[float] = None
    magnitude_bandwidth: Optional[float] = None
    wavelength_regime: Optional[List[float]] = None
    wavelength_unit: Optional[str] = None
    frequency_regime: Optional[List[float]] = None
    frequency_unit: Optional[str] = None
    energy_regime: Optional[List[float]] = None
    energy_unit: Optional[str] = None
    associated_galaxy: Optional[str] = None
    associated_galaxy_redshift: Optional[float] = None
    associated_galaxy_distance: Optional[float] = None

    @field_validator("*", mode="before")
    @classmethod
    def validate_position_data(cls, values):
        """Validate that either position or ra/dec are provided"""
        if "position" not in values and ("ra" not in values or "dec" not in values):
            raise ValueError("Either position or both ra and dec must be provided")
        return values


class PostCandidateRequest(BaseModel):
    """Main request model with either single candidate or multiple candidates"""
    graceid: str
    candidate: Optional[CandidateRequest] = None
    candidates: Optional[List[CandidateRequest]] = None

    @field_validator("*", mode="before")
    @classmethod
    def check_candidate_or_candidates(cls, values):
        """Validate that either candidate or candidates is provided"""
        if not values.get('candidate') and not values.get('candidates'):
            raise ValueError("Either 'candidate' or 'candidates' must be provided")
        return values


class CandidateResponse(BaseModel):
    """Response model matching the Flask API format"""
    candidate_ids: List[int]
    ERRORS: List[List[Any]]
    WARNINGS: List[List[Any]]


class CandidateUpdateField(BaseModel):
    """Fields that can be updated for a candidate"""
    graceid: Optional[str] = None
    candidate_name: Optional[str] = None
    tns_name: Optional[str] = None
    tns_url: Optional[str] = None
    position: Optional[str] = None
    ra: Optional[float] = None
    dec: Optional[float] = None
    discovery_date: Optional[str] = None
    discovery_magnitude: Optional[float] = None
    magnitude_central_wave: Optional[float] = None
    magnitude_bandwidth: Optional[float] = None
    magnitude_unit: Optional[str] = None
    magnitude_bandpass: Optional[str] = None
    associated_galaxy: Optional[str] = None
    associated_galaxy_redshift: Optional[float] = None
    associated_galaxy_distance: Optional[float] = None
    wavelength_regime: Optional[List[float]] = None
    wavelength_unit: Optional[str] = None
    frequency_regime: Optional[List[float]] = None
    frequency_unit: Optional[str] = None
    energy_regime: Optional[List[float]] = None
    energy_unit: Optional[str] = None

class PutCandidateRequest(BaseModel):
    """Request model for updating a candidate"""
    id: int
    payload: CandidateUpdateField

class PutCandidateSuccessResponse(BaseModel):
    """Success response model"""
    message: Literal["success"]
    candidate: Dict[str, Any]

class PutCandidateFailureResponse(BaseModel):
    """Failure response model"""
    message: Literal["failure"]
    errors: List[Any]

# Union type for response
PutCandidateResponse = Union[PutCandidateSuccessResponse, PutCandidateFailureResponse]


class DeleteCandidateResponse(BaseModel):
    """Response model for successful delete operation"""
    message: str
    deleted_ids: Optional[List[int]] = []
    warnings: Optional[List[str]] = []


# You can add this to your candidate.py schemas file
class DeleteCandidateParams(BaseModel):
    """
    Parameters for deleting candidates.
    Either id or ids must be provided.
    """
    id: Optional[int] = None
    ids: Optional[List[int]] = None

