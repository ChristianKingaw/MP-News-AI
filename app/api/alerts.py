from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.alert import DisasterAlert, AlertStatus, AlertSeverity
from app.schemas.alert import (
    DisasterAlertCreate,
    DisasterAlertUpdate,
    DisasterAlertResponse,
    DisasterAlertList,
)

router = APIRouter(prefix="/alerts", tags=["disaster-alerts"])


@router.get("", response_model=DisasterAlertList)
async def list_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: AlertStatus | None = None,
    severity: AlertSeverity | None = None,
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    if status:
        conditions.append(DisasterAlert.status == status)
    if severity:
        conditions.append(DisasterAlert.severity == severity)

    count_q = select(func.count(DisasterAlert.id))
    if conditions:
        count_q = count_q.where(*conditions)
    total = (await db.execute(count_q)).scalar() or 0

    query = select(DisasterAlert).order_by(DisasterAlert.reported_at.desc())
    if conditions:
        query = query.where(*conditions)
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    return DisasterAlertList(
        items=[DisasterAlertResponse.model_validate(a) for a in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=DisasterAlertResponse, status_code=201)
async def create_alert(
    alert_data: DisasterAlertCreate,
    db: AsyncSession = Depends(get_db),
):
    alert = DisasterAlert(**alert_data.model_dump())
    db.add(alert)
    await db.flush()
    await db.refresh(alert)
    return DisasterAlertResponse.model_validate(alert)


@router.get("/{alert_id}", response_model=DisasterAlertResponse)
async def get_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DisasterAlert).where(DisasterAlert.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return DisasterAlertResponse.model_validate(alert)


@router.patch("/{alert_id}", response_model=DisasterAlertResponse)
async def update_alert(
    alert_id: str,
    alert_data: DisasterAlertUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DisasterAlert).where(DisasterAlert.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    update_dict = alert_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(alert, key, value)

    if alert_data.status == AlertStatus.RESOLVED:
        from datetime import datetime
        alert.resolved_at = datetime.utcnow()

    db.add(alert)
    await db.flush()
    await db.refresh(alert)
    return DisasterAlertResponse.model_validate(alert)