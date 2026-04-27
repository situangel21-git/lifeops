import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests
from fastapi import Depends, FastAPI, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.agents import CoordinatorAgent
from app.db import Base, engine, get_db
from app.models import Event, Note, Task, ToolLog, WorkflowRun

app = FastAPI(title="LifeOps API", version="1.1.0")


class PlanRequest(BaseModel):
    request: str


def utcnow():
    return datetime.now(timezone.utc)


@app.on_event("startup")
def startup():
    """
    Optional schema creation for development.

    Default behavior:
    - local dev can set DB_AUTO_CREATE=true
    - Cloud Run can leave this false if schema already exists
    """
    auto_create = os.getenv("DB_AUTO_CREATE", "false").lower() == "true"

    if auto_create:
        Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {
        "name": "LifeOps",
        "message": "LifeOps API is running.",
        "version": "1.1.0",
    }


@app.get("/health")
def health():
    """
    Lightweight health endpoint.
    Returns DB connectivity status without mutating schema.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "ok",
        "database": db_status,
        "maps_api_configured": bool(os.getenv("GOOGLE_MAPS_API_KEY")),
    }


@app.post("/plan")
def create_plan(payload: PlanRequest, db: Session = Depends(get_db)):
    workflow = WorkflowRun(
        raw_request=payload.request,
        status="running",
        started_at=utcnow(),
    )

    db.add(workflow)
    db.commit()
    db.refresh(workflow)

    try:
        agent = CoordinatorAgent(db)
        result = agent.plan(payload.request, workflow.id)

        workflow.parsed_intent = result.get("intent")
        workflow.status = "completed"
        workflow.agents_used = ",".join(result.get("agents_used", []))
        workflow.final_response_json = json.dumps(result, ensure_ascii=False)
        workflow.completed_at = utcnow()

        db.commit()

        return {
            "workflow_id": workflow.id,
            **result,
        }

    except Exception as e:
        workflow.status = "failed"
        workflow.final_response_json = json.dumps(
            {"error": str(e)},
            ensure_ascii=False,
        )
        workflow.completed_at = utcnow()

        db.commit()

        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workflows")
def list_workflows(db: Session = Depends(get_db)):
    rows = db.query(WorkflowRun).order_by(WorkflowRun.created_at.desc()).all()

    return [
        {
            "id": row.id,
            "raw_request": row.raw_request,
            "parsed_intent": row.parsed_intent,
            "status": row.status,
            "agents_used": row.agents_used,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@app.get("/workflow/{workflow_id}")
def get_workflow(workflow_id: int, db: Session = Depends(get_db)):
    workflow = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_id).first()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    tasks = (
        db.query(Task)
        .filter(Task.workflow_run_id == workflow_id)
        .order_by(Task.created_at.asc())
        .all()
    )
    events = (
        db.query(Event)
        .filter(Event.workflow_run_id == workflow_id)
        .order_by(Event.created_at.asc())
        .all()
    )
    notes = (
        db.query(Note)
        .filter(Note.workflow_run_id == workflow_id)
        .order_by(Note.created_at.asc())
        .all()
    )
    logs = (
        db.query(ToolLog)
        .filter(ToolLog.workflow_run_id == workflow_id)
        .order_by(ToolLog.created_at.asc())
        .all()
    )

    parsed_final_response = None

    if workflow.final_response_json:
        try:
            parsed_final_response = json.loads(workflow.final_response_json)
        except json.JSONDecodeError:
            parsed_final_response = workflow.final_response_json

    return {
        "workflow": {
            "id": workflow.id,
            "raw_request": workflow.raw_request,
            "parsed_intent": workflow.parsed_intent,
            "status": workflow.status,
            "agents_used": workflow.agents_used.split(",") if workflow.agents_used else [],
            "started_at": workflow.started_at.isoformat() if workflow.started_at else None,
            "completed_at": workflow.completed_at.isoformat()
            if workflow.completed_at
            else None,
            "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
            "final_response": parsed_final_response,
        },
        "tasks": [
            {
                "id": row.id,
                "title": row.title,
                "description": row.description,
                "priority": row.priority,
                "due_at": row.due_at,
                "status": row.status,
                "source_agent": row.source_agent,
            }
            for row in tasks
        ],
        "events": [
            {
                "id": row.id,
                "title": row.title,
                "start_at": row.start_at,
                "end_at": row.end_at,
                "location": row.location,
                "source_agent": row.source_agent,
            }
            for row in events
        ],
        "notes": [
            {
                "id": row.id,
                "title": row.title,
                "content": row.content,
                "tags": row.tags,
                "note_type": row.note_type,
                "source_agent": row.source_agent,
            }
            for row in notes
        ],
        "tool_logs": [
            {
                "id": row.id,
                "agent_name": row.agent_name,
                "tool_name": row.tool_name,
                "input_json": json.loads(row.input_json) if row.input_json else None,
                "output_json": json.loads(row.output_json) if row.output_json else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in logs
        ],
    }


@app.get("/workflow/{workflow_id}/route-map/{route_index}")
def get_workflow_route_map(
    workflow_id: int,
    route_index: int,
    width: int = 640,
    height: int = 420,
    db: Session = Depends(get_db),
):
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="GOOGLE_MAPS_API_KEY is not configured.",
        )

    workflow = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_id).first()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    final_response = _parse_final_response(workflow.final_response_json)
    travel_estimates = final_response.get("travel_estimates") or []

    if route_index < 0 or route_index >= len(travel_estimates):
        raise HTTPException(status_code=404, detail="Route estimate not found")

    route = travel_estimates[route_index]

    static_map_url = _build_static_map_url(
        route=route,
        api_key=api_key,
        width=width,
        height=height,
    )

    try:
        response = requests.get(static_map_url, timeout=12)
        response.raise_for_status()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not fetch static map from Google Maps: {str(exc)}",
        )

    return Response(
        content=response.content,
        media_type=response.headers.get("content-type", "image/png"),
        headers={
            "Cache-Control": "public, max-age=3600",
        },
    )


@app.get("/tasks")
def list_tasks(db: Session = Depends(get_db)):
    rows = db.query(Task).order_by(Task.created_at.desc()).all()

    return [
        {
            "id": row.id,
            "title": row.title,
            "description": row.description,
            "priority": row.priority,
            "due_at": row.due_at,
            "status": row.status,
            "workflow_run_id": row.workflow_run_id,
            "source_agent": row.source_agent,
        }
        for row in rows
    ]


@app.get("/events")
def list_events(db: Session = Depends(get_db)):
    rows = db.query(Event).order_by(Event.created_at.desc()).all()

    return [
        {
            "id": row.id,
            "title": row.title,
            "start_at": row.start_at,
            "end_at": row.end_at,
            "location": row.location,
            "workflow_run_id": row.workflow_run_id,
            "source_agent": row.source_agent,
        }
        for row in rows
    ]


@app.get("/notes")
def list_notes(db: Session = Depends(get_db)):
    rows = db.query(Note).order_by(Note.created_at.desc()).all()

    return [
        {
            "id": row.id,
            "title": row.title,
            "content": row.content,
            "tags": row.tags,
            "note_type": row.note_type,
            "workflow_run_id": row.workflow_run_id,
            "source_agent": row.source_agent,
        }
        for row in rows
    ]


@app.get("/tool-logs")
def list_tool_logs(db: Session = Depends(get_db)):
    rows = db.query(ToolLog).order_by(ToolLog.created_at.desc()).all()

    return [
        {
            "id": row.id,
            "workflow_run_id": row.workflow_run_id,
            "agent_name": row.agent_name,
            "tool_name": row.tool_name,
            "input_json": json.loads(row.input_json) if row.input_json else None,
            "output_json": json.loads(row.output_json) if row.output_json else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def _parse_final_response(value: Optional[str]) -> Dict[str, Any]:
    if not value:
        return {}

    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _build_static_map_url(
    route: Dict[str, Any],
    api_key: str,
    width: int,
    height: int,
) -> str:
    safe_width = min(max(width, 360), 640)
    safe_height = min(max(height, 260), 640)

    encoded_polyline = route.get("encoded_polyline")

    start_marker = _marker_location(
        route.get("start_location"),
        route.get("resolved_origin") or route.get("origin"),
    )
    end_marker = _marker_location(
        route.get("end_location"),
        route.get("resolved_destination") or route.get("destination"),
    )

    params = [
        ("size", f"{safe_width}x{safe_height}"),
        ("scale", "2"),
        ("maptype", "roadmap"),
    ]

    if encoded_polyline:
        params.append(
            (
                "path",
                f"color:0x0B57D0|weight:8|enc:{encoded_polyline}",
            )
        )
    elif start_marker and end_marker:
        params.append(
            (
                "path",
                f"color:0x0B57D0|weight:8|{start_marker}|{end_marker}",
            )
        )

    if start_marker:
        params.append(("markers", f"color:green|label:A|{start_marker}"))

    if end_marker:
        params.append(("markers", f"color:red|label:B|{end_marker}"))

    params.append(("key", api_key))

    return "https://maps.googleapis.com/maps/api/staticmap?" + urlencode(params)


def _marker_location(
    latlng: Optional[Dict[str, Any]],
    fallback_text: Optional[str],
) -> Optional[str]:
    if isinstance(latlng, dict):
        lat = latlng.get("lat")
        lng = latlng.get("lng")

        if lat is not None and lng is not None:
            return f"{lat},{lng}"

    if fallback_text:
        return str(fallback_text)

    return None