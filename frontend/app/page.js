const SAMPLE_PROMPTS = [
  "Tomorrow I need to prepare for a 3 PM client call, buy printer ink in Makati, stop by the pharmacy, and remember to bring my notebook.",
  "Plan my Thursday. I have a 2:30 PM budget review, need to buy printer ink and bond paper after lunch, stop by Mercury Drug for vitamins, and pick up a package before 6 PM.",
  "I need help planning Friday. I have a client presentation at 3 PM, I want one hour of prep time before that, and I need to group errands efficiently before going home by 7 PM."
];

async function getDashboardData() {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL;

  if (!base) {
    return {
      error: "NEXT_PUBLIC_API_BASE_URL is not set.",
      workflows: [],
      tasks: [],
      notes: [],
    };
  }

  try {
    const [workflowsRes, tasksRes, notesRes] = await Promise.all([
      fetch(`${base}/workflows`, { cache: "no-store" }),
      fetch(`${base}/tasks`, { cache: "no-store" }),
      fetch(`${base}/notes`, { cache: "no-store" }),
    ]);

    const workflows = workflowsRes.ok ? await workflowsRes.json() : [];
    const tasks = tasksRes.ok ? await tasksRes.json() : [];
    const notes = notesRes.ok ? await notesRes.json() : [];

    return { workflows, tasks, notes, error: null };
  } catch (error) {
    return {
      workflows: [],
      tasks: [],
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
  const { workflows, tasks, notes, error } = await getDashboardData();
  const latest = workflows?.[0];
  const samplePrompt =
    SAMPLE_PROMPTS[Math.floor(Math.random() * SAMPLE_PROMPTS.length)];

  return (
    <main className="shell">
      <section className="hero">
        <div className="badge-row">
          <span className="badge">Gemini on Vertex AI</span>
          <span className="badge">AlloyDB</span>
          <span className="badge">Cloud Run</span>
          <span className="badge">Multi-Agent Workflow</span>
        </div>

        <h1 className="hero-title">LifeOps</h1>
        <p className="hero-subtitle">
          A multi-agent planning system that turns real-world requests into
          tasks, schedules, notes, and practical execution plans.
        </p>
      </section>

      <section className="grid grid-main">
        <div className="card">
          <h2 className="card-title">Plan a workflow</h2>
          <p className="card-subtitle">
            A sample prompt is already preloaded so the tester can just hit Run.
          </p>

          <form className="prompt-box" action="/run" method="get">
            <textarea
              className="textarea"
              name="q"
              defaultValue={samplePrompt}
            />
            <div className="action-row">
              <button className="button button-primary" type="submit">
                Run workflow
              </button>
              <a
                className="button button-secondary"
                href={latest ? `/workflow/${latest.id}` : "#"}
              >
                View latest workflow
              </a>
            </div>
          </form>

          <div className="section">
            <h3 className="section-title">What this demo shows</h3>
            <div className="list">
              <div className="item">
                <div className="item-title">Primary agent orchestration</div>
                <div className="small">
                  CoordinatorAgent delegates work to TaskAgent, ScheduleAgent,
                  KnowledgeAgent, and RouteAgent.
                </div>
              </div>
              <div className="item">
                <div className="item-title">Structured persistence</div>
                <div className="small">
                  Workflows, tasks, notes, events, and tool traces are stored in AlloyDB.
                </div>
              </div>
              <div className="item">
                <div className="item-title">API-first architecture</div>
                <div className="small">
                  The frontend and backend are deployed as separate Cloud Run services.
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="card">
          <h2 className="card-title">Live snapshot</h2>
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
              <div className="kpi-label">Stored notes</div>
              <div className="kpi-value">{notes.length}</div>
            </div>
          </div>

          <div className="section">
            <h3 className="section-title">Backend status</h3>
            {error ? (
              <div className="error">{error}</div>
            ) : (
              <div className="item">
                <div className="item-title">Connected</div>
                <div className="small">
                  Frontend can reach the backend API using the configured public base URL.
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="card">
          <h2 className="card-title">Recent workflows</h2>
          {workflows.length === 0 ? (
            <div className="empty">No workflows yet.</div>
          ) : (
            <div className="list">
              {workflows.slice(0, 6).map((wf) => (
                <a className="item" key={wf.id} href={`/workflow/${wf.id}`}>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <div className="item-title">Workflow #{wf.id}</div>
                    <div className={`status ${wf.status}`}>{wf.status}</div>
                  </div>
                  <div className="small" style={{ marginBottom: 8 }}>{wf.raw_request}</div>
                  <div className="item-meta">
                    <span className="pill pill-blue">Intent: {wf.parsed_intent || "—"}</span>
                    <span className="pill">Started: {fmtDate(wf.started_at)}</span>
                  </div>
                </a>
              ))}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}