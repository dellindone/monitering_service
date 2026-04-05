from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.credential_manager import credential_manager
from repository.credentials_repository import credentials_repo
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/credentials", tags=["Credentials"])


class CredentialsRequest(BaseModel):
    credentials: dict


class ActiveBrokerRequest(BaseModel):
    record_id: str  # use DB id to activate a specific account


@router.get("")
async def get_all_credentials(db: AsyncSession = Depends(get_db)):
    records = await credentials_repo.get_all(db)
    return {
        "brokers": [
            {
                "id":            str(r.id),
                "broker_name":   r.broker_name,
                "is_active":     r.is_active,
                "updated_at":    str(r.updated_at),
                "account_label": r.credentials.get("account_label") if r.credentials else None,
            }
            for r in records
        ]
    }


@router.get("/active")
async def get_active_broker():
    return {"active_broker": credential_manager.get_active_broker()}


@router.post("")
async def add_credentials(body: CredentialsRequest, db: AsyncSession = Depends(get_db)):
    """Add a new broker account."""
    broker_name = body.credentials.get("broker_name", "groww")
    record = await credentials_repo.upsert(db, broker_name, body.credentials)
    return {"message": f"Account added", "id": str(record.id)}


@router.patch("/{record_id}")
async def update_credentials(
    record_id: str,
    body: CredentialsRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update credentials for a specific account by ID."""
    try:
        record = await credentials_repo.update(db, record_id, body.credentials)
        if record.is_active:
            await credential_manager.load()
        return {"message": "Credentials updated"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/active")
async def set_active_broker(body: ActiveBrokerRequest, db: AsyncSession = Depends(get_db)):
    """Activate a specific broker account by its DB id."""
    await credentials_repo.set_active_by_id(db, body.record_id)
    await credential_manager.load()
    return {"message": f"Active account switched"}


@router.delete("/{record_id}")
async def delete_credentials(record_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a broker account by ID. Cannot delete the active one."""
    from models.broker_credentials import BrokerCredential
    record = await db.get(BrokerCredential, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Account not found")
    if record.is_active:
        raise HTTPException(status_code=400, detail="Cannot delete the active account. Switch first.")
    await db.delete(record)
    await db.commit()
    logger.info(f"Credentials deleted: {record_id}")
    return {"message": "Account deleted"}
