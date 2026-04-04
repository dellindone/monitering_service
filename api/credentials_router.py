from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.credential_manager import credential_manager
from repository.credentials_repository import credentials_repo
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/credentials", tags=["Credentials"])


class CredentialsRequest(BaseModel):
    credentials: dict  # broker-specific fields e.g. {"api_key": "...", "totp_secret": "..."}


class ActiveBrokerRequest(BaseModel):
    broker_name: str


@router.get("")
async def get_all_credentials(db: AsyncSession = Depends(get_db)):
    records = await credentials_repo.get_all(db)
    return {
        "brokers": [
            {
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


@router.patch("/{broker_name}")
async def update_credentials(
    broker_name: str,
    body: CredentialsRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update credentials for a broker. If it's the active broker, service re-authenticates live."""
    await credential_manager.update(broker_name, body.credentials)
    return {"message": f"Credentials updated for {broker_name}"}


@router.post("/active")
async def set_active_broker(body: ActiveBrokerRequest, db: AsyncSession = Depends(get_db)):
    """Switch the active broker. Service will reconnect with the new broker live."""
    await credential_manager.set_active_broker(body.broker_name)
    return {"message": f"Active broker switched to {body.broker_name}"}
