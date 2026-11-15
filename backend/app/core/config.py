from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List
from .errores import ErrorApp


class Settings(BaseSettings):
    APP_NAME: str = "Gestor Financiero Correduría"
    APP_ENV: str = "development"

    DATABASE_URL: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    ALLOWED_ORIGINS: List[str] = ["http://localhost:5173"]

    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_MINUTES: int = 15

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_strong(cls, v: str) -> str:
        if len(v) < 32:
            raise ErrorApp("CFG-001")
        return v

    @field_validator("ALGORITHM")
    @classmethod
    def algoritmo_hmac(cls, v: str) -> str:
        # La firma usa SECRET_KEY (clave simétrica): solo tienen sentido los HMAC.
        if v not in {"HS256", "HS384", "HS512"}:
            raise ErrorApp("CFG-003", valor=v)
        return v

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def no_wildcard_origins(cls, v: List[str]) -> List[str]:
        if "*" in v:
            raise ErrorApp("CFG-002")
        return v

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()
