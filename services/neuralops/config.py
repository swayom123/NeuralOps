from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore", hide_input_in_errors=True)
    environment: Literal["development", "test", "production"] = "development"
    runtime: Literal["api", "ingest", "worker", "migration"] = Field(
        default="api", validation_alias="NEURALOPS_RUNTIME"
    )
    database_url: str = Field(repr=False)
    session_secret: str = Field(default="", repr=False)
    public_origin: str = "http://localhost:3000"
    dev_auth: bool = False
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = Field(default="", repr=False)
    max_body_bytes: int = 1_048_576
    session_hours: int = 8

    @model_validator(mode="after")
    def validate_security(self):
        if self.runtime == "api" and (
            len(self.session_secret) < 32 or self.session_secret.startswith("REPLACE_")
        ):
            raise ValueError("SESSION_SECRET must have at least 32 characters")
        origin = urlparse(self.public_origin)
        if (
            origin.username
            or origin.password
            or origin.path
            or origin.query
            or origin.fragment
            or not origin.hostname
        ):
            raise ValueError("PUBLIC_ORIGIN must be an origin without userinfo, path, query or fragment")
        if self.environment == "production" and self.runtime == "api":
            if self.dev_auth or not self.public_origin.startswith("https://"):
                raise ValueError("Production requires HTTPS and development auth disabled")
            if not all([self.oidc_issuer, self.oidc_client_id, self.oidc_client_secret]):
                raise ValueError("Production OIDC configuration is mandatory")
            if not self.oidc_issuer.startswith("https://"):
                raise ValueError("OIDC issuer must use HTTPS")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
