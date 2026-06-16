from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    groq_api_key: str
    github_token: str = ""

    projects_yaml: Path = Path(__file__).parent / "projects.yaml"
    db_path: Path = Path(__file__).parent.parent / "data" / "auraos.db"
    chroma_path: Path = Path(__file__).parent.parent / "data" / "chroma"

    planner_model: str = "llama-3.3-70b-versatile"
    classifier_model: str = "llama-3.1-8b-instant"   # fast + cheap for classification

    port_filesystem: int = 8101
    port_macos: int = 8102
    port_memory: int = 8103
    port_calendar: int = 8104
    port_github: int = 8105
    port_core: int = 8100

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()