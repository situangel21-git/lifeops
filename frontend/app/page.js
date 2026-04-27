function DayWeaverMark() {
  return (
    <svg
      viewBox="0 0 128 128"
      aria-hidden="true"
      className="brand-mark-svg"
      role="img"
    >
      <defs>
        <linearGradient id="dw-bg" x1="14" y1="10" x2="114" y2="118">
          <stop offset="0%" stopColor="#2563eb" />
          <stop offset="52%" stopColor="#0ea5e9" />
          <stop offset="100%" stopColor="#14b8a6" />
        </linearGradient>

        <linearGradient id="dw-stroke" x1="24" y1="24" x2="106" y2="106">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="100%" stopColor="#eaf6ff" />
        </linearGradient>
      </defs>

      <rect x="10" y="10" width="108" height="108" rx="30" fill="url(#dw-bg)" />

      <path
        d="M34 36 C47 28, 69 28, 84 36 C96 43, 103 55, 103 67 C103 79, 97 91, 84 98 C69 106, 47 106, 34 98"
        fill="none"
        stroke="url(#dw-stroke)"
        strokeWidth="10"
        strokeLinecap="round"
      />

      <path
        d="M34 36 V98"
        fill="none"
        stroke="url(#dw-stroke)"
        strokeWidth="10"
        strokeLinecap="round"
      />

      <path
        d="M36 74 C49 60, 57 54, 70 51 C79 49, 88 50, 96 54"
        fill="none"
        stroke="#dff7ff"
        strokeWidth="5.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.95"
      />

      <circle cx="36" cy="74" r="6.5" fill="#ffffff" />
      <circle cx="70" cy="51" r="6" fill="#dff7ff" />
      <circle cx="96" cy="54" r="6.5" fill="#ffffff" />
    </svg>
  );
}

const DEMO_PROMPTS = [
  "Plan my Thursday. I will start from Makati City. I have a client presentation in BGC at 3 PM. I need one hour of prep time before that, buy printer ink in Makati before heading to BGC, stop by Mercury Drug in BGC for vitamins after the presentation, and pick up a package in Quezon City before going home by 7 PM.",
  "Plan my Friday. I will start from Ortigas. I have a project review in Makati at 11 AM, need 30 minutes of prep before that, buy a phone charger nearby after the meeting, then go to BGC for a 3 PM client sync, and be back home in Quezon City by 7 PM.",
  "Plan tomorrow. I will start from Quezon City. I need to drop documents in Ortigas before 10 AM, attend a vendor meeting in BGC at 1 PM, buy medicine after the meeting, and return to Quezon City before 6:30 PM.",
  "Plan my afternoon. I will start from Makati. I need to prepare for a 2 PM presentation in BGC for one hour, attend the presentation, buy vitamins at Mercury Drug in BGC, then go to Pasig for a pickup before heading home by 7 PM.",
  "Plan my workday. I will start from Alabang. I have a 10 AM site visit in Makati, need to buy printer supplies before lunch, attend a 3 PM meeting in BGC, and go home before 8 PM.",
  "Plan my Tuesday. I will start from BGC. I have a 9 AM strategy call, need to visit a supplier in Makati before noon, pick up documents in Quezon City after lunch, and get home by 6 PM.",
  "Plan my Wednesday. I will start from Makati. I need to buy presentation materials, travel to Ortigas for a 1 PM client meeting, stop by a pharmacy nearby after the meeting, and reach Quezon City before 6 PM.",
  "Plan my Saturday. I will start from Quezon City. I need to buy school supplies in Cubao, attend a family lunch in BGC at 1 PM, pick up a package in Makati afterward, and go home by 7 PM.",
  "Plan my Monday. I will start from Pasig. I have a 10 AM budget review in BGC with 45 minutes of prep before it, need to buy printer ink in Makati afterward, pick up vitamins, and return to Pasig before 6 PM.",
  "Plan my day. I will start from Makati. I need to prepare for a 4 PM client call in BGC, buy printer ink before going there, stop by Mercury Drug after the call, pick up a package in Quezon City, and be home by 8 PM.",
];

async function getDashboardData() {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL;

  if (!base) {
    return {
      error: "NEXT_PUBLIC_API_BASE_URL is not set.",
      workflows: [],
      tasks: [],
      events: [],
      notes: [],
    };
  }

  try {
    const [workflowsRes, tasksRes, eventsRes, notesRes] = await Promise.all([
      fetch(`${base}/workflows`, { cache: "no-store" }),
      fetch(`${base}/tasks`, { cache: "no-store" }),
      fetch(`${base}/events`, { cache: "no-store" }),
      fetch(`${base}/notes`, { cache: "no-store" }),
    ]);

    const workflows = workflowsRes.ok ? await workflowsRes.json() : [];
    const tasks = tasksRes.ok ? await tasksRes.json() : [];
    const events = eventsRes.ok ? await eventsRes.json() : [];
    const notes = notesRes.ok ? await notesRes.json() : [];

    return {
      workflows,
      tasks,
      events,
      notes,
      error: null,
    };
  } catch (error) {
    return {
      workflows: [],
      tasks: [],
      events: [],
      notes: [],
      error: String(error),
    };
  }
}

function fmtDate(value) {
  if (!value) return "—";

  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export default async function HomePage() {
  const { workflows, tasks, events, notes, error } = await getDashboardData();
  const latest = workflows?.[0];
  const demoPrompt =
    DEMO_PROMPTS[Math.floor(Math.random() * DEMO_PROMPTS.length)];

  return (
    <main className="shell">
      <section className="hero-card hero-home">
        <div className="hero-home-grid">
          <div className="brand-block">
            <div className="brand-row">
              <div className="brand-mark-shell">
                <DayWeaverMark />
              </div>

              <div className="brand-copy">
                <span className="eyebrow">MULTI-AGENT EXECUTION PLANNER</span>
                <h1 className="hero-title hero-title-home">
                  <span className="gradient-text">DayWeaver</span>
                </h1>
              </div>
            </div>

            <p className="hero-subtitle hero-subtitle-home">
              Turn messy real-world requests into structured tasks, schedule
              blocks, memory notes, and route-aware execution plans.
            </p>

            <div className="hero-gap" />

            <div className="badge-row">
              <span className="badge badge-strong">Gemini on Vertex AI</span>
              <span className="badge">AlloyDB Persistence</span>
              <span className="badge">Google Maps Routes</span>
              <span className="badge">Cloud Run</span>
              <span className="badge">Agent Traceability</span>
            </div>
          </div>

          <div className="hero-side-panel">
            <div className="hero-side-card">
              <div>
                <div className="hero-side-kicker">Demo Mode</div>
                <div className="hero-side-title">Run a judge-friendly scenario</div>
                <div className="hero-side-text">
                  Demo Mode randomly selects from 10 planning scenarios that
                  trigger tasks, fixed events, routes, maps, and agent tracing.
                </div>

                <div className="demo-action-row">
                  <a
                    className="button button-primary"
                    href={`/run?q=${encodeURIComponent(demoPrompt)}`}
                  >
                    Run Demo Mode
                  </a>
                </div>
              </div>

              <div className="hero-side-mini-grid">
                <div className="hero-mini-stat">
                  <div className="hero-mini-label">Workflows</div>
                  <div className="hero-mini-value">{workflows.length}</div>
                </div>

                <div className="hero-mini-stat">
                  <div className="hero-mini-label">Tasks</div>
                  <div className="hero-mini-value">{tasks.length}</div>
                </div>

                <div className="hero-mini-stat">
                  <div className="hero-mini-label">Events</div>
                  <div className="hero-mini-value">{events.length}</div>
                </div>

                <div className="hero-mini-stat">
                  <div className="hero-mini-label">Notes</div>
                  <div className="hero-mini-value">{notes.length}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="grid grid-main page-gap-lg">
        <div className="card feature-card">
          <div className="card-heading-row">
            <div>
              <h2 className="card-title">Run a workflow</h2>
              <p className="card-subtitle">
                A strong demo prompt is preloaded so the reviewer can test the
                full orchestration flow immediately.
              </p>
            </div>
          </div>

          <form className="prompt-box" action="/run" method="GET">
            <textarea
              className="textarea"
              name="q"
              defaultValue={demoPrompt}
              aria-label="Workflow request"
            />

            <div className="action-row">
              <button className="button button-primary" type="submit">
                Run workflow
              </button>

              <a
                className="button button-secondary"
                href={`/run?q=${encodeURIComponent(demoPrompt)}`}
              >
                Run Demo Mode
              </a>

              <a
                className="button button-secondary"
                href={latest ? `/workflow/${latest.id}` : "#"}
              >
                View latest workflow
              </a>
            </div>
          </form>

          <div className="section">
            <h3 className="section-title">Core demo strengths</h3>

            <div className="responsive-card-grid">
              <div className="item item-soft">
                <div className="item-title">Primary agent orchestration</div>
                <div className="small">
                  CoordinatorAgent delegates work to TaskAgent, ScheduleAgent,
                  KnowledgeAgent, and RouteAgent.
                </div>
              </div>

              <div className="item item-soft">
                <div className="item-title">Route-aware planning</div>
                <div className="small">
                  RouteAgent estimates travel time and the planner places route
                  blocks before the destination event, errand, or deadline.
                </div>
              </div>

              <div className="item item-soft">
                <div className="item-title">Outlook-style planner</div>
                <div className="small">
                  Time blocks are displayed on a calendar grid, with conflicts
                  shown side-by-side.
                </div>
              </div>

              <div className="item item-soft">
                <div className="item-title">Structured persistence</div>
                <div className="small">
                  Workflows, tasks, events, notes, and tool traces are stored in
                  AlloyDB for retrieval and review.
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="card feature-card snapshot-card">
          <div className="card-heading-row">
            <div>
              <h2 className="card-title">Live snapshot</h2>
              <p className="card-subtitle">
                Quick view of the current persisted data and service state.
              </p>
            </div>
          </div>

          <div className="kpi-list">
            <div className="kpi">
              <div className="kpi-label">Workflow count</div>
              <div className="kpi-value">{workflows.length}</div>
            </div>

            <div className="kpi">
              <div className="kpi-label">Task count</div>
              <div className="kpi-value">{tasks.length}</div>
            </div>

            <div className="kpi">
              <div className="kpi-label">Event count</div>
              <div className="kpi-value">{events.length}</div>
            </div>

            <div className="kpi">
              <div className="kpi-label">Stored notes</div>
              <div className="kpi-value">{notes.length}</div>
            </div>
          </div>

          <div className="section">
            <h3 className="section-title">Backend status</h3>

            {error ? (
              <div className="error">{error}</div>
            ) : (
              <div className="item item-soft">
                <div className="item-title">Connected</div>
                <div className="small">
                  Frontend can reach the backend API using the configured public
                  base URL.
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="page-gap-lg">
        <details className="details-card home-workflow-dropdown">
          <summary>
            <span>Recent workflows</span>
            <span className="summary-hint">
              Hidden by default to keep the homepage clean
            </span>
          </summary>

          <div className="details-content">
            {workflows.length === 0 ? (
              <div className="empty">No workflows yet.</div>
            ) : (
              <div className="list">
                {workflows.slice(0, 8).map((wf) => (
                  <a className="item item-soft" key={wf.id} href={`/workflow/${wf.id}`}>
                    <div className="row" style={{ justifyContent: "space-between" }}>
                      <div className="item-title">Workflow #{wf.id}</div>
                      <div className={`status-text ${wf.status}`}>{wf.status}</div>
                    </div>

                    <div className="small workflow-request-preview">
                      {wf.raw_request}
                    </div>

                    <div className="item-meta">
                      <span className="pill pill-blue">
                        Intent: {wf.parsed_intent || "—"}
                      </span>
                      <span className="pill">Started: {fmtDate(wf.started_at)}</span>
                    </div>
                  </a>
                ))}
              </div>
            )}
          </div>
        </details>
      </section>
    </main>
  );
}