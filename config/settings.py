from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    groq_api_key: str
    github_token: str = ""

    projects_yaml: Path = Path(__file__).parent / "projects.yaml"
    db_path: Path = Path(__file__).parent.parent / "data" / "auraos.db"
    chroma_path: Path = Path(__file__).parent.parent / "data" / "chroma"

    # Groq retired the llama-3.x models. Avoid small reasoning models for the
    # classifier: their hidden reasoning can eat max_tokens and return nothing.
    planner_model: str = "openai/gpt-oss-120b"
    classifier_model: str = "qwen/qwen3.8-27b"   # fast + cheap for classification

    port_filesystem: int = 8101
    port_macos: int = 8102
    port_memory: int = 8103
    port_calendar: int = 8104
    port_github: int = 8105
    port_core: int = 8100
    port_browser: int = 8106

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()