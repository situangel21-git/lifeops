import json
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.models import Task, Event, Note, ToolLog


class ToolLogger:
    def __init__(self, db: Session):
        self.db = db

    def log(
        self,
        workflow_run_id: int,
        agent_name: str,
        tool_name: str,
        input_payload: Dict[str, Any],
        output_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        row = ToolLog(
            workflow_run_id=workflow_run_id,
            agent_name=agent_name,
            tool_name=tool_name,
            input_json=json.dumps(input_payload, ensure_ascii=False),
            output_json=json.dumps(output_payload, ensure_ascii=False),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)

        return {
            "id": row.id,
            "workflow_run_id": row.workflow_run_id,
            "agent_name": row.agent_name,
            "tool_name": row.tool_name,
        }


class TaskTool:
    def __init__(self, db: Session, logger: ToolLogger):
        self.db = db
        self.logger = logger

    def create_tasks(
        self,
        tasks: List[Dict[str, Any]],
        workflow_run_id: int,
        source_agent: str,
    ) -> List[Dict[str, Any]]:
        created = []
        for item in tasks:
            task = Task(
                title=item.get("title", "Untitled Task"),
                description=item.get("description"),
                priority=item.get("priority", "medium"),
                due_at=item.get("due_at"),
                status=item.get("status", "open"),
                workflow_run_id=workflow_run_id,
                source_agent=source_agent,
            )
            self.db.add(task)
            self.db.flush()
            created.append({
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "priority": task.priority,
                "due_at": task.due_at,
                "status": task.status,
                "source_agent": task.source_agent,
            })

        self.db.commit()

        self.logger.log(
            workflow_run_id=workflow_run_id,
            agent_name=source_agent,
            tool_name="TaskTool.create_tasks",
            input_payload={"tasks": tasks},
            output_payload={"created_tasks": created},
        )

        return created


class ScheduleTool:
    def __init__(self, db: Session, logger: ToolLogger):
        self.db = db
        self.logger = logger

    def create_events(
        self,
        events: List[Dict[str, Any]],
        workflow_run_id: int,
        source_agent: str,
    ) -> List[Dict[str, Any]]:
        created = []
        for item in events:
            event = Event(
                title=item.get("title", "Untitled Event"),
                start_at=item.get("start_at"),
                end_at=item.get("end_at"),
                location=item.get("location"),
                workflow_run_id=workflow_run_id,
                source_agent=source_agent,
            )
            self.db.add(event)
            self.db.flush()
            created.append({
                "id": event.id,
                "title": event.title,
                "start_at": event.start_at,
                "end_at": event.end_at,
                "location": event.location,
                "source_agent": event.source_agent,
            })

        self.db.commit()

        self.logger.log(
            workflow_run_id=workflow_run_id,
            agent_name=source_agent,
            tool_name="ScheduleTool.create_events",
            input_payload={"events": events},
            output_payload={"created_events": created},
        )

        return created


class NotesTool:
    def __init__(self, db: Session, logger: ToolLogger):
        self.db = db
        self.logger = logger

    def save_note(
        self,
        title: str,
        content: str,
        tags: str,
        workflow_run_id: int,
        note_type: str,
        source_agent: str,
    ) -> Dict[str, Any]:
        note = Note(
            title=title,
            content=content,
            tags=tags,
            workflow_run_id=workflow_run_id,
            note_type=note_type,
            source_agent=source_agent,
        )
        self.db.add(note)
        self.db.commit()
        self.db.refresh(note)

        output = {
            "id": note.id,
            "title": note.title,
            "content": note.content,
            "tags": note.tags,
            "note_type": note.note_type,
            "source_agent": note.source_agent,
        }

        self.logger.log(
            workflow_run_id=workflow_run_id,
            agent_name=source_agent,
            tool_name="NotesTool.save_note",
            input_payload={
                "title": title,
                "content": content,
                "tags": tags,
                "note_type": note_type,
            },
            output_payload=output,
        )

        return output

    def get_recent_notes(
        self,
        workflow_run_id: int,
        caller_agent: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        notes = self.db.query(Note).order_by(Note.created_at.desc()).limit(limit).all()
        result = [
            {
                "id": n.id,
                "title": n.title,
                "content": n.content,
                "tags": n.tags,
                "note_type": n.note_type,
                "source_agent": n.source_agent,
            }
            for n in notes
        ]

        self.logger.log(
            workflow_run_id=workflow_run_id,
            agent_name=caller_agent,
            tool_name="NotesTool.get_recent_notes",
            input_payload={"limit": limit},
            output_payload={"notes": result},
        )

        return result


class MapsTool:
    def __init__(self, db: Session, logger: ToolLogger):
        self.db = db
        self.logger = logger

    def estimate_travel(
        self,
        workflow_run_id: int,
        caller_agent: str,
        origin: str,
        destination: str,
    ) -> Dict[str, Any]:
        output = {
            "origin": origin,
            "destination": destination,
            "estimated_minutes": 30,
            "mode": "driving",
            "note": "Stubbed route estimate for MVP. Replace with real Maps/MCP integration later."
        }

        self.logger.log(
            workflow_run_id=workflow_run_id,
            agent_name=caller_agent,
            tool_name="MapsTool.estimate_travel",
            input_payload={"origin": origin, "destination": destination},
            output_payload=output,
        )

        return output