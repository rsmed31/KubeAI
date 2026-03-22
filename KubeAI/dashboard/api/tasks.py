"""Tasks API — task submission and tracking, including multipart file upload."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel

from KubeAI.api.control_plane import ControlPlaneAPI
from KubeAI.dashboard.deps import get_control_plane

router = APIRouter()


class TaskSubmitRequest(BaseModel):
    """Request body for JSON task submission."""
    description: str
    blueprint: str | None = None

    def __repr__(self) -> str:
        return f"TaskSubmitRequest(description={self.description[:40]!r}, blueprint={self.blueprint!r})"


@router.get("/tasks")
def list_tasks(cp: ControlPlaneAPI = Depends(get_control_plane)) -> list[dict]:
    """List all tasks in the cluster with description and result_text."""
    return [
        {
            "id": t.task_id,
            "description": t.description or t.task_id,
            "status": t.status.upper(),
            "blueprint": t.blueprint,
            "agent_id": t.agent_id,
            "latency_ms": t.latency_ms,
            "eval_score": t.eval_score,
            "timestamp": t.timestamp,
            "result_text": t.result_text,
            "stages": cp._task_stages.get(t.task_id, []),  # noqa: SLF001
        }
        for t in cp.list_tasks(limit=200)
    ]


@router.post("/tasks/submit")
def submit_task(
    body: TaskSubmitRequest,
    cp: ControlPlaneAPI = Depends(get_control_plane),
) -> dict:
    """Submit a new task via JSON body."""
    return cp.submit_task(description=body.description, blueprint=body.blueprint)


@router.post("/tasks/submit-with-data")
async def submit_task_with_data(
    description: str = Form(...),
    blueprint: str = Form(None),
    file: UploadFile = File(None),
    files: list[UploadFile] = File(default=[]),
    url: str = Form(None),
    urls: list[str] = Form(default=[]),
    cp: ControlPlaneAPI = Depends(get_control_plane),
) -> dict:
    """Submit a task with an optional uploaded document and/or URL to scrape.

    The system automatically:
    1. Probes the uploaded data to determine RAG strategy
    2. Scrapes URLs if provided
    3. Chunks large documents into vector store
    4. Selects and executes with appropriate templates
    5. Streams progress via WebSocket stage events
    """
    payload_files: list[UploadFile] = []
    if file is not None:
        payload_files.append(file)
    payload_files.extend(files)

    file_payloads: list[str] = []
    file_names: list[str] = []
    for item in payload_files:
        raw = await item.read()
        decoded = raw.decode("utf-8", errors="replace")
        if decoded.strip():
            file_payloads.append(f"--- FILE: {item.filename or 'uploaded'} ---\n{decoded}")
            file_names.append(item.filename or "uploaded")
    data: str | None = "\n\n".join(file_payloads) if file_payloads else None

    all_urls: list[str] = []
    if url:
        all_urls.append(url)
    all_urls.extend(urls)
    deduped_urls = sorted({entry.strip() for entry in all_urls if entry and entry.strip()})

    result = cp.submit_task(
        description=description,
        blueprint=blueprint or None,
        data=data,
        data_url=url or None,
        data_urls=deduped_urls,
        file_names=file_names,
    )
    if file_names:
        result["file_names"] = file_names
        result["file_count"] = len(file_names)
        result["file_size"] = len(data) if data else 0
    if deduped_urls:
        result["urls"] = deduped_urls
        result["url_count"] = len(deduped_urls)
    return result
