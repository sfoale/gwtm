from sqlalchemy import Column, Integer, String, DateTime, Enum, func
from geoalchemy2 import Geography
import shapely.wkb
from sqlalchemy.ext.hybrid import hybrid_property
from ..database import Base
from server.core.enums.instrument_type import instrument_type
import datetime

class Instrument(Base):
    __tablename__ = 'instrument'
    __table_args__ = {'schema': 'public'}

    id = Column(Integer, primary_key=True)
    instrument_name = Column(String(25))
    nickname = Column(String(25))
    instrument_type = Column(Enum(instrument_type))
    datecreated = Column(DateTime)
    submitterid = Column(Integer)

class FootprintCCD(Base):
    __tablename__ = 'footprint_ccd'
    __table_args__ = {'schema': 'public'}

    id = Column(Integer, primary_key=True)
    instrumentid = Column(Integer)
    footprint = Column(Geography('POLYGON', srid=4326))
    
    @hybrid_property
    def footprint_wkt(self):
        """
        Return the footprint as a WKT string for serialization.
        """
        try:
            # Access the data binary and convert it to a Shapely geometry
            footprint_geom = shapely.wkb.loads(bytes(self.footprint.data))
            return str(footprint_geom)
        except (AttributeError, Exception):
            return None
    
    @hybrid_property
    def coordinates(self):
        """
        Extract the coordinates from the footprint as a list of (x, y) tuples.
        """
        try:
            # Access the data binary and convert it to a Shapely geometry
            footprint_geom = shapely.wkb.loads(bytes(self.footprint.data))
            # Get the exterior coordinates as a list of tuples
            coords = list(footprint_geom.exterior.coords)
            return coords
        except (AttributeError, Exception):
            return []
