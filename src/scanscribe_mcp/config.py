"""Configuration for scanscribe-mcp (D1).

Two sections, each read from its own environment variables:
- server: mcp-service-kit's BaseServerConfig (MCP_TRANSPORT, MCP_HOST, MCP_PORT, ...)
- ocr: ScanscribeMcpConfig (SCANSCRIBE_MCP_*)
"""

from __future__ import annotations

from typing import Annotated, Self

from mcp_service_kit import BaseServerConfig
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class ScanscribeMcpConfig(BaseSettings):
    """OCR options, job limits and local paths.

    Environment variables: SCANSCRIBE_MCP_LANGS, SCANSCRIBE_MCP_MAX_PAGES, ... The names and
    defaults are listed in the README.
    """

    model_config = SettingsConfigDict(env_prefix="SCANSCRIBE_MCP_", extra="ignore")

    langs: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["en"],
        description="OCR languages a job may ask for, comma-separated",
    )
    default_lang: str | None = Field(
        default=None, description="Language of a job that names none (default: the first of LANGS)"
    )
    default_dpi: int = Field(default=200, description="dpi of a job that names none")
    default_columns: int = Field(default=1, description="columns of a job that names none")
    device: str | None = Field(
        default=None, description="Engine device, e.g. gpu:0 or cpu (default: GPU, else CPU)"
    )
    min_dpi: int = Field(default=72, ge=1, description="Lowest dpi a job may ask for")
    max_dpi: int = Field(default=400, ge=1, description="Highest dpi a job may ask for")
    max_columns: int = Field(default=8, ge=1, description="Most columns a job may ask for")
    max_pages: int = Field(default=500, ge=1, description="Most pages one job may have")
    max_page_pixels: int = Field(
        default=100_000_000, ge=1, description="Largest PDF page, in pixels at the job's dpi"
    )
    page_timeout_s: float = Field(
        default=600.0, gt=0, description="Longest one page may take before its job fails"
    )
    max_queued: int = Field(default=20, ge=1, description="Most jobs queued at once")
    queue_timeout_s: float = Field(
        default=3600.0, gt=0, description="A queued job that hasn't started by then expires"
    )
    job_retention_s: float = Field(
        default=86400.0, gt=0, description="How long a finished job stays listed"
    )
    max_inline_chars: int = Field(
        default=50_000, ge=1, description="Longest text get_ocr_result returns inline"
    )
    allow_local_paths: bool = Field(
        default=True,
        description="Accept input_path and output_path over stdio; never allowed over HTTP",
    )

    @field_validator("langs", mode="before")
    @classmethod
    def _split_langs(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not self.langs:
            raise ValueError("SCANSCRIBE_MCP_LANGS must name at least one language")
        if self.default_lang is None:
            self.default_lang = self.langs[0]
        elif self.default_lang not in self.langs:
            raise ValueError(
                f"SCANSCRIBE_MCP_DEFAULT_LANG {self.default_lang!r} is not in "
                f"SCANSCRIBE_MCP_LANGS ({', '.join(self.langs)})"
            )
        if self.min_dpi > self.max_dpi:
            raise ValueError("SCANSCRIBE_MCP_MIN_DPI must not exceed SCANSCRIBE_MCP_MAX_DPI")
        if not self.min_dpi <= self.default_dpi <= self.max_dpi:
            raise ValueError("SCANSCRIBE_MCP_DEFAULT_DPI must be within MIN_DPI and MAX_DPI")
        if not 1 <= self.default_columns <= self.max_columns:
            raise ValueError("SCANSCRIBE_MCP_DEFAULT_COLUMNS must be within 1 and MAX_COLUMNS")
        return self

    @property
    def lang(self) -> str:
        """The default language, after validation filled it in."""
        assert self.default_lang is not None
        return self.default_lang


class AppConfig(BaseModel):
    """The complete configuration: the server section goes to the server, all of it to the
    service."""

    server: BaseServerConfig = Field(default_factory=BaseServerConfig)
    ocr: ScanscribeMcpConfig = Field(default_factory=ScanscribeMcpConfig)

    @property
    def local_paths_allowed(self) -> bool:
        """input_path and output_path: over stdio unless ALLOW_LOCAL_PATHS=false; never over
        HTTP, whatever the variable says (R2)."""
        return self.server.transport == "stdio" and self.ocr.allow_local_paths
