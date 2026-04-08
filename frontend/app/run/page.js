import { redirect } from "next/navigation";

async function runWorkflow(query) {
  const base = process.env.NEXT_PUBLIC_API_BASE_URL;

  if (!base) {
    return { error: "NEXT_PUBLIC_API_BASE_URL is not set." };
  }

  if (!query) {
    return { error: "No workflow request was provided." };
  }

  try {
    const res = await fetch(`${base}/plan`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request: query }),
    });

    const data = await res.json();

    if (!res.ok) {
      return { error: data?.detail || JSON.stringify(data) };
    }

    return { data };
  } catch (error) {
    return { error: String(error) };
  }
}

export default async function RunPage({ searchParams }) {
  const params = await searchParams;
  const query = params?.q || "";

  const result = await runWorkflow(query);

  if (result.error) {
    return (
      <main className="shell">
        <div className="top-nav">
          <a className="button button-secondary" href="/">
            ← Home
          </a>
        </div>

        <section className="hero">
          <div className="badge-row">
            <span className="badge">Workflow execution</span>
          </div>
          <h1 className="hero-title" style={{ fontSize: "clamp(28px, 4vw, 44px)" }}>
            Run failed
          </h1>
          <p className="hero-subtitle">
            The workflow request could not be completed.
          </p>
        </section>

        <div className="card">
          <h2 className="card-title">Request</h2>
          <div className="codebox">{query || "—"}</div>
        </div>

        <div className="section">
          <div className="card">
            <h2 className="card-title">Error</h2>
            <div className="error">{result.error}</div>
          </div>
        </div>
      </main>
    );
  }

  redirect(`/workflow/${result.data.workflow_id}`);
}