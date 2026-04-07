import pyotp
import traceback
from growwapi import GrowwAPI
from core.logger import get_logger
from core.exceptions import BrokerAuthError

logger = get_logger(__name__)


def create_groww_client(creds: dict) -> GrowwAPI:
    """Create a GrowwAPI client directly from a credentials dict.
    Used for read-only access to inactive accounts — no singleton."""
    try:
        api_key     = creds["api_key"].strip()
        totp_secret = creds["totp_secret"].strip().upper()
        totp_secret += "=" * ((8 - len(totp_secret) % 8) % 8)
        totp         = pyotp.TOTP(totp_secret).now()
        access_token = GrowwAPI.get_access_token(api_key=api_key, totp=totp)
        return GrowwAPI(access_token)
    except Exception as e:
        logger.error(traceback.format_exc())
        raise BrokerAuthError(f"Groww login failed for inactive account: {e}")


class GrowwAuth:
    _instance: "GrowwAuth" = None
    _client: GrowwAPI = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_client(self) -> GrowwAPI:
        if self._client is None:
            self._client = self._authenticate()
        return self._client

    def refresh(self) -> GrowwAPI:
        """Re-authenticate with current credentials from CredentialManager."""
        logger.info("Refreshing Groww auth token...")
        self._client = None
        self._client = self._authenticate()
        return self._client

    def _authenticate(self) -> GrowwAPI:
        # Import here to avoid circular import at module load
        from core.credential_manager import credential_manager
        try:
            creds       = credential_manager.get("groww")
            api_key     = creds["api_key"].strip()
            totp_secret = creds["totp_secret"].strip().upper()
            # Pad to valid base32 length
            totp_secret += "=" * ((8 - len(totp_secret) % 8) % 8)

            totp         = pyotp.TOTP(totp_secret).now()
            access_token = GrowwAPI.get_access_token(api_key=api_key, totp=totp)
            client       = GrowwAPI(access_token)
            logger.info("Groww authentication successful")
            return client
        except Exception as e:
            logger.error(traceback.format_exc())
            raise BrokerAuthError(f"Groww login failed: {e}")
