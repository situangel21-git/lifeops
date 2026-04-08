import os
import json
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from google import genai

from app.tools import TaskTool, ScheduleTool, NotesTool, MapsTool, ToolLogger


class BaseAgent:
    agent_name = "BaseAgent"

    def __init__(
        self,
        db: Session,
        client: genai.Client,
        logger: ToolLogger,
        task_tool: TaskTool,
        schedule_tool: ScheduleTool,
        notes_tool: NotesTool,
        maps_tool: MapsTool,
    ):
        self.db = db
        self.client = client
        self.logger = logger
        self.task_tool = task_tool
        self.schedule_tool = schedule_tool
        self.notes_tool = notes_tool
        self.maps_tool = maps_tool

    def _clean_json(self, text: str) -> str:
        text = (text or "").strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def _safe_json_loads(self, text: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = self._clean_json(text)
        try:
            result = json.loads(cleaned)
            if isinstance(result, dict):
                return result
            return fallback
        except json.JSONDecodeError:
            return fallback

    def _model_json(self, prompt: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        print(f"RAW MODEL OUTPUT [{self.agent_name}]:", response.text)
        return self._safe_json_loads(response.text, fallback)


class TaskAgent(BaseAgent):
    agent_name = "TaskAgent"

    def run(self, user_request: str, workflow_run_id: int) -> Dict[str, Any]:
        fallback = {
            "tasks": [
                {
                    "title": user_request[:80],
                    "description": "Fallback-created task",
                    "priority": "medium",
                    "due_at": None,
                    "status": "open",
                }
            ]
        }

        prompt = f"""
You are TaskAgent in a multi-agent productivity system.

Extract actionable tasks from the user's request.

Return ONLY valid JSON with this schema:
{{
  "tasks": [
    {{
      "title": "task title",
      "description": "optional description",
      "priority": "low|medium|high",
      "due_at": "optional natural language time",
      "status": "open"
    }}
  ]
}}

Rules:
- Return JSON only
- Do not wrap in markdown
- If no tasks exist, return {{"tasks":[]}}

User request:
{user_request}
"""

        result = self._model_json(prompt, fallback)
        tasks = result.get("tasks") or []
        if not isinstance(tasks, list):
            tasks = []

        created_tasks = self.task_tool.create_tasks(
            tasks=tasks,
            workflow_run_id=workflow_run_id,
            source_agent=self.agent_name,
        )

        return {"tasks_created": created_tasks}


class ScheduleAgent(BaseAgent):
    agent_name = "ScheduleAgent"

    def run(self, user_request: str, workflow_run_id: int) -> Dict[str, Any]:
        fallback = {"events": []}

        prompt = f"""
You are ScheduleAgent in a multi-agent productivity system.

Extract schedule-worthy calendar events from the user's request.
Only create events if there is a clear appointment, meeting, call, deadline block, or time block.

Return ONLY valid JSON with this schema:
{{
  "events": [
    {{
      "title": "event title",
      "start_at": "optional natural language date/time",
      "end_at": "optional natural language date/time",
      "location": "optional location"
    }}
  ]
}}

Rules:
- Return JSON only
- Do not wrap in markdown
- If no event exists, return {{"events":[]}}

User request:
{user_request}
"""

        result = self._model_json(prompt, fallback)
        events = result.get("events") or []
        if not isinstance(events, list):
            events = []

        created_events = self.schedule_tool.create_events(
            events=events,
            workflow_run_id=workflow_run_id,
            source_agent=self.agent_name,
        )

        return {"events_created": created_events}


class KnowledgeAgent(BaseAgent):
    agent_name = "KnowledgeAgent"

    def run(self, user_request: str, workflow_run_id: int) -> Dict[str, Any]:
        recent_notes = self.notes_tool.get_recent_notes(
            workflow_run_id=workflow_run_id,
            caller_agent=self.agent_name,
            limit=5,
        )

        fallback = {
            "memory_note": {
                "title": "Workflow Note",
                "content": user_request,
                "tags": "workflow,request",
                "note_type": "memory",
            }
        }

        prompt = f"""
You are KnowledgeAgent in a multi-agent productivity system.

Using the user's request and recent notes, create one useful memory note to store.
This note should help future retrieval.

Return ONLY valid JSON with this schema:
{{
  "memory_note": {{
    "title": "short title",
    "content": "short useful note",
    "tags": "comma,separated,tags",
    "note_type": "memory"
  }}
}}

Rules:
- Return JSON only
- Do not wrap in markdown
- memory_note must be an object, not null

Recent notes:
{json.dumps(recent_notes, ensure_ascii=False)}

User request:
{user_request}
"""

        result = self._model_json(prompt, fallback)
        note_payload = result.get("memory_note") or {}
        if not isinstance(note_payload, dict):
            note_payload = {}

        saved_note = self.notes_tool.save_note(
            title=note_payload.get("title", "Workflow Note"),
            content=note_payload.get("content", user_request),
            tags=note_payload.get("tags", "workflow"),
            workflow_run_id=workflow_run_id,
            note_type=note_payload.get("note_type", "memory"),
            source_agent=self.agent_name,
        )

        return {
            "recent_notes_used": recent_notes,
            "note_saved": saved_note,
        }


class RouteAgent(BaseAgent):
    agent_name = "RouteAgent"

    def run(
        self,
        user_request: str,
        workflow_run_id: int,
        tasks_created: List[Dict[str, Any]],
        events_created: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        fallback = {"routes": []}

        prompt = f"""
You are RouteAgent in a multi-agent productivity system.

Look at the user's request plus the created tasks/events.
If there are errands, travel needs, or location-based actions, create route estimates.

Return ONLY valid JSON with this schema:
{{
  "routes": [
    {{
      "origin": "origin text",
      "destination": "destination text"
    }}
  ]
}}

Rules:
- Return JSON only
- Do not wrap in markdown
- If no route estimate is needed, return {{"routes":[]}}

User request:
{user_request}

Tasks created:
{json.dumps(tasks_created, ensure_ascii=False)}

Events created:
{json.dumps(events_created, ensure_ascii=False)}
"""

        result = self._model_json(prompt, fallback)
        routes = result.get("routes") or []
        if not isinstance(routes, list):
            routes = []

        travel_estimates = []
        for route in routes:
            if not isinstance(route, dict):
                continue
            origin = route.get("origin")
            destination = route.get("destination")
            if not origin or not destination:
                continue

            estimate = self.maps_tool.estimate_travel(
                workflow_run_id=workflow_run_id,
                caller_agent=self.agent_name,
                origin=origin,
                destination=destination,
            )
            travel_estimates.append(estimate)

        return {"travel_estimates": travel_estimates}


class CoordinatorAgent(BaseAgent):
    agent_name = "CoordinatorAgent"

    def __init__(self, db: Session):
        client = genai.Client(
            vertexai=True,
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=os.environ["GOOGLE_CLOUD_LOCATION"],
        )

        logger = ToolLogger(db)
        task_tool = TaskTool(db, logger)
        schedule_tool = ScheduleTool(db, logger)
        notes_tool = NotesTool(db, logger)
        maps_tool = MapsTool(db, logger)

        super().__init__(
            db=db,
            client=client,
            logger=logger,
            task_tool=task_tool,
            schedule_tool=schedule_tool,
            notes_tool=notes_tool,
            maps_tool=maps_tool,
        )

        self.task_agent = TaskAgent(
            db, client, logger, task_tool, schedule_tool, notes_tool, maps_tool
        )
        self.schedule_agent = ScheduleAgent(
            db, client, logger, task_tool, schedule_tool, notes_tool, maps_tool
        )
        self.knowledge_agent = KnowledgeAgent(
            db, client, logger, task_tool, schedule_tool, notes_tool, maps_tool
        )
        self.route_agent = RouteAgent(
            db, client, logger, task_tool, schedule_tool, notes_tool, maps_tool
        )

    def plan(self, user_request: str, workflow_run_id: int) -> Dict[str, Any]:
        intent_fallback = {
            "summary": "Plan created.",
            "intent": "general_planning"
        }

        prompt = f"""
You are the primary CoordinatorAgent.

Your job:
- Understand the user's request
- Produce a short summary
- Produce a short intent label

Return ONLY valid JSON with this schema:
{{
  "summary": "short summary",
  "intent": "short_intent_label"
}}

User request:
{user_request}
"""

        coordinator_result = self._model_json(prompt, intent_fallback)

        task_result = self.task_agent.run(user_request, workflow_run_id)
        schedule_result = self.schedule_agent.run(user_request, workflow_run_id)
        knowledge_result = self.knowledge_agent.run(user_request, workflow_run_id)

        tasks_created = task_result.get("tasks_created", [])
        events_created = schedule_result.get("events_created", [])

        route_result = self.route_agent.run(
            user_request=user_request,
            workflow_run_id=workflow_run_id,
            tasks_created=tasks_created,
            events_created=events_created,
        )

        agents_used = [
            self.agent_name,
            self.task_agent.agent_name,
            self.schedule_agent.agent_name,
            self.knowledge_agent.agent_name,
            self.route_agent.agent_name,
        ]

        final_result = {
            "summary": coordinator_result.get("summary", "Plan created."),
            "intent": coordinator_result.get("intent", "general_planning"),
            "agents_used": agents_used,
            "tasks_created": tasks_created,
            "events_created": events_created,
            "travel_estimates": route_result.get("travel_estimates", []),
            "note_saved": knowledge_result.get("note_saved"),
        }

        self.logger.log(
            workflow_run_id=workflow_run_id,
            agent_name=self.agent_name,
            tool_name="CoordinatorAgent.plan",
            input_payload={"user_request": user_request},
            output_payload=final_result,
        )

        return final_result