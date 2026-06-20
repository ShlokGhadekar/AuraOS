"""
AuraOS · Core API
=================
FastAPI streaming endpoint that wraps the Agent.
This is what the Electron overlay calls.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from core.agent import Agent
from config.settings import settings

app = FastAPI(title="AuraOS Core API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    input: str


@app.get("/health")
def health():
    return {"status": "ok", "server": "core"}


@app.post("/api/v1/run")
def run(req: RunRequest):
    def stream():
        agent = Agent()
        try:
            for token in agent.run(req.input):
                yield token
        finally:
            agent.close()

    return StreamingResponse(stream(), media_type="text/plain")


if __name__ == "__main__":
    print(f"[core-api] starting on port {settings.port_core}")
    uvicorn.run(app, host="127.0.0.1", port=settings.port_core, log_level="warning")