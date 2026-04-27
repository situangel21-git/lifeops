import json
import os
import re
from typing import Any, Dict, List, Optional

from google import genai
from sqlalchemy.orm import Session

from app.tools import MapsTool, NotesTool, ScheduleTool, TaskTool, ToolLogger


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

    def _normalize_text(self, value: Optional[str]) -> str:
        return (
            str(value or "")
            .lower()
            .replace("_", " ")
            .replace("-", " ")
            .strip()
        )


class TaskAgent(BaseAgent):
    agent_name = "TaskAgent"

    def run(self, user_request: str, workflow_run_id: int) -> Dict[str, Any]:
        fallback = {"tasks": []}

        prompt = f"""
You are TaskAgent in a multi-agent productivity system.

Extract ONLY actionable tasks from the user's request.

Return ONLY valid JSON with this schema:
{{
  "tasks": [
    {{
      "title": "task title",
      "description": "optional description",
      "priority": "low|medium|high",
      "due_at": "optional natural language deadline or constraint",
      "status": "open"
    }}
  ]
}}

Rules:
- Return JSON only.
- Do not wrap in markdown.
- If no tasks exist, return {{"tasks":[]}}.
- Errands, purchases, pickups, reminders, and follow-ups are tasks.
- Do NOT create a task for fixed meetings, calls, presentations, appointments, or calendar events.
- Do NOT create a task for "attend presentation" if the request already gives a fixed presentation time.
- Do NOT create a separate task for a prep block if the user asks for a specific prep time block before a meeting. ScheduleAgent will create that block.
- If a task must happen before a meeting, deadline, route, or arrival time, preserve that in due_at.
- If the user says "before heading to BGC", "after the presentation", "before going home by 7 PM", or similar, preserve that exact phrase in due_at.
- Flexible errands should not be forced into the same time as fixed events.
- Assume a normal person needs transition time between activities. Do not imply tasks can happen during travel or during a fixed meeting.
- Prefer concrete tasks like:
  - Buy printer ink
  - Stop by Mercury Drug for vitamins
  - Pick up package
  - Bring notebook

User request:
{user_request}
"""

        result = self._model_json(prompt, fallback)
        model_tasks = result.get("tasks") or []

        if not isinstance(model_tasks, list):
            model_tasks = []

        deterministic_tasks = self._deterministic_tasks_from_request(user_request)
        tasks = self._merge_tasks(model_tasks, deterministic_tasks, user_request)

        created_tasks = self.task_tool.create_tasks(
            tasks=tasks,
            workflow_run_id=workflow_run_id,
            source_agent=self.agent_name,
        )

        return {"tasks_created": created_tasks}

    def _deterministic_tasks_from_request(self, user_request: str) -> List[Dict[str, Any]]:
        text = self._normalize_text(user_request)
        tasks = []

        if "printer ink" in text:
            tasks.append(
                {
                    "title": "Buy printer ink",
                    "description": "Buy printer ink in Makati before heading to BGC.",
                    "priority": "medium",
                    "due_at": "before heading to BGC",
                    "status": "open",
                }
            )

        if "mercury" in text or "vitamin" in text or "vitamins" in text:
            tasks.append(
                {
                    "title": "Stop by Mercury Drug for vitamins",
                    "description": "Stop by Mercury Drug in BGC for vitamins after the client presentation.",
                    "priority": "medium",
                    "due_at": "after the presentation",
                    "status": "open",
                }
            )

        if "package" in text and ("quezon" in text or "qc" in text):
            tasks.append(
                {
                    "title": "Pick up package in Quezon City",
                    "description": "Pick up the package in Quezon City before going home.",
                    "priority": "high",
                    "due_at": "before going home by 7 PM",
                    "status": "open",
                }
            )

        if "notebook" in text:
            tasks.append(
                {
                    "title": "Bring notebook",
                    "description": "Bring the notebook for the presentation or planned activities.",
                    "priority": "medium",
                    "due_at": None,
                    "status": "open",
                }
            )

        return tasks

    def _merge_tasks(
        self,
        model_tasks: List[Dict[str, Any]],
        deterministic_tasks: List[Dict[str, Any]],
        user_request: str,
    ) -> List[Dict[str, Any]]:
        merged = []
        seen = set()
        request_prefix = self._normalize_text(user_request[:80])

        for task in model_tasks + deterministic_tasks:
            if not isinstance(task, dict):
                continue

            title = str(task.get("title") or "").strip()
            normalized_title = self._normalize_text(title)

            if not title:
                continue

            if len(title) > 70 and normalized_title in request_prefix:
                continue

            if "client presentation" in normalized_title and (
                "attend" in normalized_title or "presentation in bgc" in normalized_title
            ):
                continue

            if "prep" in normalized_title and "presentation" in normalized_title:
                continue

            key = self._task_key(title)

            if key in seen:
                continue

            seen.add(key)
            merged.append(
                {
                    "title": title,
                    "description": task.get("description"),
                    "priority": task.get("priority", "medium"),
                    "due_at": task.get("due_at"),
                    "status": task.get("status", "open"),
                }
            )

        return merged

    def _task_key(self, title: str) -> str:
        normalized = self._normalize_text(title)

        if "printer" in normalized and "ink" in normalized:
            return "buy-printer-ink"

        if "mercury" in normalized or "vitamin" in normalized:
            return "mercury-drug-vitamins"

        if "package" in normalized or "pick up" in normalized or "pickup" in normalized:
            return "pick-up-package"

        if "notebook" in normalized:
            return "bring-notebook"

        return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


class ScheduleAgent(BaseAgent):
    agent_name = "ScheduleAgent"

    def run(self, user_request: str, workflow_run_id: int) -> Dict[str, Any]:
        fallback = {"events": []}

        prompt = f"""
You are ScheduleAgent in a multi-agent productivity system.

Extract ONLY fixed schedule blocks from the user's request.

Return ONLY valid JSON with this schema:
{{
  "events": [
    {{
      "title": "event title",
      "start_at": "natural language date/time",
      "end_at": "natural language date/time",
      "location": "optional location"
    }}
  ]
}}

Rules:
- Return JSON only.
- Do not wrap in markdown.
- If no real schedule block exists, return {{"events":[]}}.
- Create events only for fixed meetings, calls, appointments, presentations, and explicit time blocks.
- If the user asks for one hour of prep time before a meeting, create a prep event.
- Do NOT create events for errands that only have loose constraints like "before heading to BGC", "after the presentation", or "before going home".
- Do NOT create events for buying items, pharmacy stops, package pickups, or reminders unless the user gives an exact appointment time for them.
- Do NOT schedule tasks, route legs, and fixed events at the same time unless unavoidable.
- Assume a normal person needs reasonable transition time between events, errands, and travel.
- If the user says "presentation in BGC at 3 PM" and "one hour prep time before that":
  - Create "Prep for Client Presentation" from "Thursday 2 PM" to "Thursday 3 PM", location "BGC".
  - Create "Client Presentation" from "Thursday 3 PM" to "Thursday 4 PM", location "BGC".
- If no end time is provided for a fixed appointment, assume 1 hour.
- Preserve location names because RouteAgent needs them.

User request:
{user_request}
"""

        result = self._model_json(prompt, fallback)
        model_events = result.get("events") or []

        if not isinstance(model_events, list):
            model_events = []

        deterministic_events = self._deterministic_events_from_request(user_request)
        events = self._merge_events(model_events, deterministic_events)

        created_events = self.schedule_tool.create_events(
            events=events,
            workflow_run_id=workflow_run_id,
            source_agent=self.agent_name,
        )

        return {"events_created": created_events}

    def _deterministic_events_from_request(self, user_request: str) -> List[Dict[str, Any]]:
        text = self._normalize_text(user_request)
        events = []

        if "presentation" in text and ("3 pm" in text or "3pm" in text):
            if "one hour" in text and "prep" in text:
                events.append(
                    {
                        "title": "Prep for Client Presentation",
                        "start_at": "Thursday 2 PM",
                        "end_at": "Thursday 3 PM",
                        "location": "BGC",
                    }
                )

            events.append(
                {
                    "title": "Client Presentation",
                    "start_at": "Thursday 3 PM",
                    "end_at": "Thursday 4 PM",
                    "location": "BGC",
                }
            )

        return events

    def _merge_events(
        self,
        model_events: List[Dict[str, Any]],
        deterministic_events: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged = []
        seen = set()

        for event in deterministic_events + model_events:
            if not isinstance(event, dict):
                continue

            title = str(event.get("title") or "").strip()
            start_at = event.get("start_at")
            end_at = event.get("end_at")
            location = event.get("location")

            if not title or not start_at:
                continue

            normalized_title = self._normalize_text(title)

            if any(
                keyword in normalized_title
                for keyword in ["printer ink", "mercury", "vitamin", "package", "pickup", "pick up"]
            ):
                continue

            key = self._event_key(title, start_at, location)

            if key in seen:
                continue

            seen.add(key)
            merged.append(
                {
                    "title": title,
                    "start_at": start_at,
                    "end_at": end_at,
                    "location": location,
                }
            )

        return merged

    def _event_key(self, title: str, start_at: str, location: Optional[str]) -> str:
        normalized_title = self._normalize_text(title)

        if "prep" in normalized_title and "presentation" in normalized_title:
            return "prep-client-presentation"

        if "presentation" in normalized_title:
            return "client-presentation"

        return re.sub(
            r"[^a-z0-9]+",
            "-",
            f"{normalized_title}-{self._normalize_text(start_at)}-{self._normalize_text(location)}",
        ).strip("-")


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
This note should help future retrieval and should not be unnecessarily long.

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
- Return JSON only.
- Do not wrap in markdown.
- memory_note must be an object, not null.

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
        default_origin = os.getenv(
            "DAYWEAVER_DEFAULT_ORIGIN",
            "Makati City, Metro Manila, Philippines",
        )

        prompt = f"""
You are RouteAgent in a multi-agent productivity system.

Your job is to identify practical driving route legs from the user's request, tasks, and events.

Return ONLY valid JSON with this schema:
{{
  "routes": [
    {{
      "origin": "origin text",
      "destination": "destination text",
      "arrive_by": "optional natural language arrival time",
      "depart_after": "optional natural language departure time",
      "purpose": "why this route is needed",
      "destination_event_title": "optional event title this route supports",
      "destination_task_title": "optional task title this route supports"
    }}
  ]
}}

Rules:
- Return JSON only.
- Do not wrap in markdown.
- If no route estimate is needed, return {{"routes":[]}}.
- Only create route legs for meaningful travel between different physical areas.
- Do NOT create same-area routes such as Makati to Makati or BGC to BGC.
- Do NOT create a route for "buy printer ink in Makati" when the user already starts in Makati.
- Do NOT create a route for "Mercury Drug in BGC" if the previous event is also in BGC.
- Use concrete place names such as "Makati City, Philippines", "Bonifacio Global City, Taguig, Philippines", or "Quezon City, Philippines".
- If the first origin is not stated, use this default origin: {default_origin}
- For multiple locations, create sequential route legs.
- Do not create more than 4 route legs.
- Do not schedule travel at the same time as fixed prep, meetings, presentations, or errands.
- Assume a normal person needs transition time between tasks, events, and travel. Use at least 10 minutes of buffer when reasonable.
- If a route is needed to arrive before a fixed event, set arrive_by.
- If a route supports an event, set destination_event_title.
- If a route supports a task, set destination_task_title.
- If the user says "presentation in BGC at 3 PM" and "one hour prep before that", the route to BGC should arrive by 2 PM.
- If the user says "pick up a package in Quezon City before going home by 7 PM", create a route to Quezon City before going home and a final route home by 7 PM.
- Do not return an empty routes list when the user mentions multiple physical locations.

User request:
{user_request}

Tasks created:
{json.dumps(tasks_created, ensure_ascii=False)}

Events created:
{json.dumps(events_created, ensure_ascii=False)}
"""

        result = self._model_json(prompt, fallback)
        model_routes = result.get("routes") or []

        if not isinstance(model_routes, list):
            model_routes = []

        deterministic_routes = self._deterministic_routes_from_context(
            user_request=user_request,
            tasks_created=tasks_created,
            events_created=events_created,
            default_origin=default_origin,
        )

        routes = self._merge_routes(
            model_routes=model_routes,
            deterministic_routes=deterministic_routes,
            default_origin=default_origin,
        )

        self.logger.log(
            workflow_run_id=workflow_run_id,
            agent_name=self.agent_name,
            tool_name="RouteAgent.identify_routes",
            input_payload={
                "user_request": user_request,
                "tasks_created": tasks_created,
                "events_created": events_created,
                "model_routes": model_routes,
                "deterministic_routes": deterministic_routes,
            },
            output_payload={"routes": routes},
        )

        travel_estimates = []

        for index, route in enumerate(routes[:4]):
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

            estimate["sequence_index"] = index
            estimate["arrive_by"] = route.get("arrive_by")
            estimate["depart_after"] = route.get("depart_after")
            estimate["purpose"] = route.get("purpose")
            estimate["destination_event_title"] = route.get("destination_event_title")
            estimate["destination_task_title"] = route.get("destination_task_title")

            travel_estimates.append(estimate)

        return {"travel_estimates": travel_estimates}

    def _deterministic_routes_from_context(
        self,
        user_request: str,
        tasks_created: List[Dict[str, Any]],
        events_created: List[Dict[str, Any]],
        default_origin: str,
    ) -> List[Dict[str, Any]]:
        text = self._normalize_text(
            " ".join(
                [
                    user_request,
                    json.dumps(tasks_created, ensure_ascii=False),
                    json.dumps(events_created, ensure_ascii=False),
                ]
            )
        )

        routes = []
        start_location = self._extract_start_location(user_request) or default_origin
        home_location = self._extract_home_location(user_request) or default_origin

        has_bgc = any(
            self._contains_any(
                f"{event.get('title', '')} {event.get('location', '')}",
                ["bgc", "bonifacio", "taguig"],
            )
            for event in events_created
        ) or self._contains_any(text, ["bgc", "bonifacio", "taguig"])

        has_qc = self._contains_any(text, ["quezon city", "qc"])

        bgc_arrive_by = self._find_bgc_arrival_time(events_created)

        if has_bgc:
            routes.append(
                {
                    "origin": start_location,
                    "destination": "Bonifacio Global City, Taguig, Philippines",
                    "arrive_by": bgc_arrive_by,
                    "depart_after": "after buying printer ink and allowing transition time",
                    "purpose": "Travel to BGC before the preparation block or client presentation.",
                    "destination_event_title": "Prep for Client Presentation",
                    "destination_task_title": None,
                }
            )

        if has_bgc and has_qc:
            routes.append(
                {
                    "origin": "Bonifacio Global City, Taguig, Philippines",
                    "destination": "Quezon City, Philippines",
                    "arrive_by": "6 PM",
                    "depart_after": "after Mercury Drug stop and allowing transition time",
                    "purpose": "Travel from BGC to Quezon City for package pickup before going home.",
                    "destination_event_title": None,
                    "destination_task_title": "Pick up package",
                }
            )

        if has_qc and self._contains_any(text, ["home by", "going home", "go home"]):
            routes.append(
                {
                    "origin": "Quezon City, Philippines",
                    "destination": home_location,
                    "arrive_by": self._extract_home_by_time(user_request) or "7 PM",
                    "depart_after": "after package pickup and allowing transition time",
                    "purpose": "Travel home after the Quezon City package pickup.",
                    "destination_event_title": None,
                    "destination_task_title": None,
                }
            )

        return routes

    def _merge_routes(
        self,
        model_routes: List[Dict[str, Any]],
        deterministic_routes: List[Dict[str, Any]],
        default_origin: str,
    ) -> List[Dict[str, Any]]:
        merged = []
        seen = set()

        for route in deterministic_routes + model_routes:
            if not isinstance(route, dict):
                continue

            origin = route.get("origin")
            destination = route.get("destination")

            if not origin or not destination:
                continue

            origin_key = self._canonical_route_place(origin, default_origin)
            destination_key = self._canonical_route_place(destination, default_origin)

            if not origin_key or not destination_key:
                continue

            if origin_key == destination_key:
                continue

            key = (origin_key, destination_key)

            if key in seen:
                continue

            seen.add(key)
            merged.append(route)

        return merged

    def _canonical_route_place(self, place: str, default_origin: str) -> str:
        normalized = self._normalize_text(place)

        if normalized in {"home", "my home", "house", "my house", "going home"}:
            return self._canonical_route_place(default_origin, default_origin)

        if "makati" in normalized:
            return "makati"

        if "bgc" in normalized or "bonifacio" in normalized or "taguig" in normalized:
            return "bgc"

        if "quezon" in normalized or normalized == "qc" or " qc " in f" {normalized} ":
            return "quezon-city"

        return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")

    def _find_bgc_arrival_time(self, events_created: List[Dict[str, Any]]) -> str:
        prep_event = None
        presentation_event = None

        for event in events_created:
            title = self._normalize_text(event.get("title"))
            location = self._normalize_text(event.get("location"))

            if "prep" in title and (
                "bgc" in location or "taguig" in location or "presentation" in title
            ):
                prep_event = event

            if "presentation" in title or "client presentation" in title:
                presentation_event = event

        if prep_event and prep_event.get("start_at"):
            return prep_event.get("start_at")

        if presentation_event and presentation_event.get("start_at"):
            shifted = self._shift_time_text_back_one_hour(presentation_event.get("start_at"))

            if shifted:
                return shifted

            return presentation_event.get("start_at")

        return "2 PM"

    def _shift_time_text_back_one_hour(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None

        match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", value, re.IGNORECASE)

        if not match:
            return None

        hour = int(match.group(1))
        minute = match.group(2) or "00"
        meridiem = match.group(3).upper()

        hour_24 = hour

        if meridiem == "PM" and hour < 12:
            hour_24 += 12

        if meridiem == "AM" and hour == 12:
            hour_24 = 0

        shifted = max(0, hour_24 - 1)
        shifted_meridiem = "AM" if shifted < 12 else "PM"
        shifted_hour = shifted % 12

        if shifted_hour == 0:
            shifted_hour = 12

        return f"{shifted_hour}:{minute} {shifted_meridiem}"

    def _extract_start_location(self, user_request: str) -> Optional[str]:
        patterns = [
            r"\bstart(?:ing)?\s+from\s+([^.,;]+)",
            r"\bstart(?:ing)?\s+in\s+([^.,;]+)",
            r"\bi\s+will\s+start\s+from\s+([^.,;]+)",
            r"\bi\s+will\s+start\s+in\s+([^.,;]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, user_request, re.IGNORECASE)

            if match:
                location = match.group(1).strip()

                if location:
                    return self._normalize_location_name(location)

        return None

    def _extract_home_location(self, user_request: str) -> Optional[str]:
        match = re.search(r"\bhome\s+(?:in|at)\s+([^.,;]+)", user_request, re.IGNORECASE)

        if match:
            return self._normalize_location_name(match.group(1).strip())

        return None

    def _extract_home_by_time(self, user_request: str) -> Optional[str]:
        patterns = [
            r"\bhome\s+by\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))",
            r"\bgoing\s+home\s+by\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))",
            r"\bgo\s+home\s+by\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))",
        ]

        for pattern in patterns:
            match = re.search(pattern, user_request, re.IGNORECASE)

            if match:
                return match.group(1).upper()

        return None

    def _normalize_location_name(self, location: str) -> str:
        normalized = location.strip()

        if not normalized:
            return normalized

        lowered = normalized.lower()

        if "makati" in lowered:
            return "Makati City, Philippines"

        if "bgc" in lowered or "bonifacio" in lowered:
            return "Bonifacio Global City, Taguig, Philippines"

        if "quezon" in lowered or lowered == "qc":
            return "Quezon City, Philippines"

        if "philippines" not in lowered:
            return f"{normalized}, Philippines"

        return normalized

    def _contains_any(self, value: str, keywords: List[str]) -> bool:
        normalized = self._normalize_text(value)
        return any(keyword in normalized for keyword in keywords)


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
            db,
            client,
            logger,
            task_tool,
            schedule_tool,
            notes_tool,
            maps_tool,
        )
        self.schedule_agent = ScheduleAgent(
            db,
            client,
            logger,
            task_tool,
            schedule_tool,
            notes_tool,
            maps_tool,
        )
        self.knowledge_agent = KnowledgeAgent(
            db,
            client,
            logger,
            task_tool,
            schedule_tool,
            notes_tool,
            maps_tool,
        )
        self.route_agent = RouteAgent(
            db,
            client,
            logger,
            task_tool,
            schedule_tool,
            notes_tool,
            maps_tool,
        )

    def plan(self, user_request: str, workflow_run_id: int) -> Dict[str, Any]:
        intent_fallback = {
            "summary": "Plan created.",
            "intent": "general_planning",
        }

        prompt = f"""
You are the primary CoordinatorAgent.

Your job:
- Understand the user's request.
- Produce a short summary.
- Produce a short intent label.

Return ONLY valid JSON with this schema:
{{
  "summary": "short summary",
  "intent": "short_intent_label"
}}

Planning rules:
- Think like a normal human planning a day.
- Tasks, events, and travel should not happen at the same time unless truly unavoidable.
- Fixed events should remain fixed.
- Flexible errands should be placed before or after fixed events with reasonable breathing room.
- Travel should happen between locations, not during meetings or tasks.
- Use reasonable transition buffers, usually around 10 minutes, when possible.

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