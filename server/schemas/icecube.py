from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List
from datetime import datetime

class IceCubeNoticeCreateSchema(BaseModel):
    """Schema for creating IceCube notices (without id)."""
    ref_id: str
    graceid: str
    alert_datetime: datetime  # Make this required instead of optional
    observation_start: Optional[datetime] = None
    observation_stop: Optional[datetime] = None
    pval_generic: Optional[float] = None
    pval_bayesian: Optional[float] = None
    most_probable_direction_ra: Optional[float] = None
    most_probable_direction_dec: Optional[float] = None
    flux_sens_low: Optional[float] = None
    flux_sens_high: Optional[float] = None
    sens_energy_range_low: Optional[float] = None
    sens_energy_range_high: Optional[float] = None

    @field_validator('ref_id')
    @classmethod
    def validate_ref_id(cls, v):
        """Validate that ref_id is not empty."""
        if not v or not v.strip():
            raise ValueError('ref_id cannot be empty')
        return v.strip()

    @field_validator('graceid')
    @classmethod
    def validate_graceid(cls, v):
        """Validate that graceid is not empty."""
        if not v or not v.strip():
            raise ValueError('graceid cannot be empty')
        return v.strip()

    model_config = ConfigDict(from_attributes=True)


class IceCubeNoticeCoincEventCreateSchema(BaseModel):
    """Schema for creating IceCube notice coincident events (without id and icecube_notice_id)."""
    event_dt: Optional[float] = None
    ra: Optional[float] = None
    dec: Optional[float] = None
    containment_probability: Optional[float] = None
    event_pval_generic: Optional[float] = None
    event_pval_bayesian: Optional[float] = None
    ra_uncertainty: Optional[float] = None
    uncertainty_shape: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class IceCubeNoticeSchema(BaseModel):
    """Schema for returning IceCube notices (with id)."""
    id: int
    ref_id: str
    graceid: str
    alert_datetime: Optional[datetime] = None
    datecreated: Optional[datetime] = None
    observation_start: Optional[datetime] = None
    observation_stop: Optional[datetime] = None
    pval_generic: Optional[float] = None
    pval_bayesian: Optional[float] = None
    most_probable_direction_ra: Optional[float] = None
    most_probable_direction_dec: Optional[float] = None
    flux_sens_low: Optional[float] = None
    flux_sens_high: Optional[float] = None
    sens_energy_range_low: Optional[float] = None
    sens_energy_range_high: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class IceCubeNoticeCoincEventSchema(BaseModel):
    """Schema for returning IceCube notice coincident events (with id)."""
    id: int
    icecube_notice_id: int
    datecreated: Optional[datetime] = None
    event_dt: Optional[float] = None
    ra: Optional[float] = None
    dec: Optional[float] = None
    containment_probability: Optional[float] = None
    event_pval_generic: Optional[float] = None
    event_pval_bayesian: Optional[float] = None
    ra_uncertainty: Optional[float] = None
    uncertainty_shape: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PostIceCubeNoticeRequest(BaseModel):
    """Schema for the complete POST request."""
    notice_data: IceCubeNoticeCreateSchema
    events_data: List[IceCubeNoticeCoincEventCreateSchema]

    model_config = ConfigDict(from_attributes=True)


class PostIceCubeNoticeResponse(BaseModel):
    """Schema for the POST response."""
    icecube_notice: IceCubeNoticeSchema
    icecube_notice_events: List[IceCubeNoticeCoincEventSchema]

    model_config = ConfigDict(from_attributes=True)