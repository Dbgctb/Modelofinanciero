from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List


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
            raise ValueError("SECRET_KEY debe tener al menos 32 caracteres")
        return v

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def no_wildcard_origins(cls, v: List[str]) -> List[str]:
        if "*" in v:
            raise ValueError("ALLOWED_ORIGINS no puede contener '*' — especifica dominios concretos")
        return v

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
