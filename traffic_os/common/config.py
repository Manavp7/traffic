"""Central configuration for Traffic-OS.

A single ``Settings`` object selects between *dev* (zero external dependencies)
and *prod* (Postgres/PostGIS, TimescaleDB, Neo4j, Redis, MinIO, Redpanda) modes.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Mode = Literal["dev", "prod"]

# Repository root (…/traffic_os/common/config.py -> repo root)
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


class Settings(BaseSettings):
    """Runtime settings, overridable via environment variables (prefix ``TOS_``)."""

    model_config = SettingsConfigDict(env_prefix="TOS_", env_file=".env", extra="ignore")

    mode: Mode = "dev"

    # --- Storage locations (dev) ---
    data_dir: Path = DATA_DIR
    sqlite_path: Path = DATA_DIR / "traffic_os.db"
    blob_dir: Path = DATA_DIR / "blobs"
    kuzu_path: Path = DATA_DIR / "kuzu"

    # --- Prod connection strings (used when mode == "prod") ---
    postgres_dsn: str = "postgresql+psycopg://traffic:traffic@localhost:5432/traffic"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "traffic-os"
    redis_url: str = "redis://localhost:6379/0"
    kafka_bootstrap: str = "localhost:9092"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "traffic-os"

    # --- Simulation defaults ---
    sim_place: str = "Indiranagar, Bengaluru, India"
    sim_use_osm: bool = False  # dev default: synthetic grid (no network fetch needed)
    sim_grid_size: int = 6  # NxN synthetic grid when not using OSM
    sim_tick_seconds: int = 5  # simulated seconds per tick
    sim_seed: int = 42
    sim_demand_scale: float = 80.0  # vehicles spawned per tick at peak
    sim_directional_bias: float = 0.45  # share of trips along the main arterial corridor

    # --- Economics (configurable factors) ---
    value_of_time_inr_per_hour: float = 150.0  # INR per vehicle-hour of delay
    fuel_price_inr_per_litre: float = 100.0
    idle_fuel_litres_per_hour: float = 0.9  # litres burned per hour idling
    co2_kg_per_litre: float = 2.31  # petrol combustion factor

    # --- LLM Copilot ---
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_key: str | None = None  # optional simple API-key auth
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    api_rate_limit_per_min: int = 0  # 0 disables rate limiting
    jwt_secret: str = "traffic-os-dev-secret"

    def ensure_dirs(self) -> None:
        """Create dev data directories if missing."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.blob_dir.mkdir(parents=True, exist_ok=True)
        self.kuzu_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    return Settings()
