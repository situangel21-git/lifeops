function extractTimeParts(value) {
  if (!value || typeof value !== "string") return null;

  const match = value.match(/(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?/i);
  if (!match) return null;

  let hour = parseInt(match[1], 10);
  const minute = parseInt(match[2] || "0", 10);
  const meridiem = match[3]?.toUpperCase();

  if (meridiem === "PM" && hour < 12) hour += 12;
  if (meridiem === "AM" && hour === 12) hour = 0;

  return { hour, minute };
}

function toMinutes(parts) {
  if (!parts) return null;
  return parts.hour * 60 + parts.minute;
}

function formatMinutes(mins) {
  const hour24 = Math.floor(mins / 60);
  const minute = mins % 60;
  const meridiem = hour24 >= 12 ? "PM" : "AM";
  let hour12 = hour24 % 12;
  if (hour12 === 0) hour12 = 12;
  return `${hour12}:${String(minute).padStart(2, "0")} ${meridiem}`;
}

function buildDayPlan(tasks, events, finalResponse) {
  const dayStart = 8 * 60;
  const dayEnd = 20 * 60;
  const blocks = [];

  for (const event of events || []) {
    const start = toMinutes(extractTimeParts(event.start_at));
    const end = toMinutes(extractTimeParts(event.end_at));

    if (start !== null) {
      blocks.push({
        type: "event",
        title: event.title,
        meta: event.location || event.source_agent || "Event",
        start: Math.max(start, dayStart),
        end: Math.min(end ?? start + 60, dayEnd),
      });
    }
  }

  const eventStarts = blocks.length > 0 ? blocks.map((b) => b.start) : [];
  let cursor = eventStarts.length > 0 ? Math.min(...eventStarts) : 9 * 60;

  for (const task of tasks || []) {
    const duration = 45;
    let start = cursor;
    let end = start + duration;

    if (end > dayEnd) {
      end = dayEnd;
      start = Math.max(dayStart, end - duration);
    }

    blocks.push({
      type: "task",
      title: task.title,
      meta: `${task.priority || "medium"} priority · ${task.source_agent || "TaskAgent"}`,
      start,
      end,
    });

    cursor = end + 15;
  }

  for (const route of finalResponse?.travel_estimates || []) {
    const duration = Number(route.estimated_minutes || 30);
    let start = cursor;
    let end = start + duration;

    if (end > dayEnd) {
      end = dayEnd;
      start = Math.max(dayStart, end - duration);
    }

    blocks.push({
      type: "route",
      title: `${route.origin} → ${route.destination}`,
      meta: `${route.estimated_minutes} min · ${route.mode || "travel"}`,
      start,
      end,
    });

    cursor = end + 10;
  }

  const filtered = blocks
    .filter((b) => b.end > b.start)
    .sort((a, b) => {
      if (a.start !== b.start) return a.start - b.start;
      return a.end - b.end;
    });

  const laneEnds = [];
  let maxLane = 0;

  for (const block of filtered) {
    let lane = 0;

    while (lane < laneEnds.length && block.start < laneEnds[lane]) {
      lane += 1;
    }

    block.lane = lane;
    laneEnds[lane] = block.end;
    if (lane > maxLane) maxLane = lane;
  }

  const laneCount = maxLane + 1;

  return filtered.map((block) => ({
    ...block,
    laneCount,
  }));
}

function blockStyle(start, end, lane, laneCount) {
  const totalMinutes = 12 * 60; // 8 AM to 8 PM
  const topPct = ((start - 8 * 60) / totalMinutes) * 100;
  const heightPct = ((end - start) / totalMinutes) * 100;

  const gutter = 8;
  const totalGutter = gutter * (laneCount + 1);
  const widthPx = `calc((100% - ${totalGutter}px) / ${laneCount})`;
  const leftPx = `calc(${gutter}px + (${lane} * (${widthPx} + ${gutter}px)))`;

  return {
    top: `${topPct}%`,
    height: `${Math.max(heightPct, 6)}%`,
    width: widthPx,
    left: leftPx,
    right: "auto",
    zIndex: lane + 1,
  };
}

async function getWorkflow(id) {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL;

  if (!base) {
    return { error: "NEXT_PUBLIC_API_BASE_URL is not set." };
  }

  try {
    const res = await fetch(`${base}/workflow/${id}`, { cache: "no-store" });
    const data = await res.json();

    if (!res.ok) {
      return { error: data?.detail || JSON.stringify(data) };
    }

    return { data };
  } catch (error) {
    return { error: String(error) };
  }
}

function jsonPretty(value) {
  return JSON.stringify(value, null, 2);
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
        <div className="card">
          <h1 className="card-title">Workflow #{id}</h1>
          <div className="error">{result.error}</div>
        </div>
      </main>
    );
  }

  const { workflow, tasks, events, notes, tool_logs } = result.data;
  const finalResponse = workflow?.final_response || {};
  const dayPlan = buildDayPlan(tasks, events, finalResponse);

  return (
    <main className="shell">
      <div className="top-nav">
        <a className="button button-secondary" href="/">
          ← Home
        </a>
      </div>

      <section className="hero">
        <div className="badge-row">
          <span className="badge">Workflow detail</span>
          <span className="badge">ID #{workflow.id}</span>
        </div>
        <h1 className="hero-title" style={{ fontSize: "clamp(28px, 4vw, 46px)" }}>
          {workflow.parsed_intent || "Workflow"}
        </h1>
        <p className="hero-subtitle">{workflow.raw_request}</p>
      </section>

      <section className="grid grid-main">
        <div className="card">
          <h2 className="card-title">Execution summary</h2>
          <div className="list">
            <div className="item">
              <div className="item-title">Status</div>
              <div className={`status ${workflow.status}`}>{workflow.status}</div>
            </div>
            <div className="item">
              <div className="item-title">Summary</div>
              <div className="small">{finalResponse.summary || "—"}</div>
            </div>
            <div className="item">
              <div className="item-title">Agents used</div>
              <div className="item-meta">
                {(workflow.agents_used || []).map((agent) => (
                  <span className="pill pill-accent" key={agent}>{agent}</span>
                ))}
              </div>
            </div>
          </div>

          <div className="section">
            <h3 className="section-title">Travel estimates</h3>
            {(finalResponse.travel_estimates || []).length === 0 ? (
              <div className="empty">No travel estimates for this workflow.</div>
            ) : (
              <div className="list">
                {finalResponse.travel_estimates.map((item, idx) => (
                  <div className="item" key={idx}>
                    <div className="item-title">{item.origin} → {item.destination}</div>
                    <div className="item-meta">
                      <span className="pill pill-blue">{item.estimated_minutes} min</span>
                      <span className="pill">{item.mode}</span>
                    </div>
                    <div className="small" style={{ marginTop: 8 }}>{item.note}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="card">
          <h2 className="card-title">Workflow metadata</h2>
          <div className="list">
            <div className="item">
              <div className="item-title">Started</div>
              <div className="small">{workflow.started_at || "—"}</div>
            </div>
            <div className="item">
              <div className="item-title">Completed</div>
              <div className="small">{workflow.completed_at || "—"}</div>
            </div>
            <div className="item">
              <div className="item-title">Saved note</div>
              <div className="small">{finalResponse.note_saved?.title || "—"}</div>
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="card">
          <h2 className="card-title">Day planner view</h2>
          <div className="day-planner">
            <div className="day-planner-header">Approximate day schedule</div>
            <div className="day-planner-grid">
              <div className="day-planner-hours">
                {Array.from({ length: 12 }).map((_, i) => {
                  const hour = 8 + i;
                  const label =
                    hour > 12
                      ? `${hour - 12}:00 PM`
                      : hour === 12
                        ? "12:00 PM"
                        : `${hour}:00 AM`;
                  return <div className="day-hour" key={hour}>{label}</div>;
                })}
              </div>
              <div className="day-planner-canvas">
                {dayPlan.map((block, idx) => (
                  <div
                    key={`${block.title}-${idx}`}
                    className={`day-block ${block.type}`}
                    style={blockStyle(block.start, block.end, block.lane, block.laneCount)}
                    title={`${block.title} (${formatMinutes(block.start)} – ${formatMinutes(block.end)})`}
                  >
                    <div className="day-block-title">{block.title}</div>
                    <div className="day-block-meta">
                      {formatMinutes(block.start)} – {formatMinutes(block.end)}
                    </div>
                    <div className="day-block-meta">{block.meta}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="split">
          <div className="card">
            <h2 className="card-title">Tasks</h2>
            {tasks.length === 0 ? (
              <div className="empty">No tasks.</div>
            ) : (
              <div className="list">
                {tasks.map((task) => (
                  <div className="item" key={task.id}>
                    <div className="item-title">{task.title}</div>
                    <div className="small">{task.description || "No description"}</div>
                    <div className="item-meta">
                      <span className="pill pill-blue">{task.priority}</span>
                      <span className="pill">{task.status}</span>
                      <span className="pill">{task.source_agent}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="card">
            <h2 className="card-title">Events</h2>
            {events.length === 0 ? (
              <div className="empty">No events.</div>
            ) : (
              <div className="list">
                {events.map((event) => (
                  <div className="item" key={event.id}>
                    <div className="item-title">{event.title}</div>
                    <div className="small">
                      {event.start_at || "—"} → {event.end_at || "—"}
                    </div>
                    <div className="item-meta">
                      <span className="pill">{event.location || "No location"}</span>
                      <span className="pill">{event.source_agent}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="split">
          <div className="card">
            <h2 className="card-title">Notes</h2>
            {notes.length === 0 ? (
              <div className="empty">No notes.</div>
            ) : (
              <div className="list">
                {notes.map((note) => (
                  <div className="item" key={note.id}>
                    <div className="item-title">{note.title}</div>
                    <div className="small">{note.content}</div>
                    <div className="item-meta">
                      <span className="pill">{note.note_type || "note"}</span>
                      <span className="pill">{note.tags || "—"}</span>
                      <span className="pill">{note.source_agent}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="card">
            <h2 className="card-title">Tool trace</h2>
            {tool_logs.length === 0 ? (
              <div className="empty">No tool logs.</div>
            ) : (
              <div className="timeline">
                {tool_logs.map((log) => (
                  <div className="timeline-item" key={log.id}>
                    <div className="row" style={{ justifyContent: "space-between" }}>
                      <div className="item-title">{log.tool_name}</div>
                      <div className="small">{log.agent_name}</div>
                    </div>
                    <div className="small">{log.created_at}</div>
                    <div className="codebox">{jsonPretty(log.output_json)}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}