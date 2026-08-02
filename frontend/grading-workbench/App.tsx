import { useCallback, useEffect, useRef, useState } from "react";

import { PixiViewport, type ViewerControls } from "./PixiViewport";
import { fetchWorkspace, type GradingWorkspace } from "./workspace";


interface AppProps {
  workspaceUrl: string;
}

export function App({ workspaceUrl }: AppProps) {
  const [workspace, setWorkspace] = useState<GradingWorkspace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(100);
  const viewerRef = useRef<ViewerControls>(null);
  const onZoomChange = useCallback((percent: number) => setZoom(percent), []);

  useEffect(() => {
    const controller = new AbortController();
    setWorkspace(null);
    setError(null);
    fetchWorkspace(workspaceUrl, controller.signal)
      .then(setWorkspace)
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Unable to load grading workspace.");
      });
    return () => controller.abort();
  }, [workspaceUrl]);

  if (error) {
    return (
      <section className="grading-workbench-fatal" role="alert">
        <h1>Grading workbench unavailable</h1>
        <p>{error}</p>
        <a className="btn btn-outline-light" href="/grading/">Return to grading</a>
      </section>
    );
  }

  if (!workspace) {
    return <div className="grading-workbench-bootstrap-state" role="status">Loading grading workbench…</div>;
  }

  return (
    <div className="grading-workbench-shell">
      <header className="grading-workbench-header">
        <div>
          <div className="grading-workbench-eyebrow">Standalone grading viewer</div>
          <h1>{workspace.task.disease.name}</h1>
          <div className="grading-workbench-context">
            {workspace.task.lab_unit.name} · {workspace.target.slot} · {workspace.task.state}
          </div>
        </div>
        <div className="grading-workbench-actions">
          <button type="button" onClick={() => viewerRef.current?.zoomOut()} aria-label="Zoom out">−</button>
          <output aria-label="Current zoom">{zoom}%</output>
          <button type="button" onClick={() => viewerRef.current?.zoomIn()} aria-label="Zoom in">+</button>
          <button type="button" onClick={() => viewerRef.current?.fit()}>Fit</button>
          <a href="/grading/">Close</a>
        </div>
      </header>

      <main className="grading-workbench-main">
        <PixiViewport
          ref={viewerRef}
          imageUrl={workspace.image.url}
          imageLabel={workspace.image.filename || `Fundus image ${workspace.image.uuid}`}
          onZoomChange={onZoomChange}
        />
        <aside className="grading-workbench-side-panel" aria-label="Grading context">
          <h2>Grading</h2>
          <dl>
            <dt>Image</dt>
            <dd>{workspace.image.filename || workspace.image.uuid}</dd>
            <dt>Source</dt>
            <dd>{workspace.image.source.replaceAll("_", " ")}</dd>
            <dt>Task</dt>
            <dd><code>{workspace.task.uuid}</code></dd>
          </dl>
          <div className="grading-workbench-read-only" role="note">
            <strong>Read-only foundation</strong>
            {workspace.read_only_reasons.map((reason) => <p key={reason}>{reason}</p>)}
          </div>
        </aside>
      </main>
    </div>
  );
}
