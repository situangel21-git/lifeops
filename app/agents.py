import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from google import genai
from sqlalchemy.orm import Session

from app.tools import MapsTool, NotesTool, ScheduleTool, TaskTool, ToolLogger


def normalize_for_compare(value: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


class DayPlanParser:
    ACTION_VERBS = [
        "stop by",
        "swing by",
        "pass by",
        "drop by",
        "pick up",
        "pickup",
        "pck up",
        "pik up",
        "collect",
        "claim",
        "fetch",
        "grab",
        "get",
        "buy",
        "buuy",
        "purchase",
        "purchse",
        "shop for",
        "shop",
        "order",
        "drop off",
        "dropoff",
        "drop-off",
        "drop",
        "drp",
        "leave",
        "deliver",
        "send",
        "bring",
        "take",
        "carry",
        "return",
        "visit",
        "call",
        "phone",
        "text",
        "message",
        "email",
        "reply",
        "respond",
        "follow up",
        "follow-up",
        "submit",
        "file",
        "sign",
        "scan",
        "print",
        "photocopy",
        "copy",
        "upload",
        "download",
        "share",
        "forward",
        "check",
        "verify",
        "confirm",
        "review",
        "approve",
        "pay",
        "settle",
        "renew",
        "book",
        "reserve",
        "schedule",
        "arrange",
        "coordinate",
        "register",
        "enroll",
        "prepare",
        "prep",
        "finish",
        "complete",
        "do",
        "make",
        "create",
        "draft",
        "write",
        "edit",
        "update",
        "fix",
        "test",
        "validate",
        "inspect",
        "install",
        "setup",
        "set up",
        "configure",
        "clean",
        "wash",
        "pack",
        "unpack",
        "cook",
        "play",
        "practice",
        "study",
        "read",
        "watch",
        "attend",
        "join",
        "meet",
    ]

    EVENT_PATTERN = (
        r"presentation|meeting|review|sync|call|appointment|reservation|"
        r"interview|class|session|workshop|training|consultation|briefing|demo"
    )

    TRAVEL_PREFIX_PATTERN = (
        r"travel to|drive to|commute to|head to|go to|proceed to|move to|"
        r"return to|return home|go home|going home|get home|be home|"
        r"be back home|head home|reach |arrive at|arrive in"
    )

    def __init__(self, user_request: str):
        self.user_request = self._compact(user_request)
        self.day = self._extract_day()
        self._clauses_cache: Optional[List[str]] = None
        self._events_cache: Optional[List[Dict[str, Any]]] = None
        self._tasks_cache: Optional[List[Dict[str, Any]]] = None
        self._ledger_cache: Optional[List[Dict[str, Any]]] = None
        self._routes_cache: Optional[List[Dict[str, Any]]] = None

    def _compact(self, value: Optional[str]) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    def _normalize(self, value: Optional[str]) -> str:
        return (
            str(value or "")
            .lower()
            .replace("_", " ")
            .replace("-", " ")
            .strip()
        )

    def _slug(self, value: Optional[str]) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self._normalize(value)).strip("-")

    def _action_pattern(self) -> str:
        ordered = sorted(self.ACTION_VERBS, key=len, reverse=True)
        return "|".join(re.escape(verb) for verb in ordered)

    def _extract_day(self) -> Optional[str]:
        match = re.search(
            r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            self.user_request,
            re.IGNORECASE,
        )
        return match.group(1).capitalize() if match else None

    def _parse_time_to_minutes(self, value: Optional[str]) -> Optional[int]:
        text = str(value or "")

        if re.search(r"\bbefore\s+(lunch|noon)\b", text, re.IGNORECASE):
            return 12 * 60

        if re.search(r"\bafter\s+lunch\b", text, re.IGNORECASE):
            return 13 * 60

        match = re.search(
            r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",
            text,
            re.IGNORECASE,
        )

        if not match:
            return None

        hour = int(match.group(1))
        minute = int(match.group(2) or "0")
        meridiem = match.group(3).lower()

        if meridiem == "pm" and hour < 12:
            hour += 12

        if meridiem == "am" and hour == 12:
            hour = 0

        return hour * 60 + minute

    def _format_minutes(self, minutes: int) -> str:
        minutes = max(0, min(23 * 60 + 59, minutes))
        hour_24 = minutes // 60
        minute = minutes % 60
        meridiem = "PM" if hour_24 >= 12 else "AM"
        hour_12 = hour_24 % 12 or 12
        minute_suffix = f":{minute:02d}" if minute else ""
        time_text = f"{hour_12}{minute_suffix} {meridiem}"
        return f"{self.day} {time_text}" if self.day else time_text

    def _canonical_location(self, value: Optional[str]) -> str:
        normalized = self._normalize(value)

        if not normalized:
            return ""

        if normalized in {"home", "my home", "house", "my house"}:
            return "home"

        if "bgc" in normalized or "bonifacio" in normalized:
            return "bgc"

        if "ortigas" in normalized:
            return "ortigas"

        if "makati" in normalized:
            return "makati"

        if "pasig" in normalized:
            return "pasig"

        if "quezon" in normalized or normalized == "qc":
            return "quezon-city"

        if "alabang" in normalized or "muntinlupa" in normalized:
            return "alabang"

        if "mandaluyong" in normalized:
            return "mandaluyong"

        if "taguig" in normalized:
            return "taguig"

        if "marikina" in normalized:
            return "marikina"

        if "san juan" in normalized:
            return "san-juan"

        if "paranaque" in normalized or "parañaque" in normalized:
            return "paranaque"

        if "las pinas" in normalized or "las piñas" in normalized:
            return "las-pinas"

        if "caloocan" in normalized:
            return "caloocan"

        if "valenzuela" in normalized:
            return "valenzuela"

        if "navotas" in normalized:
            return "navotas"

        if "malabon" in normalized:
            return "malabon"

        if "muntinlupa" in normalized:
            return "muntinlupa"

        if "manila" in normalized:
            return "manila"

        normalized = normalized.replace("city of ", "")
        normalized = normalized.replace("metro manila", "")
        normalized = normalized.replace("philippines", "")
        normalized = normalized.replace("province", "")
        normalized = normalized.replace("barangay", "")
        normalized = normalized.replace("brgy", "")
        normalized = normalized.strip()

        return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")

    def _normalize_location_name(self, location: Optional[str]) -> Optional[str]:
        text = self._compact(location)

        if not text:
            return None

        lowered = text.lower()

        if lowered in {"home", "my home", "house", "my house"}:
            home_location = os.getenv("DAYWEAVER_HOME_LOCATION")
            return home_location if home_location else None

        if "bgc" in lowered or "bonifacio" in lowered:
            return "Bonifacio Global City, Taguig, Philippines"

        if "ortigas" in lowered:
            return "Ortigas Center, Philippines"

        if "makati" in lowered:
            return "Makati City, Philippines"

        if "pasig" in lowered:
            return "Pasig City, Philippines"

        if "quezon" in lowered or lowered == "qc":
            return "Quezon City, Philippines"

        if "alabang" in lowered or "muntinlupa" in lowered:
            return "Alabang, Muntinlupa, Philippines"

        if "mandaluyong" in lowered:
            return "Mandaluyong City, Philippines"

        if "taguig" in lowered:
            return "Taguig City, Philippines"

        if "marikina" in lowered:
            return "Marikina City, Philippines"

        if "san juan" in lowered:
            return "San Juan City, Philippines"

        if "paranaque" in lowered or "parañaque" in lowered:
            return "Parañaque City, Philippines"

        if "las pinas" in lowered or "las piñas" in lowered:
            return "Las Piñas City, Philippines"

        if "caloocan" in lowered:
            return "Caloocan City, Philippines"

        if "valenzuela" in lowered:
            return "Valenzuela City, Philippines"

        if "navotas" in lowered:
            return "Navotas City, Philippines"

        if "malabon" in lowered:
            return "Malabon City, Philippines"

        if "manila" in lowered:
            return "Manila, Philippines"

        if "philippines" not in lowered:
            return f"{text}, Philippines"

        return text

    def _friendly_location(self, location: Optional[str]) -> Optional[str]:
        key = self._canonical_location(location)

        mapping = {
            "bgc": "BGC",
            "ortigas": "Ortigas",
            "makati": "Makati",
            "pasig": "Pasig",
            "quezon-city": "Quezon City",
            "alabang": "Alabang",
            "mandaluyong": "Mandaluyong",
            "taguig": "Taguig",
            "manila": "Manila",
            "marikina": "Marikina",
            "san-juan": "San Juan",
            "paranaque": "Parañaque",
            "las-pinas": "Las Piñas",
            "caloocan": "Caloocan",
            "valenzuela": "Valenzuela",
            "navotas": "Navotas",
            "malabon": "Malabon",
            "home": "Home",
        }

        return mapping.get(key, self._compact(location))

    def _clean_location_candidate(self, value: Optional[str]) -> Optional[str]:
        text = self._compact(value)

        if not text:
            return None

        text = re.split(
            r"\s+(?:before|after|by|then|and|with|for|to pick|to buy|to get|to attend|to meet|but|when|constraint)\b",
            text,
            flags=re.IGNORECASE,
        )[0]

        text = re.sub(
            r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b.*$",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = text.strip(" .,-;:")

        return text or None

    def _remove_timing_and_future_travel_constraints(self, clause: str) -> str:
        text = self._compact(clause)

        text = re.sub(
            r"\s+before\s+(?:going|go|heading|head|traveling|travelling|travel|driving|drive|commuting|commute|leaving|leave|proceeding|proceed|moving|move)\s+(?:to\s+[^.,;\n]+|there|here)",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"\s+after\s+the\s+(?:meeting|review|sync|presentation|call|appointment|event|class|session|workshop|training|demo).*?$",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"\s+(?:before|after|by|when|afterward|afterwards)\b.*$",
            "",
            text,
            flags=re.IGNORECASE,
        )

        return self._compact(text)

    def _extract_location_phrase(self, value: str) -> Optional[str]:
        text = self._compact(value)

        if not text:
            return None

        patterns = [
            r"\b(?:location:|in|at|to|near|around)\s+([^.,;\n]+)",
            r"\bfrom\s+([^.,;\n]+)",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                candidate = self._clean_location_candidate(match.group(1))

                if candidate and self._is_probable_location(candidate):
                    return candidate

        return None

    def _extract_task_location_phrase(self, clause: str) -> Optional[str]:
        text = self._remove_timing_and_future_travel_constraints(clause)

        if not text:
            return None

        patterns = [
            r"\blocation:\s+([^.,;\n]+)",
            r"\b(?:in|at|near|around)\s+([^.,;\n]+)",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                candidate = self._clean_location_candidate(match.group(1))

                if candidate and self._is_probable_location(candidate):
                    return candidate

        return None

    def _looks_like_non_location(self, value: str) -> bool:
        normalized = self._normalize(value)

        non_locations = {
            "lunch",
            "dinner",
            "breakfast",
            "meeting",
            "call",
            "presentation",
            "appointment",
            "review",
            "sync",
            "task",
            "errand",
            "work",
            "it",
            "that",
            "materials",
            "presentation materials",
            "printer ink",
            "printer",
            "vitamins",
            "phone charger",
            "charger",
            "pharmacy",
            "pharmacy nearby",
            "nearby",
            "client meeting",
            "client sync",
            "project review",
            "budget review",
            "documents",
            "package",
            "parcel",
            "food",
            "groceries",
            "medicine",
            "supplies",
            "items",
            "stuff",
            "plan my day",
            "plan the day",
            "my day",
            "day",
        }

        return normalized in non_locations

    def _is_task_like_text(self, value: Optional[str]) -> bool:
        normalized = self._normalize(value)

        if not normalized:
            return True

        action_words = [
            "buy",
            "purchase",
            "pick up",
            "pickup",
            "collect",
            "get ",
            "grab",
            "drop",
            "drop off",
            "stop by",
            "submit",
            "send",
            "email",
            "call",
            "text",
            "message",
            "bring",
            "take",
            "deliver",
            "print",
            "prepare",
            "prep",
            "review",
            "finish",
            "complete",
            "check",
            "verify",
            "pay",
            "book",
            "reserve",
            "schedule",
            "arrange",
            "play",
            "practice",
            "study",
            "read",
            "watch",
            "clean",
            "cook",
            "pack",
            "plan my day",
            "plan the day",
        ]

        if any(normalized.startswith(word) for word in action_words):
            return True

        object_words = [
            "presentation materials",
            "printer ink",
            "printer",
            "phone charger",
            "charger",
            "vitamins",
            "medicine",
            "package",
            "parcel",
            "documents",
            "groceries",
            "materials",
            "supplies",
            "items",
            "pharmacy nearby",
            "client meeting",
            "client sync",
            "project review",
            "budget review",
        ]

        if any(word in normalized for word in object_words):
            return True

        return False

    def _is_event_like_text(self, value: Optional[str]) -> bool:
        normalized = self._normalize(value)

        if not normalized:
            return False

        event_words = [
            "client meeting",
            "client sync",
            "client call",
            "project review",
            "budget review",
            "presentation",
            "meeting",
            "review",
            "sync",
            "appointment",
            "interview",
            "class",
            "session",
            "workshop",
            "training",
            "consultation",
            "briefing",
            "demo",
        ]

        return any(word in normalized for word in event_words)

    def _is_probable_location(self, value: Optional[str]) -> bool:
        text = self._compact(value)
        normalized = self._normalize(text)

        if not normalized:
            return False

        if normalized == "home":
            return True

        if self._looks_like_non_location(text):
            return False

        if self._is_task_like_text(text):
            return False

        if self._is_event_like_text(text):
            return False

        if len(normalized) < 2:
            return False

        return True

    def _is_valid_route_endpoint(self, value: Optional[str]) -> bool:
        text = self._compact(value)
        normalized = self._normalize(text)

        if not normalized:
            return False

        if normalized == "home":
            return bool(os.getenv("DAYWEAVER_HOME_LOCATION"))

        if self._looks_like_non_location(text):
            return False

        if self._is_task_like_text(text):
            return False

        if self._is_event_like_text(text):
            return False

        if re.search(r"\b(?:need|needs|needed|must|should|please|task|todo)\b", normalized):
            return False

        return True

    def clauses(self) -> List[str]:
        if self._clauses_cache is not None:
            return self._clauses_cache

        protected = re.sub(
            r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",
            lambda match: match.group(0).replace(" ", "_"),
            self.user_request,
            flags=re.IGNORECASE,
        )

        parts = re.split(
            r"[.;\n]|,|\bthen\b|\band then\b|\balso\b",
            protected,
            flags=re.IGNORECASE,
        )

        self._clauses_cache = [
            self._compact(part.replace("_", " ").strip(" ,"))
            for part in parts
            if self._compact(part.replace("_", " ").strip(" ,"))
        ]

        return self._clauses_cache

    def start_location(self) -> Optional[str]:
        patterns = [
            r"\bday\s+starts?\s+(?:at|in|from)\s+([^.,;\n]+)",
            r"\bday\s+started\s+(?:at|in|from)\s+([^.,;\n]+)",
            r"\bstart(?:ing)?\s+the\s+day\s+(?:at|in|from)\s+([^.,;\n]+)",
            r"\bstart(?:ing)?\s+from\s+([^.,;\n]+)",
            r"\bstart(?:ing)?\s+in\s+([^.,;\n]+)",
            r"\bstart(?:ing)?\s+at\s+([^.,;\n]+)",
            r"\bi\s+will\s+start\s+(?:from|in|at)\s+([^.,;\n]+)",
            r"\bi\s+am\s+starting\s+(?:from|in|at)\s+([^.,;\n]+)",
            r"\bcoming\s+from\s+([^.,;\n]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, self.user_request, re.IGNORECASE)

            if match:
                location = self._clean_location_candidate(match.group(1))
                if location and self._is_probable_location(location):
                    return location

        return None

    def final_destination(self) -> Optional[str]:
        patterns = [
            r"\breturn\s+to\s+([^.,;\n]+)",
            r"\breturning\s+to\s+([^.,;\n]+)",
            r"\bbe\s+back\s+home\s+(?:in|at|to)\s+([^.,;\n]+?)\s+(?:by|before|at)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)",
            r"\breach\s+([^.,;\n]+?)\s+(?:by|before|at)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)",
            r"\barrive\s+(?:at|in)\s+([^.,;\n]+?)\s+(?:by|before|at)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)",
            r"\bgo(?:ing)?\s+home\s+(?:to|in|at)\s+([^.,;\n]+)",
            r"\bhome\s+(?:in|at)\s+([^.,;\n]+)",
            r"\bhouse\s+(?:in|at)\s+([^.,;\n]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, self.user_request, re.IGNORECASE)

            if match:
                location = self._clean_location_candidate(match.group(1))
                if location and self._is_probable_location(location):
                    return location

        if re.search(
            r"\b(return home|go home|going home|get home|be home|be back home|head home|home by|home before|home at)\b",
            self.user_request,
            re.IGNORECASE,
        ):
            home_location = os.getenv("DAYWEAVER_HOME_LOCATION")
            return home_location if home_location else "Home"

        return None

    def final_arrive_by(self) -> Optional[str]:
        patterns = [
            r"\b(?:return\s+to|returning\s+to|reach|arrive\s+at|arrive\s+in|be\s+back\s+home|home|go\s+home|going\s+home|get\s+home|be\s+home)\s+[^.,;\n]*?\b(?:by|before|at)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))",
        ]

        for pattern in patterns:
            match = re.search(pattern, self.user_request, re.IGNORECASE)

            if match:
                return match.group(1).upper()

        return None

    def _event_from_clause(self, clause: str, order: int) -> Optional[Dict[str, Any]]:
        event_patterns = [
            {
                "pattern": r"\b(?:travel|go|head|drive|commute|proceed|move)\s+to\s+([^.,;\n]+?)\s+for\s+(?:a|an)?\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s+([^.,;\n]+?(?:presentation|meeting|review|sync|call|appointment|reservation|interview|class|session|workshop|training|consultation|briefing|demo))",
                "location_group": 1,
                "time_group": 2,
                "title_group": 3,
            },
            {
                "pattern": r"\b(?:i\s+have|have|there\s+is)?\s*(?:a|an)?\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s+([^.,;\n]+?(?:presentation|meeting|review|sync|call|appointment|reservation|interview|class|session|workshop|training|consultation|briefing|demo))\s+(?:in|at)\s+([^.,;\n]+)",
                "time_group": 1,
                "title_group": 2,
                "location_group": 3,
            },
            {
                "pattern": r"\b(?:i\s+have|have|there\s+is)?\s*(?:a|an)?\s*([^.,;\n]+?(?:presentation|meeting|review|sync|call|appointment|reservation|interview|class|session|workshop|training|consultation|briefing|demo))\s+(?:in|at)\s+([^.,;\n]+?)\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))",
                "title_group": 1,
                "location_group": 2,
                "time_group": 3,
            },
            {
                "pattern": r"\b(?:i\s+have|have|there\s+is)?\s*(?:a|an)?\s*([^.,;\n]+?(?:presentation|meeting|review|sync|call|appointment|reservation|interview|class|session|workshop|training|consultation|briefing|demo))\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s+(?:in|at)\s+([^.,;\n]+)",
                "title_group": 1,
                "time_group": 2,
                "location_group": 3,
            },
        ]

        for event_pattern in event_patterns:
            match = re.search(event_pattern["pattern"], clause, re.IGNORECASE)

            if not match:
                continue

            title_text = self._compact(match.group(event_pattern["title_group"]))
            location_text = self._compact(match.group(event_pattern["location_group"]))
            time_text = self._compact(match.group(event_pattern["time_group"]))

            title = self._clean_event_title(title_text)
            location = self._clean_location_candidate(location_text)
            start_minutes = self._parse_time_to_minutes(time_text)

            if not title or not location or start_minutes is None:
                continue

            if not self._is_probable_location(location):
                continue

            return {
                "type": "event",
                "title": title,
                "order": order,
                "start_minutes": start_minutes,
                "end_minutes": start_minutes + 60,
                "location": location,
                "start_at": self._format_minutes(start_minutes),
                "end_at": self._format_minutes(start_minutes + 60),
            }

        return None

    def _clean_event_title(self, title: str) -> str:
        cleaned = self._compact(title)
        cleaned = re.sub(r"^(?:i\s+have|have|a|an|the)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+with\s+.*$", "", cleaned, flags=re.IGNORECASE)

        words = []
        for word in cleaned.split(" "):
            if len(word) <= 4 and word.upper() == word:
                words.append(word.upper())
            else:
                words.append(word[:1].upper() + word[1:].lower())

        return " ".join(words)

    def _prep_minutes_from_text(self, text: str) -> Optional[int]:
        patterns = [
            r"(\d+)\s+minutes?\s+of\s+prep",
            r"(\d+)\s+minutes?\s+prep",
            r"(\d+)\s+hour(?:s)?\s+of\s+prep",
            r"(\d+)\s+hour(?:s)?\s+prep",
            r"(one)\s+hour\s+of\s+prep",
            r"(one)\s+hour\s+prep",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)

            if not match:
                continue

            value = match.group(1).lower()

            if value == "one":
                return 60

            amount = int(value)

            if "hour" in match.group(0).lower():
                return amount * 60

            return amount

        if re.search(
            r"\bprepare\s+for\s+(?:a|an|the)?\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)\s+",
            text,
            re.IGNORECASE,
        ):
            return 30

        return None

    def _prep_target(self, parsed_events: List[Dict[str, Any]]) -> Tuple[Optional[int], Optional[int]]:
        prep_minutes = None
        target_order = None

        for index, clause in enumerate(self.clauses()):
            minutes = self._prep_minutes_from_text(clause)

            if minutes is None:
                continue

            prep_minutes = minutes

            same_clause_event = self._event_from_clause(clause, index)
            if same_clause_event:
                target_order = same_clause_event["order"]
                break

            previous_events = [event for event in parsed_events if event["order"] < index]
            if previous_events:
                target_order = previous_events[-1]["order"]
                break

            next_events = [event for event in parsed_events if event["order"] > index]
            if next_events:
                target_order = next_events[0]["order"]
                break

        if prep_minutes is None:
            prep_minutes = self._prep_minutes_from_text(self.user_request)

        if prep_minutes is not None and target_order is None and parsed_events:
            target_order = parsed_events[0]["order"]

        return prep_minutes, target_order

    def _event_category(self, title: str) -> str:
        normalized = self._normalize(title)

        if "prep" in normalized:
            return "prep"

        for word in [
            "presentation",
            "meeting",
            "review",
            "sync",
            "call",
            "appointment",
            "reservation",
            "interview",
            "class",
            "session",
            "workshop",
            "training",
            "consultation",
            "briefing",
            "demo",
        ]:
            if word in normalized:
                return word

        return self._slug(normalized)

    def events(self) -> List[Dict[str, Any]]:
        if self._events_cache is not None:
            return self._events_cache

        parsed_events = []
        seen = set()

        for index, clause in enumerate(self.clauses()):
            event = self._event_from_clause(clause, index)

            if not event:
                continue

            event_key = (
                self._event_category(event["title"]),
                event["start_minutes"],
                self._canonical_location(event["location"]),
            )

            if event_key in seen:
                continue

            seen.add(event_key)
            parsed_events.append(event)

        prep_minutes, prep_target_order = self._prep_target(parsed_events)

        events = []
        seen_output = set()

        for event in parsed_events:
            if prep_minutes and prep_target_order == event["order"]:
                prep_start = event["start_minutes"] - prep_minutes
                prep_key = (
                    "prep",
                    prep_start,
                    self._canonical_location(event["location"]),
                )

                if prep_key not in seen_output:
                    seen_output.add(prep_key)
                    events.append(
                        {
                            "title": f"Prep for {event['title']}",
                            "start_at": self._format_minutes(prep_start),
                            "end_at": self._format_minutes(event["start_minutes"]),
                            "location": event["location"],
                        }
                    )

            output_key = (
                self._event_category(event["title"]),
                event["start_minutes"],
                self._canonical_location(event["location"]),
            )

            if output_key not in seen_output:
                seen_output.add(output_key)
                events.append(
                    {
                        "title": event["title"],
                        "start_at": event["start_at"],
                        "end_at": event["end_at"],
                        "location": event["location"],
                    }
                )

        self._events_cache = events
        return events

    def _extract_action_and_object(self, clause: str) -> Optional[Tuple[str, str]]:
        normalized = self._normalize(clause)

        if re.match(r"^plan\s+(my|the|a|this|our)\s+day\b", normalized):
            return None

        if re.match(r"^plan\s+(my|the|a|this|our)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", normalized):
            return None

        action_pattern = self._action_pattern()

        action_match = re.search(
            rf"\b({action_pattern})\b\s+(.+)$",
            clause,
            re.IGNORECASE,
        )

        if action_match:
            return (
                self._compact(action_match.group(1)).lower(),
                self._compact(action_match.group(2)),
            )

        generic_patterns = [
            r"\b(?:i|we)\s+plan(?:s|ned)?\s+to\s+([a-zA-Z][a-zA-Z'\-]*)\s+(.+)$",
            r"\b(?:i|we)?\s*(?:need|needs|needed|have|has|had|must|should|want|wants|wanted|going|will|please)\s+(?:to\s+)?([a-zA-Z][a-zA-Z'\-]*)\s+(.+)$",
            r"\b(?:can you|could you|pls|please)\s+([a-zA-Z][a-zA-Z'\-]*)\s+(.+)$",
        ]

        for pattern in generic_patterns:
            match = re.search(pattern, clause, re.IGNORECASE)

            if not match:
                continue

            verb = self._compact(match.group(1)).lower()
            obj = self._compact(match.group(2))

            blocked_verbs = {
                "start",
                "begin",
                "begins",
                "started",
                "starts",
                "travel",
                "drive",
                "commute",
                "head",
                "go",
                "return",
                "reach",
                "arrive",
                "be",
                "have",
                "has",
                "is",
                "are",
                "was",
                "were",
                "plan",
                "plans",
                "planned",
            }

            if verb in blocked_verbs:
                continue

            return (verb, obj)

        return None

    def _task_from_clause(
        self,
        clause: str,
        current_location: Optional[str],
        order: int,
    ) -> Optional[Dict[str, Any]]:
        normalized = self._normalize(clause)

        if not normalized:
            return None

        if re.match(r"^plan\s+(my|the|a|this|our)\s+day\b", normalized):
            return None

        if self._event_from_clause(clause, order):
            return None

        action_parts = self._extract_action_and_object(clause)

        if not action_parts:
            if self._looks_like_travel_or_destination_clause(clause):
                return None
            return None

        verb, obj_raw = action_parts
        obj = self._clean_task_object(obj_raw)

        if not obj:
            return None

        title = self._build_task_title(verb, obj)
        explicit_location = self._extract_task_location_phrase(clause)
        inferred_location = explicit_location

        if re.search(r"\bnearby\b", clause, re.IGNORECASE):
            inferred_location = current_location

        if not inferred_location and current_location:
            physical_action_words = [
                "buy",
                "purchase",
                "shop",
                "pick",
                "pickup",
                "collect",
                "claim",
                "fetch",
                "get",
                "grab",
                "drop",
                "leave",
                "deliver",
                "send",
                "bring",
                "take",
                "visit",
                "stop",
                "swing",
                "pass",
                "order",
                "book",
                "reserve",
                "pay",
                "print",
                "scan",
                "photocopy",
            ]

            if any(word in self._normalize(title) for word in physical_action_words):
                inferred_location = current_location

        due_at = self._infer_due_at(clause, order)

        description_parts = [title]

        if inferred_location:
            description_parts.append(f"Location: {self._friendly_location(inferred_location)}")

        if due_at:
            description_parts.append(f"Constraint: {due_at}")

        description = ". ".join(description_parts)

        return {
            "type": "task",
            "title": title,
            "description": description,
            "priority": self._infer_priority(clause),
            "due_at": due_at,
            "status": "open",
            "order": order,
            "location": inferred_location,
        }

    def _clean_task_object(self, value: str) -> str:
        text = self._compact(value)
        text = re.sub(r"^(?:a|an|the|some)\s+", "", text, flags=re.IGNORECASE)

        text = re.sub(
            r"\s+before\s+(?:going|go|heading|head|traveling|travelling|travel|driving|drive|commuting|commute|leaving|leave|proceeding|proceed|moving|move)\s+(?:to\s+[^.,;\n]+|there|here)",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"\s+(?:before|after|by|when|afterward|afterwards)\b.*$",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = re.sub(
            r"\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm).*$",
            "",
            text,
            flags=re.IGNORECASE,
        )

        return text.strip(" ,.;:")

    def _build_task_title(self, verb: str, obj: str) -> str:
        verb_map = {
            "pickup": "Pick up",
            "pck up": "Pick up",
            "pik up": "Pick up",
            "pick up": "Pick up",
            "dropoff": "Drop off",
            "drop-off": "Drop off",
            "drop off": "Drop off",
            "drp": "Drop",
            "buuy": "Buy",
            "purchse": "Purchase",
            "stop by": "Stop by",
            "swing by": "Swing by",
            "pass by": "Pass by",
            "drop by": "Drop by",
            "follow up": "Follow up",
            "follow-up": "Follow up",
            "set up": "Set up",
        }

        clean_verb = verb_map.get(verb, verb.capitalize())
        return f"{clean_verb} {obj}"[:255]

    def _infer_due_at(self, clause: str, order: int) -> Optional[str]:
        patterns = [
            r"before\s+(?:going|go|heading|head|traveling|travelling|travel|driving|drive|commuting|commute|leaving|leave|proceeding|proceed|moving|move)\s+(?:to\s+[^.,;\n]+|there|here)",
            r"after\s+the\s+(?:meeting|review|sync|presentation|call|appointment|event|class|session|workshop|training|demo)",
            r"before\s+the\s+(?:meeting|review|sync|presentation|call|appointment|event|class|session|workshop|training|demo)",
            r"before\s+going\s+home(?:\s+(?:by|before|at)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm))?",
            r"afterward",
            r"afterwards",
            r"before\s+(?:lunch|noon|dinner|breakfast)",
            r"after\s+(?:lunch|noon|dinner|breakfast)",
            r"by\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)",
            r"before\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)",
            r"after\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)",
        ]

        for pattern in patterns:
            match = re.search(pattern, clause, re.IGNORECASE)

            if match:
                value = self._compact(match.group(0))
                if value.lower() in {"afterward", "afterwards"}:
                    return "after the previous activity"
                return value

        return None

    def _infer_priority(self, clause: str) -> str:
        text = self._normalize(clause)

        if any(word in text for word in ["urgent", "critical", "important", "must"]):
            return "high"

        return "medium"

    def _looks_like_travel_or_destination_clause(self, clause: str) -> bool:
        text = self._normalize(clause)
        return bool(re.search(rf"\b(?:{self.TRAVEL_PREFIX_PATTERN})\b", text, re.IGNORECASE))

    def _task_key(self, task: Dict[str, Any]) -> str:
        title = self._normalize(task.get("title"))
        location = self._canonical_location(
            task.get("location") or self._extract_location_phrase(task.get("description", "")) or ""
        )

        core = title
        core = re.sub(r"\b(a|an|the|my|some)\b", " ", core)
        core = re.sub(r"\b(in|at|near|around|from|to|location)\b\s+.+$", "", core)
        core = re.sub(r"\b(before|after|by|when|constraint)\b\s+.+$", "", core)
        core = re.sub(r"\s+", " ", core).strip()

        return f"{self._slug(core)}-{location}".strip("-")

    def _resolve_before_there_task(
        self,
        task: Dict[str, Any],
        last_event: Optional[Dict[str, Any]],
        location_before_last_event: Optional[str],
    ) -> Dict[str, Any]:
        due_at = self._normalize(task.get("due_at"))
        if not due_at:
            return task

        references_there = bool(
            re.search(
                r"\bbefore\s+(?:going|go|heading|head|traveling|travelling|travel|driving|drive|commuting|commute|leaving|leave|proceeding|proceed|moving|move)\s+(?:there|here)\b",
                due_at,
                re.IGNORECASE,
            )
        )

        if references_there and last_event:
            target_location = self._friendly_location(last_event.get("location"))
            task["due_at"] = f"before going to {target_location}"

            if location_before_last_event:
                task["location"] = location_before_last_event

            task["before_event_order"] = last_event.get("order")
            task["description"] = self._rebuild_task_description(task)
            return task

        explicit_match = re.search(
            r"\bbefore\s+(?:going|go|heading|head|traveling|travelling|travel|driving|drive|commuting|commute|leaving|leave|proceeding|proceed|moving|move)\s+to\s+([^.,;\n]+)",
            str(task.get("due_at") or ""),
            re.IGNORECASE,
        )

        if explicit_match and last_event:
            target = self._clean_location_candidate(explicit_match.group(1))
            if (
                target
                and self._canonical_location(target) == self._canonical_location(last_event.get("location"))
                and location_before_last_event
            ):
                task["location"] = location_before_last_event
                task["before_event_order"] = last_event.get("order")
                task["description"] = self._rebuild_task_description(task)

        return task

    def _rebuild_task_description(self, task: Dict[str, Any]) -> str:
        parts = [task["title"]]

        if task.get("location"):
            parts.append(f"Location: {self._friendly_location(task.get('location'))}")

        if task.get("due_at"):
            parts.append(f"Constraint: {task.get('due_at')}")

        return ". ".join(parts)

    def _apply_final_deadline_to_late_tasks(self, ledger: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        final_destination = self.final_destination()
        final_arrive_by = self.final_arrive_by()

        if not final_destination or not final_arrive_by:
            return ledger

        final_key = self._canonical_location(final_destination)
        if final_key == "home":
            constraint = f"before going home by {final_arrive_by}"
        else:
            constraint = f"before going to {self._friendly_location(final_destination)} by {final_arrive_by}"

        last_event_order = -999
        for item in ledger:
            if item.get("type") == "event":
                last_event_order = max(last_event_order, int(item.get("order", -999)))

        for item in ledger:
            if item.get("type") != "task":
                continue

            if item.get("due_at"):
                continue

            if int(item.get("order", 0)) >= last_event_order:
                item["due_at"] = constraint
                item["description"] = self._rebuild_task_description(item)

        return ledger

    def ledger(self) -> List[Dict[str, Any]]:
        if self._ledger_cache is not None:
            return self._ledger_cache

        ledger: List[Dict[str, Any]] = []
        current_location = self.start_location()
        last_event: Optional[Dict[str, Any]] = None
        location_before_last_event: Optional[str] = None

        if current_location:
            ledger.append(
                {
                    "type": "start",
                    "title": "Start",
                    "location": current_location,
                    "order": -1,
                }
            )

        for order, clause in enumerate(self.clauses()):
            event = self._event_from_clause(clause, order)

            if event:
                location_before_last_event = current_location
                last_event = event
                ledger.append(event)
                current_location = event["location"]
                continue

            task = self._task_from_clause(
                clause=clause,
                current_location=current_location,
                order=order,
            )

            if task:
                task = self._resolve_before_there_task(
                    task=task,
                    last_event=last_event,
                    location_before_last_event=location_before_last_event,
                )

                ledger.append(task)

                if task.get("location") and not task.get("before_event_order"):
                    current_location = task["location"]

        ledger = self._apply_final_deadline_to_late_tasks(ledger)

        final_destination = self.final_destination()

        if final_destination:
            ledger.append(
                {
                    "type": "destination",
                    "title": "Final destination",
                    "location": final_destination,
                    "arrive_by": self.final_arrive_by(),
                    "order": len(self.clauses()) + 1,
                }
            )

        ledger = sorted(
            ledger,
            key=lambda item: (
                float(item.get("before_event_order")) - 0.1
                if item.get("type") == "task" and item.get("before_event_order") is not None
                else float(item.get("order", 9999))
            ),
        )

        self._ledger_cache = ledger
        return ledger

    def tasks(self) -> List[Dict[str, Any]]:
        if self._tasks_cache is not None:
            return self._tasks_cache

        tasks = []
        seen = set()

        for item in self.ledger():
            if item.get("type") != "task":
                continue

            key = self._task_key(item)

            if not key or key in seen:
                continue

            seen.add(key)
            tasks.append(
                {
                    "title": item["title"],
                    "description": item.get("description"),
                    "priority": item.get("priority", "medium"),
                    "due_at": item.get("due_at"),
                    "status": "open",
                }
            )

        self._tasks_cache = tasks
        return tasks

    def routes(self, default_origin: str) -> List[Dict[str, Any]]:
        if self._routes_cache is not None:
            return self._routes_cache

        routes = []
        seen = set()

        current_location = self.start_location() or default_origin
        current_location = self._normalize_location_name(current_location) or default_origin

        parsed_events = [
            item for item in self.ledger()
            if item.get("type") == "event"
        ]
        prep_minutes, prep_target_order = self._prep_target(parsed_events)

        for item in self.ledger():
            if item.get("type") == "start":
                start_location = self._normalize_location_name(item.get("location"))
                if start_location and self._is_valid_route_endpoint(start_location):
                    current_location = start_location
                continue

            item_type = item.get("type")
            item_location = item.get("location")

            if item_type not in {"event", "task", "destination"}:
                continue

            if not item_location:
                continue

            destination = self._normalize_location_name(item_location)

            if not destination:
                continue

            if not self._is_valid_route_endpoint(current_location):
                continue

            if not self._is_valid_route_endpoint(destination):
                continue

            if self._canonical_location(current_location) != self._canonical_location(destination):
                arrive_by = None
                depart_after = None
                destination_event_title = None
                destination_task_title = None

                if item_type == "event":
                    arrive_minutes = item["start_minutes"]

                    if prep_minutes and prep_target_order == item["order"]:
                        arrive_minutes = item["start_minutes"] - prep_minutes

                    arrive_by = self._format_minutes(arrive_minutes)
                    destination_event_title = item["title"]

                elif item_type == "task":
                    if self._is_deadline(item.get("due_at")):
                        arrive_by = item.get("due_at")

                    if self._is_after_constraint(item.get("due_at")):
                        depart_after = item.get("due_at")

                    destination_task_title = item["title"]

                elif item_type == "destination":
                    arrive_by = item.get("arrive_by")
                    depart_after = "after completing the planned activities"

                self._append_route(
                    routes=routes,
                    seen=seen,
                    origin=current_location,
                    destination=destination,
                    arrive_by=arrive_by,
                    depart_after=depart_after,
                    purpose=self._route_purpose(destination, item),
                    destination_event_title=destination_event_title,
                    destination_task_title=destination_task_title,
                )

            current_location = destination

        self._routes_cache = routes[:8]
        return self._routes_cache

    def _route_purpose(self, destination: str, item: Dict[str, Any]) -> str:
        item_type = item.get("type")
        title = item.get("title")

        if item_type == "event":
            return f"Travel to {destination} for {title}."

        if item_type == "task":
            return f"Travel to {destination} for {title}."

        if item_type == "destination":
            return f"Travel to {destination} after completing the planned activities."

        return f"Travel to {destination}."

    def _is_deadline(self, value: Optional[str]) -> bool:
        text = self._normalize(value)
        return "before" in text or "by " in text or " at " in text

    def _is_after_constraint(self, value: Optional[str]) -> bool:
        text = self._normalize(value)
        return "after" in text

    def _append_route(
        self,
        routes: List[Dict[str, Any]],
        seen: set,
        origin: str,
        destination: str,
        arrive_by: Optional[str],
        depart_after: Optional[str],
        purpose: str,
        destination_event_title: Optional[str],
        destination_task_title: Optional[str],
    ) -> None:
        if not self._is_valid_route_endpoint(origin):
            return

        if not self._is_valid_route_endpoint(destination):
            return

        origin_key = self._canonical_location(origin)
        destination_key = self._canonical_location(destination)

        if not origin_key or not destination_key:
            return

        if origin_key == destination_key:
            return

        key = f"{origin_key}->{destination_key}"

        if key in seen:
            return

        seen.add(key)

        routes.append(
            {
                "origin": self._normalize_location_name(origin) or origin,
                "destination": self._normalize_location_name(destination) or destination,
                "arrive_by": arrive_by,
                "depart_after": depart_after,
                "purpose": purpose,
                "destination_event_title": destination_event_title,
                "destination_task_title": destination_task_title,
            }
        )


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

    def _slug(self, value: Optional[str]) -> str:
        normalized = self._normalize_text(value)
        return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")

    def _safe_string(self, value: Any) -> Optional[str]:
        if value is None:
            return None

        text = str(value).strip()
        return text if text else None

    def _normalize_priority(self, value: Any) -> str:
        normalized = self._normalize_text(value)

        if normalized in {"low", "medium", "high"}:
            return normalized

        if normalized in {"urgent", "critical", "important"}:
            return "high"

        return "medium"


class TaskAgent(BaseAgent):
    agent_name = "TaskAgent"

    def run(self, user_request: str, workflow_run_id: int) -> Dict[str, Any]:
        deterministic_tasks = DayPlanParser(user_request).tasks()

        if deterministic_tasks:
            tasks = deterministic_tasks
        else:
            fallback = {"tasks": []}
            prompt = f"""
You are TaskAgent in a multi-agent productivity system.

Extract ONLY actionable non-calendar tasks from the CURRENT user request.

Return ONLY valid JSON with this schema:
{{
  "tasks": [
    {{
      "title": "task title",
      "description": "optional description",
      "priority": "low|medium|high",
      "due_at": "optional natural language deadline, sequence, or constraint",
      "status": "open"
    }}
  ]
}}

Rules:
- Return JSON only.
- Do not wrap in markdown.
- Extract every explicit flexible action the user needs to do.
- Valid tasks include errands, purchases, pickups, drop-offs, pharmacy stops, reminders, follow-ups, calls to make, messages to send, things to bring, things to submit, things to buy, things to play, things to prepare, and things to finish.
- Do NOT create tasks for fixed meetings, calls, reviews, presentations, syncs, appointments, classes, or reservations when a time is given.
- Do NOT create a task for prep time when the user asks for a timed prep block before an event.
- Do NOT create a task for travel, going home, returning home, driving, or commuting.
- Do NOT create a task for general planning instructions like "plan my day".
- Preserve timing constraints such as "before lunch", "after lunch", "afterward", "after the presentation", "after the meeting", "before going there", "before going to BGC", "before heading to BGC", "before going home", or "by 6 PM".
- Preserve task locations naturally in the title or description.
- Do not invent tasks.
- Do not duplicate tasks.

User request:
{user_request}
"""
            result = self._model_json(prompt, fallback)
            model_tasks = result.get("tasks") or []
            tasks = self._merge_model_tasks(model_tasks)

        created_tasks = self.task_tool.create_tasks(
            tasks=tasks,
            workflow_run_id=workflow_run_id,
            source_agent=self.agent_name,
        )

        return {"tasks_created": created_tasks}

    def _merge_model_tasks(self, model_tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged = []
        seen = set()

        for task in model_tasks:
            if not isinstance(task, dict):
                continue

            title = self._safe_string(task.get("title"))

            if not title:
                continue

            normalized = self._normalize_text(title)

            if any(word in normalized for word in ["plan my day", "plan the day"]):
                continue

            if any(word in normalized for word in ["travel to", "go home", "return to", "drive to", "commute to"]):
                continue

            key = self._slug(title)

            if key in seen:
                continue

            seen.add(key)

            merged.append(
                {
                    "title": title[:255],
                    "description": self._safe_string(task.get("description")),
                    "priority": self._normalize_priority(task.get("priority")),
                    "due_at": self._safe_string(task.get("due_at")),
                    "status": self._safe_string(task.get("status")) or "open",
                }
            )

        return merged


class ScheduleAgent(BaseAgent):
    agent_name = "ScheduleAgent"

    def run(self, user_request: str, workflow_run_id: int) -> Dict[str, Any]:
        deterministic_events = DayPlanParser(user_request).events()

        if deterministic_events:
            events = deterministic_events
        else:
            fallback = {"events": []}
            prompt = f"""
You are ScheduleAgent in a multi-agent productivity system.

Extract ONLY fixed schedule blocks from the CURRENT user request.

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
- Events are fixed schedule blocks only.
- Create events for meetings, reviews, syncs, calls, presentations, appointments, reservations, interviews, classes, sessions, workshops, trainings, consultations, briefings, demos, and explicit blocked time.
- If the user asks for prep time before a fixed event, create a prep event before that fixed event.
- Do NOT create events for flexible errands, buying items, pickups, drop-offs, pharmacy stops, shopping, or travel.
- Do not duplicate events.
- If no end time is given, assume 1 hour.
- Preserve locations.

User request:
{user_request}
"""
            result = self._model_json(prompt, fallback)
            model_events = result.get("events") or []
            events = self._merge_model_events(model_events)

        created_events = self.schedule_tool.create_events(
            events=events,
            workflow_run_id=workflow_run_id,
            source_agent=self.agent_name,
        )

        return {"events_created": created_events}

    def _merge_model_events(self, model_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged = []
        seen = set()

        for event in model_events:
            if not isinstance(event, dict):
                continue

            title = self._safe_string(event.get("title"))
            start_at = self._safe_string(event.get("start_at"))
            end_at = self._safe_string(event.get("end_at"))
            location = self._safe_string(event.get("location"))

            if not title or not start_at:
                continue

            normalized_title = self._normalize_text(title)

            if any(word in normalized_title for word in ["buy ", "pick up", "pickup", "stop by", "travel", "return"]):
                continue

            key = self._slug(f"{title}-{start_at}-{location or ''}")

            if key in seen:
                continue

            seen.add(key)

            merged.append(
                {
                    "title": title[:255],
                    "start_at": start_at,
                    "end_at": end_at,
                    "location": location[:255] if location else None,
                }
            )

        return merged


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

Create one concise memory note for this workflow.

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
- Focus on the current request.
- Do not invent details.

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
        default_origin = os.getenv(
            "DAYWEAVER_DEFAULT_ORIGIN",
            "Makati City, Metro Manila, Philippines",
        )

        deterministic_routes = DayPlanParser(user_request).routes(default_origin)

        if deterministic_routes:
            routes = deterministic_routes
        else:
            fallback = {"routes": []}
            prompt = f"""
You are RouteAgent in a multi-agent productivity system.

Identify ONLY necessary travel legs for the CURRENT request.

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
- Only use actual physical locations as origin and destination.
- Never use task names like "buy printer", "buy materials", "buy charger", "drop package", "play basketball", or "pick up vitamins" as map destinations.
- Never use event names like "client meeting", "project review", or "client sync" as map destinations.
- Do not create travel inside the same area.
- Do not create travel for tasks without a physical location.
- Do not create an initial route into the user's stated starting location.
- Do not invent locations.
- Do not duplicate routes.
- If the user mentions returning, reaching, being home, or arriving somewhere by/before/at a time, include that final route/deadline.
- Routes must follow the actual chronological order.

User request:
{user_request}

Tasks created:
{json.dumps(tasks_created, ensure_ascii=False)}

Events created:
{json.dumps(events_created, ensure_ascii=False)}
"""
            result = self._model_json(prompt, fallback)
            model_routes = result.get("routes") or []
            routes = self._merge_model_routes(model_routes, default_origin)

        self.logger.log(
            workflow_run_id=workflow_run_id,
            agent_name=self.agent_name,
            tool_name="RouteAgent.identify_routes",
            input_payload={
                "user_request": user_request,
                "tasks_created": tasks_created,
                "events_created": events_created,
            },
            output_payload={"routes": routes},
        )

        travel_estimates = []

        for index, route in enumerate(routes[:8]):
            origin = self._safe_string(route.get("origin"))
            destination = self._safe_string(route.get("destination"))

            if not origin or not destination:
                continue

            if self._looks_invalid_route_endpoint(origin):
                continue

            if self._looks_invalid_route_endpoint(destination):
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

    def _looks_invalid_route_endpoint(self, value: Optional[str]) -> bool:
        normalized = self._normalize_text(value)

        if not normalized:
            return True

        if normalized == "home":
            return not bool(os.getenv("DAYWEAVER_HOME_LOCATION"))

        bad_words = [
            "buy",
            "purchase",
            "pick up",
            "pickup",
            "collect",
            "get ",
            "grab",
            "drop",
            "drop off",
            "stop by",
            "submit",
            "send",
            "email",
            "call",
            "text",
            "message",
            "bring",
            "take",
            "deliver",
            "print",
            "prepare",
            "prep",
            "review",
            "finish",
            "complete",
            "check",
            "verify",
            "pay",
            "book",
            "reserve",
            "schedule",
            "arrange",
            "play",
            "practice",
            "study",
            "read",
            "watch",
            "clean",
            "cook",
            "pack",
            "presentation materials",
            "printer ink",
            "printer",
            "phone charger",
            "charger",
            "vitamins",
            "medicine",
            "package",
            "parcel",
            "documents",
            "groceries",
            "materials",
            "supplies",
            "items",
            "pharmacy nearby",
            "client meeting",
            "client sync",
            "client call",
            "project review",
            "budget review",
            "meeting",
            "sync",
            "presentation",
            "plan my day",
        ]

        return any(word in normalized for word in bad_words)

    def _merge_model_routes(self, model_routes: List[Dict[str, Any]], default_origin: str) -> List[Dict[str, Any]]:
        merged = []
        seen = set()

        for route in model_routes:
            if not isinstance(route, dict):
                continue

            origin = self._safe_string(route.get("origin")) or default_origin
            destination = self._safe_string(route.get("destination"))

            if not destination:
                continue

            if self._looks_invalid_route_endpoint(origin):
                continue

            if self._looks_invalid_route_endpoint(destination):
                continue

            key = self._slug(f"{origin}->{destination}")

            if key in seen:
                continue

            seen.add(key)

            merged.append(
                {
                    "origin": origin,
                    "destination": destination,
                    "arrive_by": route.get("arrive_by"),
                    "depart_after": route.get("depart_after"),
                    "purpose": route.get("purpose"),
                    "destination_event_title": route.get("destination_event_title"),
                    "destination_task_title": route.get("destination_task_title"),
                }
            )

        return merged[:8]


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

Return ONLY valid JSON with this schema:
{{
  "summary": "short summary",
  "intent": "short_intent_label"
}}

Rules:
- Summarize the current request.
- Do not invent facts.
- Fixed events stay fixed.
- Flexible tasks fit around events and travel.
- Deadlines are finish-by constraints, not start times.

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