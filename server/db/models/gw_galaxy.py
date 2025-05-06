from sqlalchemy import Column, Integer, Float, String, JSON
from ..database import Base
from geoalchemy2 import Geography

class GWGalaxyEntry(Base):
    __tablename__ = 'gw_galaxy_entry'
    __table_args__ = {'schema': 'public'}

    id = Column(Integer, primary_key=True)
    listid = Column(Integer)
    name = Column(String)
    score = Column(Float)
    position = Column(Geography('POINT', srid=4326))
    rank = Column(Integer)
    info = Column(JSON)
