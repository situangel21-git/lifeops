import json
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import requests
from sqlalchemy.orm import Session

from app.models import Event, Note, Task, ToolLog


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

            created.append(
                {
                    "id": task.id,
                    "title": task.title,
                    "description": task.description,
                    "priority": task.priority,
                    "due_at": task.due_at,
                    "status": task.status,
                    "source_agent": task.source_agent,
                }
            )

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

            created.append(
                {
                    "id": event.id,
                    "title": event.title,
                    "start_at": event.start_at,
                    "end_at": event.end_at,
                    "location": event.location,
                    "source_agent": event.source_agent,
                }
            )

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
    ROUTES_ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"

    def __init__(self, db: Session, logger: ToolLogger):
        self.db = db
        self.logger = logger
        self.api_key = os.getenv("GOOGLE_MAPS_API_KEY")
        self.default_origin = os.getenv(
            "DAYWEAVER_DEFAULT_ORIGIN",
            "Makati City, Metro Manila, Philippines",
        )

    def estimate_travel(
        self,
        workflow_run_id: int,
        caller_agent: str,
        origin: str,
        destination: str,
    ) -> Dict[str, Any]:
        resolved_origin = self._resolve_vague_location(origin)
        resolved_destination = self._resolve_vague_location(destination)

        input_payload = {
            "origin": origin,
            "destination": destination,
            "resolved_origin": resolved_origin,
            "resolved_destination": resolved_destination,
        }

        if not self.api_key:
            output = self._fallback_output(
                origin=origin,
                destination=destination,
                resolved_origin=resolved_origin,
                resolved_destination=resolved_destination,
                status="missing_api_key",
                note=(
                    "GOOGLE_MAPS_API_KEY is not set. Returning fallback route data. "
                    "Set the key and enable Routes API + Maps Static API for real routes."
                ),
            )

            self.logger.log(
                workflow_run_id=workflow_run_id,
                agent_name=caller_agent,
                tool_name="MapsTool.estimate_travel",
                input_payload=input_payload,
                output_payload=output,
            )

            return output

        try:
            response = requests.post(
                self.ROUTES_ENDPOINT,
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": self.api_key,
                    "X-Goog-FieldMask": (
                        "routes.duration,"
                        "routes.staticDuration,"
                        "routes.distanceMeters,"
                        "routes.polyline.encodedPolyline,"
                        "routes.legs.startLocation.latLng,"
                        "routes.legs.endLocation.latLng"
                    ),
                },
                json={
                    "origin": {"address": resolved_origin},
                    "destination": {"address": resolved_destination},
                    "travelMode": "DRIVE",
                    "routingPreference": "TRAFFIC_AWARE",
                    "computeAlternativeRoutes": False,
                    "languageCode": "en-US",
                    "units": "METRIC",
                    "polylineQuality": "HIGH_QUALITY",
                    "polylineEncoding": "ENCODED_POLYLINE",
                },
                timeout=12,
            )

            response.raise_for_status()
            data = response.json()
            routes = data.get("routes") or []

            if not routes:
                output = self._fallback_output(
                    origin=origin,
                    destination=destination,
                    resolved_origin=resolved_origin,
                    resolved_destination=resolved_destination,
                    status="no_route_found",
                    note="Google Routes API returned no route for this origin/destination pair.",
                )
            else:
                route = routes[0]
                duration_seconds = self._parse_google_duration(route.get("duration"))
                estimated_minutes = max(1, round(duration_seconds / 60))
                distance_meters = route.get("distanceMeters")
                encoded_polyline = (
                    route.get("polyline", {}).get("encodedPolyline")
                    if isinstance(route.get("polyline"), dict)
                    else None
                )

                start_location, end_location = self._extract_leg_locations(route)

                output = {
                    "origin": origin,
                    "destination": destination,
                    "resolved_origin": resolved_origin,
                    "resolved_destination": resolved_destination,
                    "estimated_seconds": duration_seconds,
                    "estimated_minutes": estimated_minutes,
                    "distance_meters": distance_meters,
                    "distance_km": self._meters_to_km(distance_meters),
                    "mode": "driving",
                    "source": "Google Routes API",
                    "maps_api_status": "ok",
                    "encoded_polyline": encoded_polyline,
                    "start_location": start_location,
                    "end_location": end_location,
                    "google_maps_url": self._google_maps_directions_url(
                        resolved_origin,
                        resolved_destination,
                    ),
                    "note": "Real route estimate generated from Google Routes API.",
                }

        except Exception as exc:
            output = self._fallback_output(
                origin=origin,
                destination=destination,
                resolved_origin=resolved_origin,
                resolved_destination=resolved_destination,
                status="maps_api_error",
                note=f"Google Maps route lookup failed: {str(exc)}",
            )

        self.logger.log(
            workflow_run_id=workflow_run_id,
            agent_name=caller_agent,
            tool_name="MapsTool.estimate_travel",
            input_payload=input_payload,
            output_payload=output,
        )

        return output

    def _resolve_vague_location(self, value: Optional[str]) -> str:
        raw = (value or "").strip()

        if not raw:
            return self.default_origin

        vague_values = {
            "home",
            "my home",
            "house",
            "my house",
            "office",
            "my office",
            "work",
            "current location",
            "my location",
            "starting point",
            "start",
            "origin",
        }

        if raw.lower() in vague_values:
            return self.default_origin

        return raw

    def _fallback_output(
        self,
        origin: str,
        destination: str,
        resolved_origin: str,
        resolved_destination: str,
        status: str,
        note: str,
    ) -> Dict[str, Any]:
        return {
            "origin": origin,
            "destination": destination,
            "resolved_origin": resolved_origin,
            "resolved_destination": resolved_destination,
            "estimated_seconds": 1800,
            "estimated_minutes": 30,
            "distance_meters": None,
            "distance_km": None,
            "mode": "driving",
            "source": "Fallback",
            "maps_api_status": status,
            "encoded_polyline": None,
            "start_location": None,
            "end_location": None,
            "google_maps_url": self._google_maps_directions_url(
                resolved_origin,
                resolved_destination,
            ),
            "note": note,
        }

    def _parse_google_duration(self, value: Optional[str]) -> int:
        if not value:
            return 1800

        match = re.match(r"^(\d+)s$", str(value).strip())
        if not match:
            return 1800

        return int(match.group(1))

    def _meters_to_km(self, meters: Optional[int]) -> Optional[float]:
        if meters is None:
            return None

        try:
            return round(float(meters) / 1000, 2)
        except (TypeError, ValueError):
            return None

    def _extract_leg_locations(self, route: Dict[str, Any]) -> tuple[Optional[Dict[str, float]], Optional[Dict[str, float]]]:
        legs = route.get("legs") or []

        if not legs:
            return None, None

        first_leg = legs[0]
        last_leg = legs[-1]

        start_latlng = (
            first_leg.get("startLocation", {}).get("latLng")
            if isinstance(first_leg.get("startLocation"), dict)
            else None
        )

        end_latlng = (
            last_leg.get("endLocation", {}).get("latLng")
            if isinstance(last_leg.get("endLocation"), dict)
            else None
        )

        return self._normalize_latlng(start_latlng), self._normalize_latlng(end_latlng)

    def _normalize_latlng(self, value: Optional[Dict[str, Any]]) -> Optional[Dict[str, float]]:
        if not value:
            return None

        try:
            return {
                "lat": float(value["latitude"]),
                "lng": float(value["longitude"]),
            }
        except (KeyError, TypeError, ValueError):
            return None

    def _google_maps_directions_url(self, origin: str, destination: str) -> str:
        return (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={quote_plus(origin)}"
            f"&destination={quote_plus(destination)}"
            "&travelmode=driving"
        )