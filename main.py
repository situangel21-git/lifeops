import json
import os
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.models import WorkflowRun, Task, Event, Note, ToolLog
from app.agents import CoordinatorAgent

app = FastAPI(title="LifeOps API", version="1.0.0")


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
        "version": "1.0.0",
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
            **result
        }

    except Exception as e:
        workflow.status = "failed"
        workflow.final_response_json = json.dumps(
            {"error": str(e)},
            ensure_ascii=False
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

    tasks = db.query(Task).filter(Task.workflow_run_id == workflow_id).order_by(Task.created_at.asc()).all()
    events = db.query(Event).filter(Event.workflow_run_id == workflow_id).order_by(Event.created_at.asc()).all()
    notes = db.query(Note).filter(Note.workflow_run_id == workflow_id).order_by(Note.created_at.asc()).all()
    logs = db.query(ToolLog).filter(ToolLog.workflow_run_id == workflow_id).order_by(ToolLog.created_at.asc()).all()

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
            "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None,
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
        ]
    }


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