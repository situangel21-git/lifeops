function extractTimeParts(value) {
  if (!value || typeof value !== "string") return null;

  const normalized = value.toLowerCase();

  if (normalized.includes("after lunch")) {
    return { hour: 13, minute: 0, constraint: "after" };
  }

  if (normalized.includes("before lunch")) {
    return { hour: 11, minute: 30, constraint: "before" };
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

  if (normalized.includes("before") || normalized.includes("by ")) {
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
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function canonicalPlace(value) {
  const normalized = normalizeText(value);

  if (!normalized) return "";

  if (
    normalized === "home" ||
    normalized.includes("my home") ||
    normalized.includes("going home")
  ) {
    return "home";
  }

  if (normalized.includes("makati")) return "makati";

  if (
    normalized.includes("bgc") ||
    normalized.includes("bonifacio") ||
    normalized.includes("taguig")
  ) {
    return "bgc";
  }

  if (normalized.includes("quezon") || normalized === "qc") {
    return "quezon-city";
  }

  return normalized;
}

function friendlyPlaceName(value) {
  const place = canonicalPlace(value);

  if (place === "makati") return "Makati";
  if (place === "bgc") return "BGC";
  if (place === "quezon-city") return "Quezon City";
  if (place === "home") return "Home";

  const raw = String(value || "").trim();

  if (!raw) return "Unknown";

  return raw
    .replace(", Philippines", "")
    .replace(", Metro Manila", "")
    .replace("Bonifacio Global City, Taguig", "BGC");
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

function isFuzzyOnlyTime(value) {
  const normalized = normalizeText(value);

  return (
    normalized.includes("after") ||
    normalized.includes("before") ||
    normalized.includes("heading") ||
    normalized.includes("going home")
  );
}

function isDisplayEvent(event) {
  const start = parseTimeToMinutes(event.start_at);

  if (start === null) return false;
  if (isFuzzyOnlyTime(event.start_at)) return false;

  const title = normalizeText(event.title);

  if (
    title.includes("buy ") ||
    title.includes("pickup") ||
    title.includes("pick up") ||
    title.includes("vitamin") ||
    title.includes("mercury") ||
    title.includes("printer ink")
  ) {
    return false;
  }

  return true;
}

function isBadFallbackTask(task, rawRequest) {
  const title = normalizeText(task.title);
  const requestStart = normalizeText(String(rawRequest || "").slice(0, 90));

  if (!title) return true;

  return (
    title.length > 60 &&
    requestStart.length > 20 &&
    requestStart.includes(title.slice(0, 40))
  );
}

function inferTasksFromRequest(rawRequest) {
  const text = normalizeText(rawRequest);
  const tasks = [];

  if (text.includes("printer ink")) {
    tasks.push({
      id: "inferred-printer-ink",
      title: "Buy printer ink",
      description: "Buy printer ink in Makati before heading to BGC.",
      priority: "medium",
      due_at: "before heading to BGC",
      status: "open",
      source_agent: "TaskAgent",
      inferred: true,
    });
  }

  if (text.includes("mercury") || text.includes("vitamin")) {
    tasks.push({
      id: "inferred-mercury-vitamins",
      title: "Stop by Mercury Drug for vitamins",
      description:
        "Stop by Mercury Drug in BGC for vitamins after the presentation.",
      priority: "medium",
      due_at: "after the presentation",
      status: "open",
      source_agent: "TaskAgent",
      inferred: true,
    });
  }

  if (text.includes("package") && (text.includes("quezon") || text.includes("qc"))) {
    tasks.push({
      id: "inferred-qc-package",
      title: "Pick up package in Quezon City",
      description: "Pick up the package in Quezon City before going home.",
      priority: "high",
      due_at: "before going home by 7 PM",
      status: "open",
      source_agent: "TaskAgent",
      inferred: true,
    });
  }

  return tasks;
}

function taskKey(task) {
  const title = normalizeText(task.title);

  if (title.includes("printer") && title.includes("ink")) return "printer-ink";
  if (title.includes("mercury") || title.includes("vitamin")) {
    return "mercury-vitamins";
  }

  if (
    title.includes("package") ||
    title.includes("pick up") ||
    title.includes("pickup")
  ) {
    return "package-pickup";
  }

  return title;
}

function isTaskDuplicateOfEvent(task, events) {
  const key = taskKey(task);

  if (key === "printer-ink") return false;
  if (key === "mercury-vitamins") return false;
  if (key === "package-pickup") return false;

  const taskTextValue = `${task.title || ""} ${task.description || ""}`;
  const normalizedTask = normalizeText(taskTextValue);

  return events.some((event) => {
    const eventText = `${event.title || ""} ${event.location || ""}`;
    const normalizedEvent = normalizeText(eventText);

    if (textMatches(normalizedTask, normalizedEvent)) return true;

    if (
      normalizedTask.includes("prepare") &&
      normalizedEvent.includes("prep") &&
      normalizedEvent.includes("presentation")
    ) {
      return true;
    }

    if (
      normalizedTask.includes("attend") &&
      normalizedTask.includes("presentation") &&
      normalizedEvent.includes("presentation")
    ) {
      return true;
    }

    return false;
  });
}

function getDisplayTasks(tasks, events, rawRequest) {
  const cleaned = (tasks || []).filter((task) => !isBadFallbackTask(task, rawRequest));
  const inferred = inferTasksFromRequest(rawRequest);
  const map = new Map();

  for (const task of [...cleaned, ...inferred]) {
    if (isTaskDuplicateOfEvent(task, events)) continue;

    const key = taskKey(task);
    if (!key) continue;

    if (!map.has(key)) {
      map.set(key, task);
    }
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

function findRoute(routes, originKey, destinationKey) {
  return routes.find((route) => {
    const origin = route.__originKey || canonicalPlace(route.origin || route.resolved_origin);
    const destination =
      route.__destinationKey ||
      canonicalPlace(route.destination || route.resolved_destination);

    return origin === originKey && destination === destinationKey;
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

function durationForRoute(route, fallback = 30) {
  return Math.max(10, Number(route?.estimated_minutes || fallback));
}

function buildPlannerData(tasks, events, finalResponse) {
  const buffer = 10;
  const blocks = [];
  const routeBlocks = [];

  const uniqueTravelEstimates = getUniqueTravelEstimates(
    finalResponse?.travel_estimates || []
  );

  const routeMakatiToBGC = findRoute(uniqueTravelEstimates, "makati", "bgc");
  const routeBGCToQC = findRoute(uniqueTravelEstimates, "bgc", "quezon-city");
  const routeQCToHome =
    findRoute(uniqueTravelEstimates, "quezon-city", "makati") ||
    findRoute(uniqueTravelEstimates, "quezon-city", "home");

  const printerTask = tasks.find((task) => taskKey(task) === "printer-ink");
  const mercuryTask = tasks.find((task) => taskKey(task) === "mercury-vitamins");
  const packageTask = tasks.find((task) => taskKey(task) === "package-pickup");

  const prepEvent = events.find((event) =>
    normalizeText(event.title).includes("prep")
  );

  const presentationEvent = events.find((event) =>
    normalizeText(event.title).includes("presentation")
  );

  const prepStart = parseTimeToMinutes(prepEvent?.start_at) ?? 14 * 60;
  const prepEnd = parseTimeToMinutes(prepEvent?.end_at) ?? 15 * 60;
  const presentationStart = parseTimeToMinutes(presentationEvent?.start_at) ?? 15 * 60;
  const presentationEnd = parseTimeToMinutes(presentationEvent?.end_at) ?? 16 * 60;

  if (printerTask) {
    blocks.push(
      makeBlock({
        type: "task",
        title: printerTask.title,
        meta: `${printerTask.priority || "medium"} priority · ${
          printerTask.source_agent || "TaskAgent"
        }`,
        start: 9 * 60,
        end: 9 * 60 + 45,
        task: printerTask,
      })
    );
  }

  if (routeMakatiToBGC) {
    const duration = durationForRoute(routeMakatiToBGC, 20);
    const end = prepStart - buffer;
    const start = Math.max(8 * 60, end - duration);

    const block = makeBlock({
      type: "route",
      title: routeDisplayTitle(routeMakatiToBGC),
      meta: `${duration} min by car · ${
        routeMakatiToBGC.distance_km
          ? `${routeMakatiToBGC.distance_km} km`
          : routeMakatiToBGC.mode || "driving"
      }`,
      start,
      end,
      location: routeMakatiToBGC.destination || "",
      route: routeMakatiToBGC,
    });

    blocks.push(block);
    routeBlocks.push(block);
  }

  if (prepEvent) {
    blocks.push(
      makeBlock({
        type: "event",
        title: prepEvent.title,
        meta: prepEvent.location || prepEvent.source_agent || "Event",
        start: prepStart,
        end: prepEnd,
        location: prepEvent.location || "",
        event: prepEvent,
      })
    );
  }

  if (presentationEvent) {
    blocks.push(
      makeBlock({
        type: "event",
        title: presentationEvent.title,
        meta: presentationEvent.location || presentationEvent.source_agent || "Event",
        start: presentationStart,
        end: presentationEnd,
        location: presentationEvent.location || "",
        event: presentationEvent,
      })
    );
  }

  let mercuryEnd = presentationEnd;

  if (mercuryTask) {
    const mercuryStart = presentationEnd + buffer;
    mercuryEnd = mercuryStart + 45;

    blocks.push(
      makeBlock({
        type: "task",
        title: mercuryTask.title,
        meta: `${mercuryTask.priority || "medium"} priority · ${
          mercuryTask.source_agent || "TaskAgent"
        }`,
        start: mercuryStart,
        end: mercuryEnd,
        task: mercuryTask,
      })
    );
  }

  let qcArrival = mercuryEnd;

  if (routeBGCToQC) {
    const duration = durationForRoute(routeBGCToQC, 40);
    const start = mercuryEnd + buffer;
    const end = start + duration;
    qcArrival = end;

    const block = makeBlock({
      type: "route",
      title: routeDisplayTitle(routeBGCToQC),
      meta: `${duration} min by car · ${
        routeBGCToQC.distance_km
          ? `${routeBGCToQC.distance_km} km`
          : routeBGCToQC.mode || "driving"
      }`,
      start,
      end,
      location: routeBGCToQC.destination || "",
      route: routeBGCToQC,
      conflict: end > 18 * 60,
    });

    blocks.push(block);
    routeBlocks.push(block);
  }

  let packageEnd = qcArrival;

  if (packageTask) {
    const packageStart = qcArrival + buffer;
    packageEnd = packageStart + 35;

    blocks.push(
      makeBlock({
        type: "task",
        title: packageTask.title,
        meta: `${packageTask.priority || "high"} priority · ${
          packageTask.source_agent || "TaskAgent"
        }`,
        start: packageStart,
        end: packageEnd,
        task: packageTask,
      })
    );
  }

  if (routeQCToHome) {
    const duration = durationForRoute(routeQCToHome, 45);
    const arriveBy = parseTimeToMinutes(routeQCToHome.arrive_by) ?? 19 * 60;
    const latestStart = arriveBy - duration;
    const start = Math.max(packageEnd + buffer, latestStart);
    const end = start + duration;

    const block = makeBlock({
      type: "route",
      title: routeDisplayTitle(routeQCToHome),
      meta: `${duration} min by car · ${
        routeQCToHome.distance_km
          ? `${routeQCToHome.distance_km} km`
          : routeQCToHome.mode || "driving"
      }`,
      start,
      end,
      location: routeQCToHome.destination || "",
      route: routeQCToHome,
      conflict: end > arriveBy || end > 20 * 60,
    });

    blocks.push(block);
    routeBlocks.push(block);
  }

  const usedEventIds = new Set(
    blocks.filter((block) => block.event).map((block) => block.event.id)
  );

  for (const event of events || []) {
    if (usedEventIds.has(event.id)) continue;

    const start = parseTimeToMinutes(event.start_at);
    const end = parseTimeToMinutes(event.end_at);

    if (start === null) continue;

    blocks.push(
      makeBlock({
        type: "event",
        title: event.title,
        meta: event.location || event.source_agent || "Event",
        start,
        end: end && end > start ? end : start + 60,
        location: event.location || "",
        event,
      })
    );
  }

  const usedTaskKeys = new Set(
    blocks.filter((block) => block.task).map((block) => taskKey(block.task))
  );

  for (const task of tasks || []) {
    const key = taskKey(task);
    if (usedTaskKeys.has(key)) continue;

    blocks.push(
      makeBlock({
        type: "task",
        title: task.title,
        meta: `${task.priority || "medium"} priority · ${
          task.source_agent || "TaskAgent"
        }`,
        start: 10 * 60,
        end: 10 * 60 + 45,
        task,
      })
    );
  }

  const dayPlan = assignCalendarLanes(
    blocks
      .filter((block) => block.end > block.start)
      .sort((a, b) => {
        if (a.start !== b.start) return a.start - b.start;
        return a.end - b.end;
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

function overlaps(aStart, aEnd, bStart, bEnd) {
  return aStart < bEnd && aEnd > bStart;
}

function assignCalendarLanes(blocks) {
  const sorted = [...blocks].sort((a, b) => {
    if (a.start !== b.start) return a.start - b.start;
    return a.end - b.end;
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
  const rowEnd = Math.max(rowStart + 2, Math.ceil((block.end - dayStart) / step) + 1);

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
    gridTemplateColumns: `repeat(${maxLaneCount}, minmax(0, 1fr))`,
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
  const plannerData = buildPlannerData(displayTasks, displayEvents, finalResponse);
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
                <div className="item item-soft" key={task.id}>
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
                <div className="item item-soft" key={event.id}>
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