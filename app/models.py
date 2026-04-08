from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime, timezone

from app.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(Integer, primary_key=True, index=True)
    raw_request = Column(Text, nullable=False)
    parsed_intent = Column(String(255), nullable=True)
    status = Column(String(50), default="pending")
    final_response_json = Column(Text, nullable=True)
    agents_used = Column(String(500), nullable=True)
    started_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String(50), default="medium")
    due_at = Column(String(100), nullable=True)
    status = Column(String(50), default="open")
    workflow_run_id = Column(Integer, nullable=True)
    source_agent = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utcnow)


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    start_at = Column(String(100), nullable=True)
    end_at = Column(String(100), nullable=True)
    location = Column(String(255), nullable=True)
    workflow_run_id = Column(Integer, nullable=True)
    source_agent = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utcnow)


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    tags = Column(String(255), nullable=True)
    workflow_run_id = Column(Integer, nullable=True)
    note_type = Column(String(100), nullable=True)
    source_agent = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utcnow)


class ToolLog(Base):
    __tablename__ = "tool_logs"

    id = Column(Integer, primary_key=True, index=True)
    workflow_run_id = Column(Integer, nullable=False, index=True)
    agent_name = Column(String(100), nullable=False)
    tool_name = Column(String(100), nullable=False)
    input_json = Column(Text, nullable=True)
    output_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)