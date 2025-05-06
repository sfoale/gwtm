from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Dict

from server.db.database import get_db
from server.auth.auth import verify_admin

router = APIRouter(tags=["admin"])

@router.get("/fixdata")
@router.post("/fixdata")
async def fixdata(
    alert_name: str = None,
    duration: float = None,
    central_freq: float = None,
    db: Session = Depends(get_db),
    user = Depends(verify_admin)  # Only admin can use this endpoint
):
    """
    Fix data issues (admin only).
    
    This endpoint is for administrative data fixes.
    Currently supports updating duration and central frequency for GW alerts.
    """
    from server.db.models.gw_alert import GWAlert
    
    if not alert_name:
        return {"message": "Alert name is required"}
    
    # Find the alert
    alert = db.query(GWAlert).filter(GWAlert.graceid == alert_name).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_name} not found")
    
    # Update fields if provided
    if duration is not None:
        alert.duration = duration
    
    if central_freq is not None:
        alert.centralfreq = central_freq
    
    db.commit()
    
    return {"message": f"Alert {alert_name} updated successfully"}