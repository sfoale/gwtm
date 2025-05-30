# server/schemas/doi.py

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import List, Dict, Any, Optional, Union
from datetime import datetime


class DOIAuthorBase(BaseModel):
    """Base schema for DOI author data."""
    name: str
    affiliation: str
    orcid: Optional[str] = None
    gnd: Optional[str] = None
    pos_order: Optional[int] = None


class DOIAuthorCreate(DOIAuthorBase):
    """Schema for creating a new DOI author."""
    author_groupid: int


class DOIAuthorSchema(DOIAuthorBase):
    """Schema for returning a DOI author."""
    id: int
    author_groupid: int

    model_config = ConfigDict(from_attributes=True)


class DOIAuthorGroupBase(BaseModel):
    """Base schema for DOI author group data."""
    name: str
    userid: Optional[int] = None


class DOIAuthorGroupCreate(DOIAuthorGroupBase):
    """Schema for creating a new DOI author group."""
    pass


class DOIAuthorGroupSchema(DOIAuthorGroupBase):
    """Schema for returning a DOI author group."""
    id: int

    model_config = ConfigDict(from_attributes=True)


class DOICreator(BaseModel):
    """Schema for a DOI creator."""
    name: str
    affiliation: str
    orcid: Optional[str] = None
    gnd: Optional[str] = None


class DOIPointingInfo(BaseModel):
    """Schema for DOI pointing information."""
    id: int
    graceid: str
    instrument_name: str
    status: str
    doi_url: Optional[str] = None
    doi_id: Optional[int] = None


class DOIPointingsResponse(BaseModel):
    """Schema for DOI pointings response."""
    pointings: List[DOIPointingInfo]


class DOIRequestSchema(BaseModel):
    """Schema for DOI request data."""
    graceid: Optional[str] = Field(None, description="Grace ID of the GW event")
    id: Optional[int] = Field(None, description="Single pointing ID")
    ids: Optional[List[int]] = Field(None, description="List of pointing IDs")
    doi_group_id: Optional[Union[int, str]] = Field(None, description="DOI author group ID or name")
    creators: Optional[List[DOICreator]] = Field(None, description="List of creators for the DOI")
    doi_url: Optional[str] = Field(None, description="Optional DOI URL if already exists")

    @model_validator(mode='after')
    def validate_filter_parameters(self):
        """Ensure at least one filter parameter is provided."""
        has_graceid = self.graceid is not None
        has_id = self.id is not None
        has_ids = self.ids is not None and len(self.ids) > 0

        if not (has_graceid or has_id or has_ids):
            raise ValueError("Please provide either graceid, id, or ids parameter")

        # Ensure only one of id or ids is provided, not both
        if has_id and has_ids:
            raise ValueError("Please provide either 'id' or 'ids', not both")

        return self

    @model_validator(mode='after')
    def validate_creators(self):
        """Validate creators if provided."""
        if self.creators:
            for creator in self.creators:
                if not creator.name or not creator.affiliation:
                    raise ValueError("Each creator must have both 'name' and 'affiliation'")
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 123,
                    "creators": [
                        {
                            "name": "John Doe",
                            "affiliation": "University of Science"
                        }
                    ]
                },
                {
                    "graceid": "S190425z",
                    "doi_group_id": 1
                },
                {
                    "ids": [123, 124, 125],
                    "doi_url": "https://doi.org/10.5281/zenodo.example"
                }
            ]
        }
    )

class DOIRequestResponse(BaseModel):
    """Schema for DOI request response."""
    DOI_URL: Optional[str] = None
    WARNINGS: List[Any] = []


class DOIMetadata(BaseModel):
    """Schema for DOI metadata."""
    doi: str
    creators: List[DOICreator]
    titles: List[Dict[str, str]]
    publisher: str
    publicationYear: str
    resourceType: Dict[str, str]
    descriptions: List[Dict[str, str]]
    relatedIdentifiers: Optional[List[Dict[str, str]]] = None


class DOICreate(BaseModel):
    """Schema for creating a new DOI."""
    points: List[int]
    graceid: str
    creators: List[DOICreator]
    reference: Optional[str] = None
