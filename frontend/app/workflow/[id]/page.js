function extractTimeParts(value) {
  if (!value || typeof value !== "string") return null;

  const normalized = value.toLowerCase();

  if (normalized.includes("after lunch")) {
    return { hour: 13, minute: 0, constraint: "after" };
  }

  if (normalized.includes("before lunch") || normalized.includes("before noon")) {
    return { hour: 12, minute: 0, constraint: "before" };
  }

  if (normalized.includes("noon")) {
    return { hour: 12, minute: 0, constraint: "at" };
  }

  const match = value.match(/(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?/i);

  if (!match) return null;

  let hour = parseInt(match[1], 10);
  const minute = parseInt(match[2] || "0", 10);
  const meridiem = match[3]?.toUpperCase();

  if (meridiem === "PM" && hour < 12) hour += 12;
  if (meridiem === "AM" && hour === 12) hour = 0;

  if (!meridiem && hour >= 1 && hour <= 7) {
    hour += 12;
  }

  let constraint = "at";

  if (
    normalized.includes("before") ||
    normalized.includes("by ") ||
    normalized.startsWith("by ")
  ) {
    constraint = "before";
  } else if (normalized.includes("after")) {
    constraint = "after";
  }

  return { hour, minute, constraint };
}

function toMinutes(parts) {
  if (!parts) return null;
  return parts.hour * 60 + parts.minute;
}

function parseTimeToMinutes(value) {
  return toMinutes(extractTimeParts(value));
}

function formatMinutes(mins) {
  const safeMins = Math.max(0, Math.min(24 * 60 - 1, Math.round(mins)));
  const hour24 = Math.floor(safeMins / 60);
  const minute = safeMins % 60;
  const meridiem = hour24 >= 12 ? "PM" : "AM";

  let hour12 = hour24 % 12;
  if (hour12 === 0) hour12 = 12;

  return `${hour12}:${String(minute).padStart(2, "0")} ${meridiem}`;
}

function normalizeText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[_-]/g, " ")
    .replace(/[^a-z0-9\s:/]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function compactText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function titleCase(value) {
  return String(value || "")
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => {
      if (word.length <= 4 && word === word.toUpperCase()) return word;
      return word.charAt(0).toUpperCase() + word.slice(1);
    })
    .join(" ");
}

function canonicalPlace(value) {
  const normalized = normalizeText(value)
    .replace(/\bphilippines\b/g, "")
    .replace(/\bmetro manila\b/g, "")
    .replace(/\bprovince\b/g, "")
    .replace(/\bcity of\b/g, "")
    .replace(/\bcity\b/g, "")
    .replace(/\bbarangay\b/g, "")
    .replace(/\bbrgy\b/g, "")
    .replace(/\s+/g, " ")
    .trim();

  if (!normalized) return "";

  if (
    normalized === "home" ||
    normalized === "house" ||
    normalized.includes("my home") ||
    normalized.includes("my house") ||
    normalized.includes("going home") ||
    normalized.includes("get home") ||
    normalized.includes("be home") ||
    normalized.includes("go home")
  ) {
    return "home";
  }

  if (normalized.includes("bgc") || normalized.includes("bonifacio")) return "bgc";
  if (normalized.includes("ortigas")) return "ortigas";
  if (normalized.includes("makati")) return "makati";
  if (normalized.includes("pasig")) return "pasig";
  if (normalized.includes("quezon") || normalized === "qc") return "quezon-city";
  if (normalized.includes("alabang") || normalized.includes("muntinlupa")) return "alabang";

  return normalized;
}

function friendlyPlaceName(value) {
  const raw = compactText(value);

  if (!raw) return "Unknown";

  const cleaned = raw
    .replace(/,\s*Philippines/gi, "")
    .replace(/,\s*Metro Manila/gi, "")
    .replace(/\s+Philippines$/gi, "")
    .replace(/\s+Metro Manila$/gi, "")
    .replace(/\s+/g, " ")
    .trim();

  if (!cleaned) return "Unknown";

  const key = canonicalPlace(cleaned);

  if (key === "bgc") return "BGC";
  if (key === "ortigas") return "Ortigas";
  if (key === "makati") return "Makati";
  if (key === "pasig") return "Pasig";
  if (key === "quezon-city") return "Quezon City";
  if (key === "alabang") return "Alabang";
  if (key === "home") return "Home";

  return titleCase(cleaned);
}

function routeDisplayTitle(route) {
  const origin = friendlyPlaceName(route.resolved_origin || route.origin);
  const destination = friendlyPlaceName(route.resolved_destination || route.destination);

  return `Travel: ${origin} → ${destination}`;
}

function textMatches(a, b) {
  const left = normalizeText(a);
  const right = normalizeText(b);

  if (!left || !right) return false;
  if (left.includes(right)) return true;
  if (right.includes(left)) return true;

  const leftWords = new Set(left.split(" ").filter((word) => word.length > 2));
  const rightWords = right.split(" ").filter((word) => word.length > 2);

  if (rightWords.length === 0) return false;

  const matchCount = rightWords.filter((word) => leftWords.has(word)).length;
  return matchCount >= Math.min(2, rightWords.length);
}

function extractLocationPhrase(value) {
  const text = compactText(value);

  if (!text) return "";

  const patterns = [
    /\b(?:location:|in|at|to|near|around)\s+([^.,;\n]+)/i,
    /\bfrom\s+([^.,;\n]+)/i,
  ];

  for (const pattern of patterns) {
    const match = text.match(pattern);

    if (!match) continue;

    let candidate = compactText(match[1]);

    candidate = candidate
      .replace(/\s+(before|after|by|then|and|with|for|to pick|to buy|to get|to attend|to meet|but|when|constraint)\b.*$/i, "")
      .replace(/\b\d{1,2}(?::\d{2})?\s*(am|pm)\b.*$/i, "")
      .trim();

    if (candidate && looksLikePlace(candidate)) {
      return candidate;
    }
  }

  return "";
}

function looksLikePlace(value) {
  const normalized = normalizeText(value);

  if (!normalized || normalized.length < 2) return false;

  const nonPlaceWords = new Set([
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
    "phone charger",
    "charger",
    "pharmacy",
    "pharmacy nearby",
    "client meeting",
    "client sync",
    "project review",
  ]);

  return !nonPlaceWords.has(normalized);
}

function taskLocationKey(task) {
  const explicit =
    task?.location ||
    task?.place ||
    task?.destination ||
    extractLocationPhrase(`${task?.title || ""} ${task?.description || ""} ${task?.due_at || ""}`);

  return canonicalPlace(explicit);
}

function eventLocationKey(event) {
  return canonicalPlace(event?.location || extractLocationPhrase(`${event?.title || ""}`));
}

function isFuzzyOnlyTime(value) {
  const normalized = normalizeText(value);
  const hasExplicitClock = /\b\d{1,2}(?::\d{2})?\s*(am|pm)\b/i.test(String(value || ""));

  if (hasExplicitClock) return false;

  return (
    normalized.includes("after") ||
    normalized.includes("before") ||
    normalized.includes("heading") ||
    normalized.includes("going home") ||
    normalized.includes("sometime")
  );
}

function isDisplayEvent(event) {
  const start = parseTimeToMinutes(event?.start_at);

  if (start === null) return false;
  if (isFuzzyOnlyTime(event?.start_at)) return false;

  const title = normalizeText(event?.title);

  const taskLikeWords = [
    "buy ",
    "purchase ",
    "pickup",
    "pick up",
    "drop off",
    "dropoff",
    "errand",
    "collect ",
    "get documents",
    "get groceries",
    "stop by",
  ];

  return !taskLikeWords.some((word) => title.includes(word));
}

function isBadFallbackTask(task, rawRequest) {
  const title = normalizeText(task?.title);
  const requestStart = normalizeText(String(rawRequest || "").slice(0, 120));

  if (!title) return true;

  return (
    title.length > 90 &&
    requestStart.length > 20 &&
    requestStart.includes(title.slice(0, 55))
  );
}

function taskCore(value) {
  return normalizeText(value)
    .replace(/\b(a|an|the|my|some)\b/g, " ")
    .replace(/\b(in|at|near|around|from|to|location)\b\s+.+$/g, "")
    .replace(/\b(before|after|by|when|constraint)\b\s+.+$/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function taskKey(task) {
  const title = normalizeText(task?.title);
  const core = taskCore(title);
  const location = taskLocationKey(task);
  return `${core}-${location}`.replace(/-+$/g, "");
}

function eventKey(event) {
  return `${normalizeText(event?.title)}-${normalizeText(event?.start_at)}-${normalizeText(event?.location)}`;
}

function isTaskDuplicateOfEvent(task, events) {
  const taskTextValue = `${task?.title || ""} ${task?.description || ""}`;
  const normalizedTask = normalizeText(taskTextValue);

  if (!normalizedTask) return false;

  const explicitEventWrapper =
    normalizedTask.includes("attend ") ||
    normalizedTask.includes("join ") ||
    normalizedTask.includes("go to meeting") ||
    normalizedTask.includes("go to review") ||
    normalizedTask.includes("go to sync") ||
    normalizedTask.includes("prepare for") ||
    normalizedTask.includes("prep for");

  if (!explicitEventWrapper) return false;

  return (events || []).some((event) => {
    const eventText = `${event?.title || ""} ${event?.location || ""}`;
    const normalizedEvent = normalizeText(eventText);

    if (!normalizedEvent) return false;

    if (
      (normalizedTask.includes("prep") || normalizedTask.includes("prepare")) &&
      (normalizedEvent.includes("prep") || normalizedEvent.includes("prepare"))
    ) {
      return true;
    }

    return textMatches(normalizedTask, normalizedEvent);
  });
}

function getDisplayTasks(tasks, events, rawRequest) {
  const cleaned = (tasks || []).filter((task) => !isBadFallbackTask(task, rawRequest));
  const map = new Map();

  for (const task of cleaned) {
    if (isTaskDuplicateOfEvent(task, events)) continue;

    const key = taskKey(task);
    const noLocationKey = taskCore(task?.title);

    if (!key && !noLocationKey) continue;

    const existingExact = map.get(key);
    const existingCore = Array.from(map.values()).find(
      (existing) => taskCore(existing?.title) === noLocationKey
    );

    if (existingExact) {
      map.set(key, {
        ...existingExact,
        description: existingExact.description || task.description,
        due_at: existingExact.due_at || task.due_at,
        priority: existingExact.priority || task.priority,
        status: existingExact.status || task.status,
        source_agent: existingExact.source_agent || task.source_agent,
      });
      continue;
    }

    if (existingCore) {
      const existingCoreKey = taskKey(existingCore);
      map.set(existingCoreKey, {
        ...existingCore,
        description: existingCore.description || task.description,
        due_at: existingCore.due_at || task.due_at,
        priority: existingCore.priority || task.priority,
        status: existingCore.status || task.status,
        source_agent: existingCore.source_agent || task.source_agent,
      });
      continue;
    }

    map.set(key || noLocationKey, task);
  }

  return Array.from(map.values());
}

function routeScore(route) {
  let score = 0;

  if (route.maps_api_status === "ok") score += 20;
  if (route.encoded_polyline) score += 20;
  if (route.estimated_minutes) score += 10;
  if (route.arrive_by) score += 8;
  if (route.depart_after) score += 5;
  if (route.purpose) score += 3;
  if (route.destination_event_title) score += 3;
  if (route.destination_task_title) score += 3;

  return score;
}

function getUniqueTravelEstimates(travelEstimates) {
  const map = new Map();

  for (const [index, route] of (travelEstimates || []).entries()) {
    const originKey = canonicalPlace(route.resolved_origin || route.origin);
    const destinationKey = canonicalPlace(route.resolved_destination || route.destination);

    if (!originKey || !destinationKey) continue;
    if (originKey === destinationKey) continue;

    const key = `${originKey}->${destinationKey}`;
    const candidate = {
      ...route,
      __originalIndex: index,
      __routeKey: key,
      __originKey: originKey,
      __destinationKey: destinationKey,
    };

    const existing = map.get(key);

    if (!existing || routeScore(candidate) > routeScore(existing)) {
      map.set(key, candidate);
    }
  }

  return Array.from(map.values()).sort((a, b) => {
    const aSeq = Number.isFinite(Number(a.sequence_index))
      ? Number(a.sequence_index)
      : 999;
    const bSeq = Number.isFinite(Number(b.sequence_index))
      ? Number(b.sequence_index)
      : 999;

    if (aSeq !== bSeq) return aSeq - bSeq;
    return a.__originalIndex - b.__originalIndex;
  });
}

function makeBlock({
  type,
  title,
  meta,
  start,
  end,
  location = "",
  route = null,
  task = null,
  event = null,
  conflict = false,
}) {
  return {
    type,
    title,
    meta,
    start,
    end,
    location,
    route,
    task,
    event,
    conflict,
    lane: 0,
    laneCount: 1,
  };
}

function durationForRoute(route, fallback = 35) {
  const raw = Number(route?.estimated_minutes || fallback);

  if (!Number.isFinite(raw)) return fallback;

  return Math.max(25, Math.round(raw));
}

function buildRouteMeta(route, duration) {
  return `${duration} min by car · ${
    route.distance_km
      ? `${route.distance_km} km`
      : route.mode || "driving"
  }`;
}

function overlaps(aStart, aEnd, bStart, bEnd) {
  return aStart < bEnd && aEnd > bStart;
}

function blockPriority(block) {
  if (block.type === "event") return 1;
  if (block.type === "task") return 2;
  if (block.type === "route") return 3;
  return 4;
}

function routeWindow(route) {
  const routeText = normalizeText(
    `${route?.depart_after || ""} ${route?.arrive_by || ""} ${route?.purpose || ""}`
  );

  let earliest = 8 * 60 + 30;
  let latest = null;

  if (routeText.includes("after lunch")) {
    earliest = Math.max(earliest, 13 * 60);
  }

  if (routeText.includes("before noon") || routeText.includes("before lunch")) {
    latest = 12 * 60;
  }

  const departParts = extractTimeParts(route?.depart_after);
  const arriveParts = extractTimeParts(route?.arrive_by);

  if (departParts && (departParts.constraint === "after" || departParts.constraint === "at")) {
    earliest = Math.max(earliest, toMinutes(departParts));
  }

  if (arriveParts && (arriveParts.constraint === "before" || arriveParts.constraint === "at")) {
    latest = toMinutes(arriveParts);
  }

  return { earliest, latest };
}

function taskWindow(task, rawRequest = "") {
  const taskText = normalizeText(`${task?.title || ""} ${task?.description || ""} ${task?.due_at || ""}`);
  const requestText = normalizeText(rawRequest);

  if (taskText.includes("before heading")) {
    return { earliest: 8 * 60 + 30, latest: 13 * 60, rank: 8 };
  }

  if (taskText.includes("before noon") || taskText.includes("before lunch")) {
    return { earliest: 8 * 60 + 30, latest: 12 * 60, rank: 10 };
  }

  if (taskText.includes("morning")) {
    return { earliest: 8 * 60 + 30, latest: 12 * 60, rank: 15 };
  }

  const dueParts = extractTimeParts(task?.due_at);

  if (dueParts && (dueParts.constraint === "before" || dueParts.constraint === "at")) {
    return { earliest: 8 * 60 + 30, latest: toMinutes(dueParts), rank: 20 };
  }

  if (taskText.includes("after lunch")) {
    return { earliest: 13 * 60, latest: null, rank: 30 };
  }

  if (
    taskText.includes("after previous fixed event") ||
    taskText.includes("after previous activity") ||
    taskText.includes("after fixed event") ||
    taskText.includes("after the") ||
    taskText.includes("after meeting") ||
    taskText.includes("after review") ||
    taskText.includes("after sync") ||
    taskText.includes("after presentation")
  ) {
    return { earliest: 11 * 60 + 15, latest: null, rank: 35 };
  }

  if (dueParts && dueParts.constraint === "after") {
    return { earliest: toMinutes(dueParts), latest: null, rank: 40 };
  }

  if (taskText.includes("afternoon")) {
    return { earliest: 13 * 60, latest: null, rank: 45 };
  }

  if (taskText.includes("before going home") || taskText.includes("going home")) {
    const homeDeadline = parseTimeToMinutes(task?.due_at) || parseTimeToMinutes(rawRequest);
    return { earliest: 13 * 60, latest: homeDeadline, rank: 60 };
  }

  if (requestText.includes("after lunch") && !requestText.includes("before lunch")) {
    return { earliest: 13 * 60, latest: null, rank: 70 };
  }

  return { earliest: 8 * 60 + 30, latest: null, rank: 80 };
}

function findEarliestSlot({
  earliest,
  duration,
  blocks,
  latest = null,
  buffer = 20,
}) {
  let candidateStart = Math.max(8 * 60, earliest);
  const sortedBlocks = [...blocks].sort((a, b) => a.start - b.start);

  let changed = true;

  while (changed) {
    changed = false;

    for (const block of sortedBlocks) {
      const paddedStart = block.start - buffer;
      const paddedEnd = block.end + buffer;

      if (overlaps(candidateStart, candidateStart + duration, paddedStart, paddedEnd)) {
        candidateStart = paddedEnd;
        changed = true;
        break;
      }
    }
  }

  const candidateEnd = candidateStart + duration;

  return {
    start: candidateStart,
    end: candidateEnd,
    conflict: latest !== null && candidateEnd > latest,
  };
}

function findLatestSlotBefore({
  latest,
  duration,
  blocks,
  earliest = 8 * 60,
  buffer = 20,
}) {
  let candidateEnd = latest;
  let candidateStart = candidateEnd - duration;
  const sortedBlocks = [...blocks].sort((a, b) => b.start - a.start);

  let changed = true;

  while (changed) {
    changed = false;

    for (const block of sortedBlocks) {
      const paddedStart = block.start - buffer;
      const paddedEnd = block.end + buffer;

      if (overlaps(candidateStart, candidateEnd, paddedStart, paddedEnd)) {
        candidateEnd = paddedStart;
        candidateStart = candidateEnd - duration;
        changed = true;
        break;
      }
    }
  }

  return {
    start: Math.max(earliest, candidateStart),
    end: Math.max(earliest + duration, candidateEnd),
    conflict: candidateStart < earliest,
  };
}

function routeMatchesTask(route, task) {
  const taskTitle = normalizeText(task?.title);
  const taskText = normalizeText(`${task?.title || ""} ${task?.description || ""}`);
  const destinationTaskTitle = normalizeText(route?.destination_task_title);
  const purpose = normalizeText(route?.purpose);
  const routeDestination = route?.__destinationKey || canonicalPlace(route?.resolved_destination || route?.destination);
  const taskPlace = taskLocationKey(task);

  if (destinationTaskTitle && taskTitle && textMatches(destinationTaskTitle, taskTitle)) return true;
  if (purpose && taskText && textMatches(purpose, taskText)) return true;
  if (routeDestination && taskPlace && routeDestination === taskPlace) return true;

  return false;
}

function routeMatchesEvent(route, event) {
  const eventTitle = normalizeText(event?.title);
  const destinationEventTitle = normalizeText(route?.destination_event_title);
  const routeDestination = route?.__destinationKey || canonicalPlace(route?.resolved_destination || route?.destination);
  const eventPlace = eventLocationKey(event);

  if (destinationEventTitle && eventTitle && textMatches(destinationEventTitle, eventTitle)) return true;
  if (routeDestination && eventPlace && routeDestination === eventPlace) return true;

  return false;
}

function buildFixedEventBlocks(events) {
  return (events || [])
    .map((event) => {
      const start = parseTimeToMinutes(event.start_at);
      const parsedEnd = parseTimeToMinutes(event.end_at);

      if (start === null) return null;

      const end = parsedEnd && parsedEnd > start ? parsedEnd : start + 60;

      return makeBlock({
        type: "event",
        title: event.title,
        meta: event.location || event.source_agent || "Event",
        start,
        end,
        location: event.location || "",
        event,
      });
    })
    .filter(Boolean)
    .sort((a, b) => a.start - b.start);
}

function findEventBlockForRoute(route, eventBlocks) {
  const destination = route.__destinationKey || canonicalPlace(route.resolved_destination || route.destination);

  const matches = (eventBlocks || []).filter((block) => {
    if (!block.event) return false;
    if (routeMatchesEvent(route, block.event)) return true;
    return eventLocationKey(block.event) === destination;
  });

  if (matches.length === 0) return null;

  return matches.sort((a, b) => a.start - b.start)[0];
}

function sameLocationEventClusterEnd(targetBlock, eventBlocks) {
  if (!targetBlock) return null;

  const location = eventLocationKey(targetBlock.event);
  let clusterEnd = targetBlock.end;

  const related = (eventBlocks || [])
    .filter((block) => eventLocationKey(block.event) === location)
    .sort((a, b) => a.start - b.start);

  for (const block of related) {
    if (block.start >= targetBlock.start - 90 && block.start <= clusterEnd + 20) {
      clusterEnd = Math.max(clusterEnd, block.end);
    }
  }

  return clusterEnd;
}

function findTaskForRoute(route, tasks, usedTaskKeys) {
  return (tasks || []).find((task) => {
    const key = taskKey(task);

    if (!key || usedTaskKeys.has(key)) return false;

    return routeMatchesTask(route, task);
  });
}

function findOriginLocalTasks(route, tasks, usedTaskKeys) {
  const origin = route.__originKey || canonicalPlace(route.resolved_origin || route.origin);

  if (!origin) return [];

  return (tasks || []).filter((task) => {
    const key = taskKey(task);
    const taskPlace = taskLocationKey(task);

    if (!key || usedTaskKeys.has(key)) return false;
    if (!taskPlace || taskPlace !== origin) return false;
    if (routeMatchesTask(route, task)) return false;

    return true;
  });
}

function isReturnRoute(route) {
  const text = normalizeText(`${route?.purpose || ""} ${route?.destination || ""} ${route?.resolved_destination || ""}`);
  return (
    text.includes("return") ||
    text.includes("home") ||
    text.includes("after completing") ||
    Boolean(route?.arrive_by && !route?.destination_task_title && !route?.destination_event_title)
  );
}

function makeTaskBlock(task, start, end, conflict = false) {
  return makeBlock({
    type: "task",
    title: task.title,
    meta: `${task.priority || "medium"} priority · ${
      task.source_agent || "TaskAgent"
    }`,
    start,
    end,
    task,
    conflict,
  });
}

function scheduleTask({
  task,
  rawRequest,
  blocks,
  currentTime,
  earliestOverride = null,
  ignoreCurrentTimeForDeadline = false,
}) {
  const duration = 45;
  const window = taskWindow(task, rawRequest);
  const baseCurrentTime = ignoreCurrentTimeForDeadline && window.latest !== null
    ? window.earliest - 20
    : currentTime;
  const earliest = Math.max(baseCurrentTime + 20, window.earliest, earliestOverride ?? 0);

  const placed = findEarliestSlot({
    earliest,
    duration,
    blocks,
    latest: window.latest,
    buffer: 20,
  });

  return makeTaskBlock(task, placed.start, placed.end, placed.conflict);
}

function scheduleRouteOnly({
  route,
  blocks,
  currentTime,
  eventBlocks,
  targetEventBlock = null,
}) {
  const duration = durationForRoute(route, 35);
  const window = routeWindow(route);

  if (targetEventBlock) {
    const arriveBy = parseTimeToMinutes(route.arrive_by);
    const latest = arriveBy !== null
      ? arriveBy - 10
      : targetEventBlock.start - 20;

    const placed = findLatestSlotBefore({
      latest,
      duration,
      blocks,
      earliest: 8 * 60,
      buffer: 15,
    });

    const block = makeBlock({
      type: "route",
      title: routeDisplayTitle(route),
      meta: buildRouteMeta(route, duration),
      start: placed.start,
      end: placed.end,
      location: route.resolved_destination || route.destination || "",
      route,
      conflict: placed.conflict,
    });

    const clusterEnd = sameLocationEventClusterEnd(targetEventBlock, eventBlocks) ?? targetEventBlock.end;

    return {
      block,
      nextTime: Math.max(currentTime, clusterEnd),
    };
  }

  const placed = findEarliestSlot({
    earliest: Math.max(currentTime + 20, window.earliest),
    duration,
    blocks,
    latest: window.latest,
    buffer: 20,
  });

  const block = makeBlock({
    type: "route",
    title: routeDisplayTitle(route),
    meta: buildRouteMeta(route, duration),
    start: placed.start,
    end: placed.end,
    location: route.resolved_destination || route.destination || "",
    route,
    conflict: placed.conflict,
  });

  return {
    block,
    nextTime: block.end,
  };
}

function scheduleRouteAndTaskPackage({
  route,
  task,
  rawRequest,
  blocks,
  currentTime,
}) {
  const routeDuration = durationForRoute(route, 35);
  const taskDuration = 45;
  const routeTaskBuffer = 20;
  const packageDuration = routeDuration + routeTaskBuffer + taskDuration;
  const taskTiming = taskWindow(task, rawRequest);
  const routeTiming = routeWindow(route);
  const earliest = Math.max(currentTime + 20, taskTiming.earliest, routeTiming.earliest);

  const placed = findEarliestSlot({
    earliest,
    duration: packageDuration,
    blocks,
    latest: taskTiming.latest,
    buffer: 20,
  });

  const routeStart = placed.start;
  const routeEnd = routeStart + routeDuration;
  const taskStart = routeEnd + routeTaskBuffer;
  const taskEnd = taskStart + taskDuration;

  const routeBlock = makeBlock({
    type: "route",
    title: routeDisplayTitle(route),
    meta: buildRouteMeta(route, routeDuration),
    start: routeStart,
    end: routeEnd,
    location: route.resolved_destination || route.destination || "",
    route,
    conflict: placed.conflict,
  });

  const taskBlock = makeTaskBlock(task, taskStart, taskEnd, placed.conflict);

  return {
    routeBlock,
    taskBlock,
    nextTime: taskEnd,
  };
}

function scheduleRemainingBeforeReturn({
  tasks,
  usedTaskKeys,
  rawRequest,
  blocks,
  currentTime,
}) {
  let nextTime = currentTime;

  const remaining = (tasks || [])
    .filter((task) => {
      const key = taskKey(task);
      if (!key || usedTaskKeys.has(key)) return false;
      return !taskLocationKey(task);
    })
    .sort((a, b) => {
      const aWindow = taskWindow(a, rawRequest);
      const bWindow = taskWindow(b, rawRequest);
      if (aWindow.rank !== bWindow.rank) return aWindow.rank - bWindow.rank;
      return (aWindow.latest ?? 9999) - (bWindow.latest ?? 9999);
    });

  for (const task of remaining) {
    const taskBlock = scheduleTask({
      task,
      rawRequest,
      blocks,
      currentTime: nextTime,
    });

    blocks.push(taskBlock);
    usedTaskKeys.add(taskKey(task));
    nextTime = Math.max(nextTime, taskBlock.end);
  }

  return nextTime;
}

function buildPlannerData(tasks, events, finalResponse, rawRequest = "") {
  const blocks = buildFixedEventBlocks(events);
  const routeBlocks = [];
  const eventBlocks = [...blocks];
  const usedRouteKeys = new Set();
  const usedTaskKeys = new Set();

  const uniqueTravelEstimates = getUniqueTravelEstimates(
    finalResponse?.travel_estimates || []
  ).map((route, index) => ({
    ...route,
    __uniqueKey: `${route.__routeKey || `${route.__originKey}->${route.__destinationKey}`}-${index}`,
  }));

  let currentTime = 8 * 60 + 30;

  for (const route of uniqueTravelEstimates) {
    if (usedRouteKeys.has(route.__uniqueKey)) continue;

    const localTasks = findOriginLocalTasks(route, tasks, usedTaskKeys).sort((a, b) => {
      const aWindow = taskWindow(a, rawRequest);
      const bWindow = taskWindow(b, rawRequest);
      if (aWindow.rank !== bWindow.rank) return aWindow.rank - bWindow.rank;
      return (aWindow.latest ?? 9999) - (bWindow.latest ?? 9999);
    });

    for (const localTask of localTasks) {
      const taskBlock = scheduleTask({
        task: localTask,
        rawRequest,
        blocks,
        currentTime,
        ignoreCurrentTimeForDeadline: true,
      });
      blocks.push(taskBlock);
      usedTaskKeys.add(taskKey(localTask));
      currentTime = Math.max(currentTime, taskBlock.end);
    }

    if (isReturnRoute(route)) {
      currentTime = scheduleRemainingBeforeReturn({
        tasks,
        usedTaskKeys,
        rawRequest,
        blocks,
        currentTime,
      });
    }

    const targetEventBlock = findEventBlockForRoute(route, eventBlocks);
    const targetTask = findTaskForRoute(route, tasks, usedTaskKeys);

    if (targetTask && !targetEventBlock) {
      const scheduledPackage = scheduleRouteAndTaskPackage({
        route,
        task: targetTask,
        rawRequest,
        blocks,
        currentTime,
      });

      blocks.push(scheduledPackage.routeBlock);
      blocks.push(scheduledPackage.taskBlock);
      routeBlocks.push(scheduledPackage.routeBlock);
      usedRouteKeys.add(route.__uniqueKey);
      usedTaskKeys.add(taskKey(targetTask));
      currentTime = Math.max(currentTime, scheduledPackage.nextTime);
      continue;
    }

    const scheduledRoute = scheduleRouteOnly({
      route,
      blocks,
      currentTime,
      eventBlocks,
      targetEventBlock,
    });

    blocks.push(scheduledRoute.block);
    routeBlocks.push(scheduledRoute.block);
    usedRouteKeys.add(route.__uniqueKey);

    currentTime = Math.max(currentTime, scheduledRoute.nextTime);

    if (targetTask) {
      const taskBlock = scheduleTask({
        task: targetTask,
        rawRequest,
        blocks,
        currentTime: scheduledRoute.block.end,
        earliestOverride: scheduledRoute.block.end + 20,
      });

      blocks.push(taskBlock);
      usedTaskKeys.add(taskKey(targetTask));
      currentTime = Math.max(currentTime, taskBlock.end);
    }
  }

  const sortedTasks = [...(tasks || [])].sort((a, b) => {
    const aWindow = taskWindow(a, rawRequest);
    const bWindow = taskWindow(b, rawRequest);

    if (aWindow.rank !== bWindow.rank) return aWindow.rank - bWindow.rank;

    const aLatest = aWindow.latest ?? 9999;
    const bLatest = bWindow.latest ?? 9999;

    return aLatest - bLatest;
  });

  for (const task of sortedTasks) {
    const key = taskKey(task);

    if (!key || usedTaskKeys.has(key)) continue;

    const taskBlock = scheduleTask({
      task,
      rawRequest,
      blocks,
      currentTime,
      ignoreCurrentTimeForDeadline: true,
    });

    blocks.push(taskBlock);
    usedTaskKeys.add(key);
    currentTime = Math.max(currentTime, taskBlock.end);
  }

  const dayPlan = assignCalendarLanes(
    blocks
      .filter((block) => block.end > block.start)
      .sort((a, b) => {
        if (a.start !== b.start) return a.start - b.start;
        return blockPriority(a) - blockPriority(b);
      })
  );

  const scheduledRoutes = routeBlocks
    .map((block) => ({
      ...block.route,
      __scheduledStart: block.start,
      __scheduledEnd: block.end,
      __conflict: block.conflict,
      __displayTitle: block.title,
    }))
    .sort((a, b) => {
      if (a.__scheduledStart !== b.__scheduledStart) {
        return a.__scheduledStart - b.__scheduledStart;
      }

      return (a.sequence_index || 0) - (b.sequence_index || 0);
    });

  return {
    dayPlan,
    scheduledRoutes,
  };
}

function assignCalendarLanes(blocks) {
  const sorted = [...blocks].sort((a, b) => {
    if (a.start !== b.start) return a.start - b.start;
    return blockPriority(a) - blockPriority(b);
  });

  const clusters = [];

  for (const block of sorted) {
    const lastCluster = clusters[clusters.length - 1];

    if (!lastCluster) {
      clusters.push({
        start: block.start,
        end: block.end,
        blocks: [block],
      });
      continue;
    }

    if (block.start < lastCluster.end) {
      lastCluster.blocks.push(block);
      lastCluster.end = Math.max(lastCluster.end, block.end);
    } else {
      clusters.push({
        start: block.start,
        end: block.end,
        blocks: [block],
      });
    }
  }

  for (const cluster of clusters) {
    const laneEnds = [];

    for (const block of cluster.blocks) {
      let lane = 0;

      while (lane < laneEnds.length && block.start < laneEnds[lane]) {
        lane += 1;
      }

      block.lane = lane;
      laneEnds[lane] = block.end;
    }

    const laneCount = Math.max(1, laneEnds.length);

    for (const block of cluster.blocks) {
      block.laneCount = laneCount;
    }
  }

  return sorted;
}

function calendarBlockStyle(block) {
  const dayStart = 8 * 60;
  const step = 5;
  const rowStart = Math.max(1, Math.floor((block.start - dayStart) / step) + 1);
  const naturalRowEnd = Math.ceil((block.end - dayStart) / step) + 1;
  const rowEnd = Math.max(rowStart + 6, naturalRowEnd);

  const laneCount = Math.max(1, block.laneCount || 1);
  const lane = Math.max(0, block.lane || 0);

  return {
    gridRow: `${rowStart} / ${rowEnd}`,
    gridColumn: laneCount > 1 ? `${lane + 1} / span 1` : "1 / -1",
  };
}

function calendarGridStyle(dayPlan) {
  const maxLaneCount = Math.max(1, ...dayPlan.map((block) => block.laneCount || 1));

  return {
    gridTemplateColumns: `repeat(${maxLaneCount}, minmax(240px, 1fr))`,
  };
}

async function getWorkflow(id) {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL;

  if (!base) {
    return { error: "NEXT_PUBLIC_API_BASE_URL is not set." };
  }

  try {
    const res = await fetch(`${base}/workflow/${id}`, {
      cache: "no-store",
    });

    const data = await res.json();

    if (!res.ok) {
      return { error: data?.detail || JSON.stringify(data) };
    }

    return { data, base };
  } catch (error) {
    return { error: String(error) };
  }
}

function jsonPretty(value) {
  return JSON.stringify(value, null, 2);
}

function routeMapSrc(base, workflowId, route) {
  return `${base}/workflow/${workflowId}/route-map/${route.__originalIndex}?width=640&height=420`;
}

function displayDistance(route) {
  if (route.distance_km) return `${route.distance_km} km`;
  if (route.distance_meters) return `${Math.round(route.distance_meters / 1000)} km`;
  return "Distance unavailable";
}

function displayRouteStatus(status) {
  if (!status) return "Unknown";
  if (status === "ok") return "Live route";
  return status.replaceAll("_", " ");
}

export default async function WorkflowDetailPage({ params }) {
  const { id } = await params;
  const result = await getWorkflow(id);

  if (result.error) {
    return (
      <main className="shell">
        <div className="top-nav">
          <a className="button button-secondary" href="/">
            ← Home
          </a>
        </div>

        <section className="hero-card">
          <div className="badge-row">
            <span className="badge">Workflow #{id}</span>
          </div>

          <h1 className="hero-title">Workflow failed</h1>
          <p className="hero-subtitle">{result.error}</p>
        </section>
      </main>
    );
  }

  const { workflow, tasks, events, notes, tool_logs } = result.data;
  const finalResponse = workflow?.final_response || {};
  const displayEvents = (events || []).filter(isDisplayEvent);
  const displayTasks = getDisplayTasks(tasks, displayEvents, workflow.raw_request);
  const plannerData = buildPlannerData(displayTasks, displayEvents, finalResponse, workflow.raw_request);
  const dayPlan = plannerData.dayPlan;
  const orderedTravelEstimates = plannerData.scheduledRoutes;
  const base = result.base;

  return (
    <main className="shell">
      <div className="top-nav">
        <a className="button button-secondary" href="/">
          ← Home
        </a>
      </div>

      <section className="hero-card">
        <div className="badge-row">
          <span className="badge badge-strong">DayWeaver</span>
          <span className="badge">Workflow #{workflow.id}</span>
          <span className={`status-pill ${workflow.status}`}>{workflow.status}</span>
        </div>

        <h1 className="hero-title">{workflow.parsed_intent || "Workflow"}</h1>
        <p className="hero-subtitle">{workflow.raw_request}</p>
      </section>

      <section className="full-stack">
        <div className="card main-card">
          <div className="card-heading-row">
            <div>
              <h2 className="card-title">Tasks</h2>
              <p className="card-subtitle">
                Action items after removing duplicates that are already represented as fixed schedule blocks.
              </p>
            </div>
            <span className="count-pill">{displayTasks.length}</span>
          </div>

          {displayTasks.length === 0 ? (
            <div className="empty">No standalone tasks.</div>
          ) : (
            <div className="responsive-card-grid">
              {displayTasks.map((task) => (
                <div className="item item-soft" key={task.id || taskKey(task)}>
                  <div className="item-title">{task.title}</div>
                  <div className="small">{task.description || "No description"}</div>
                  <div className="item-meta">
                    <span className="pill">{task.priority}</span>
                    <span className="pill">{task.status}</span>
                    <span className="pill pill-blue">{task.source_agent}</span>
                    {task.due_at ? <span className="pill">Due: {task.due_at}</span> : null}
                    {task.inferred ? <span className="pill pill-accent">Recovered</span> : null}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card main-card">
          <div className="card-heading-row">
            <div>
              <h2 className="card-title">Events</h2>
              <p className="card-subtitle">
                Fixed schedule blocks only. Loose errands are kept as tasks.
              </p>
            </div>
            <span className="count-pill">{displayEvents.length}</span>
          </div>

          {displayEvents.length === 0 ? (
            <div className="empty">No fixed events.</div>
          ) : (
            <div className="responsive-card-grid">
              {displayEvents.map((event) => (
                <div className="item item-soft" key={event.id || eventKey(event)}>
                  <div className="item-title">{event.title}</div>
                  <div className="small">
                    {event.start_at || "—"} → {event.end_at || "—"}
                  </div>
                  <div className="item-meta">
                    <span className="pill">{event.location || "No location"}</span>
                    <span className="pill pill-blue">{event.source_agent}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card main-card">
          <div className="card-heading-row">
            <div>
              <h2 className="card-title">Notes</h2>
              <p className="card-subtitle">Stored memory and context from this workflow.</p>
            </div>
            <span className="count-pill">{notes.length}</span>
          </div>

          {notes.length === 0 ? (
            <div className="empty">No notes.</div>
          ) : (
            <div className="responsive-card-grid">
              {notes.map((note) => (
                <div className="item item-soft" key={note.id}>
                  <div className="item-title">{note.title}</div>
                  <div className="small">{note.content}</div>
                  <div className="item-meta">
                    <span className="pill">{note.note_type || "note"}</span>
                    <span className="pill">{note.tags || "—"}</span>
                    <span className="pill pill-blue">{note.source_agent}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card main-card">
          <div className="card-heading-row">
            <div>
              <h2 className="card-title">Day planner view</h2>
              <p className="card-subtitle">
                Outlook-style calendar view. Conflicts share the same time row but use separate columns.
              </p>
            </div>
            <span className="count-pill">{dayPlan.length}</span>
          </div>

          <div className="planner-legend">
            <span className="legend-item">
              <span className="legend-dot legend-task"></span>
              Task
            </span>
            <span className="legend-item">
              <span className="legend-dot legend-event"></span>
              Event
            </span>
            <span className="legend-item">
              <span className="legend-dot legend-route"></span>
              Travel
            </span>
            <span className="legend-item">
              <span className="legend-dot legend-conflict"></span>
              Potential conflict
            </span>
          </div>

          <div className="outlook-planner">
            <div className="outlook-time-column">
              {Array.from({ length: 13 }).map((_, index) => {
                const hour = 8 + index;
                const label =
                  hour > 12
                    ? `${hour - 12}:00 PM`
                    : hour === 12
                      ? "12:00 PM"
                      : `${hour}:00 AM`;

                return (
                  <div className="outlook-hour" key={label}>
                    {label}
                  </div>
                );
              })}
            </div>

            <div className="outlook-calendar-area">
              <div className="outlook-calendar-grid" style={calendarGridStyle(dayPlan)}>
                {dayPlan.map((block, index) => (
                  <div
                    className={`calendar-block ${block.type} ${
                      block.conflict ? "conflict" : ""
                    }`}
                    style={calendarBlockStyle(block)}
                    key={`${block.type}-${index}-${block.title}`}
                  >
                    <div className="calendar-block-kind">
                      {block.type === "route"
                        ? "Travel"
                        : block.type === "event"
                          ? "Event"
                          : "Task"}
                    </div>
                    <div className="calendar-block-title">{block.title}</div>
                    <div className="calendar-block-time">
                      {formatMinutes(block.start)} – {formatMinutes(block.end)}
                    </div>
                    <div className="calendar-block-meta">{block.meta}</div>
                    {block.conflict ? (
                      <div className="day-block-warning">Potential conflict</div>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="helper-note">
            Planned sequence uses transition buffers when possible: task, buffer, travel, buffer, fixed event, next task.
          </div>
        </div>

        <div className="card main-card">
          <div className="card-heading-row">
            <div>
              <h2 className="card-title">Route map</h2>
              <p className="card-subtitle">
                Driving routes generated through the backend Maps integration. Ordered chronologically by planner placement.
              </p>
            </div>
            <span className="count-pill">{orderedTravelEstimates.length}</span>
          </div>

          {orderedTravelEstimates.length === 0 ? (
            <div className="empty">
              No travel estimates for this workflow. Re-run the workflow after deploying the route fix.
            </div>
          ) : (
            <div className="route-map-list">
              {orderedTravelEstimates.map((item) => (
                <div className="route-card" key={`${item.__routeKey}-${item.__originalIndex}`}>
                  <div className="route-card-header">
                    <div>
                      <div className="route-title">
                        {item.__displayTitle || routeDisplayTitle(item)}
                      </div>
                      <div className="route-subtitle">
                        Scheduled: {formatMinutes(item.__scheduledStart)} – {formatMinutes(item.__scheduledEnd)}
                      </div>
                      <div className="route-subtitle">
                        Source: {item.resolved_origin || item.origin}
                      </div>
                      <div className="route-subtitle">
                        Destination: {item.resolved_destination || item.destination}
                      </div>
                      {item.arrive_by ? (
                        <div className="route-subtitle">Arrive by: {item.arrive_by}</div>
                      ) : null}
                      {item.depart_after ? (
                        <div className="route-subtitle">Depart after: {item.depart_after}</div>
                      ) : null}
                      {item.purpose ? (
                        <div className="route-subtitle">Purpose: {item.purpose}</div>
                      ) : null}
                    </div>

                    <span
                      className={
                        item.maps_api_status === "ok"
                          ? "pill pill-accent"
                          : "pill"
                      }
                    >
                      {displayRouteStatus(item.maps_api_status)}
                    </span>
                  </div>

                  <div className="route-metrics">
                    <div className="route-metric route-metric-primary">
                      <div className="route-metric-label">Current driving time by car</div>
                      <div className="route-metric-value">
                        {item.estimated_minutes ? `${item.estimated_minutes} min` : "Unavailable"}
                      </div>
                    </div>

                    <div className="route-metric">
                      <div className="route-metric-label">Distance</div>
                      <div className="route-metric-value">{displayDistance(item)}</div>
                    </div>

                    <div className="route-metric">
                      <div className="route-metric-label">Mode</div>
                      <div className="route-metric-value">{item.mode || "Driving"}</div>
                    </div>
                  </div>

                  {item.maps_api_status === "ok" ? (
                    <img
                      className="route-map-image"
                      src={routeMapSrc(base, workflow.id, item)}
                      alt={`Route map from ${item.origin} to ${item.destination}`}
                    />
                  ) : (
                    <div className="map-placeholder">
                      <div className="item-title">Map unavailable</div>
                      <div className="small">
                        {item.note || "No route map was returned."}
                      </div>
                    </div>
                  )}

                  <div className="route-actions">
                    {item.google_maps_url ? (
                      <a
                        className="button button-secondary button-small"
                        href={item.google_maps_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open in Google Maps
                      </a>
                    ) : null}

                    <span className="small">
                      Source: {item.source || "RouteAgent"}
                    </span>
                  </div>

                  {item.note ? <div className="helper-note route-note">{item.note}</div> : null}
                </div>
              ))}
            </div>
          )}
        </div>

        <details className="details-card">
          <summary>
            <span>Metadata</span>
            <span className="summary-hint">Workflow timing and stored state</span>
          </summary>

          <div className="details-content">
            <div className="metadata-grid">
              <div className="kpi">
                <div className="kpi-label">Status</div>
                <div className={`kpi-value status-text ${workflow.status}`}>
                  {workflow.status}
                </div>
              </div>

              <div className="kpi">
                <div className="kpi-label">Started</div>
                <div className="small">{workflow.started_at || "—"}</div>
              </div>

              <div className="kpi">
                <div className="kpi-label">Completed</div>
                <div className="small">{workflow.completed_at || "—"}</div>
              </div>

              <div className="kpi">
                <div className="kpi-label">Saved note</div>
                <div className="small">{finalResponse.note_saved?.title || "—"}</div>
              </div>
            </div>

            <div className="agent-row">
              {(workflow.agents_used || []).map((agent) => (
                <span className="pill pill-blue" key={agent}>
                  {agent}
                </span>
              ))}
            </div>
          </div>
        </details>

        <details className="details-card">
          <summary>
            <span>Execution summary</span>
            <span className="summary-hint">Intent, summary, and final structured output</span>
          </summary>

          <div className="details-content">
            <div className="summary-panel">
              <div className="item-title">Intent</div>
              <div className="small">{workflow.parsed_intent || "—"}</div>
            </div>

            <div className="summary-panel">
              <div className="item-title">Summary</div>
              <div className="small">{finalResponse.summary || "—"}</div>
            </div>

            <pre className="codebox">{jsonPretty(finalResponse)}</pre>
          </div>
        </details>

        <details className="details-card">
          <summary>
            <span>Tool trace</span>
            <span className="summary-hint">Normally hidden agent/tool logs</span>
          </summary>

          <div className="details-content">
            {tool_logs.length === 0 ? (
              <div className="empty">No tool logs.</div>
            ) : (
              <div className="timeline">
                {tool_logs.map((log) => (
                  <div className="timeline-item" key={log.id}>
                    <div className="timeline-header">
                      <div>
                        <div className="item-title">{log.tool_name}</div>
                        <div className="small">
                          {log.agent_name} · {log.created_at}
                        </div>
                      </div>
                    </div>

                    <pre className="codebox">{jsonPretty(log.output_json)}</pre>
                  </div>
                ))}
              </div>
            )}
          </div>
        </details>
      </section>
    </main>
  );
}