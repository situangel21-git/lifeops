export default function Loading() {
  return (
    <main className="loading-overlay">
      <div className="loading-card">
        <div className="loading-spinner" />
        <h1 className="loading-title">Please wait while the agents plan your day</h1>
        <p className="loading-text">
          CoordinatorAgent is orchestrating your workflow, while TaskAgent,
          ScheduleAgent, KnowledgeAgent, and RouteAgent are preparing a practical plan.
        </p>
      </div>
    </main>
  );
}