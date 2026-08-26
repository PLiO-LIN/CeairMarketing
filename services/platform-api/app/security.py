from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


class SecretCipher:
    def __init__(self) -> None:
        key = get_settings().encryption_key.encode()
        self._fernet = Fernet(key) if key else None

    def encrypt(self, value: str) -> str:
        if not value:
            return ""
        if self._fernet is None:
            raise RuntimeError("ENCRYPTION_KEY must be configured before storing model credentials")
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        if not value:
            return ""
        if self._fernet is None:
            raise RuntimeError("ENCRYPTION_KEY is not configured")
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise RuntimeError("Stored model credential cannot be decrypted") from exc
