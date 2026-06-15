"""
AuraOS · Settings
=================
Loaded from .env file. Never commit .env.
"""
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Anthropic
    anthropic_api_key: str

    # Project registry
    projects_yaml: Path = Path(__file__).parent / "projects.yaml"

    # Data paths
    data_dir: Path = Path(__file__).parent.parent / "data"
    db_path: Path = Path(__file__).parent.parent / "data" / "auraos.db"
    chroma_path: Path = Path(__file__).parent.parent / "data" / "chroma"

    # GitHub (optional for Phase 1)
    github_token: str = ""

    # Agent
    planner_model: str = "claude-sonnet-4-6"
    classifier_model: str = "claude-haiku-4-5-20251001"

    # MCP server ports
    port_filesystem: int = 8101
    port_macos: int = 8102
    port_memory: int = 8103
    port_calendar: int = 8104
    port_github: int = 8105

    # Core agent API
    port_core: int = 8100

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()