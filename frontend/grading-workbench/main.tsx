import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./workbench.css";


const host = document.getElementById("grading-workbench-root");
if (!host) {
  throw new Error("Grading workbench root element is missing.");
}

const workspaceUrl = host.dataset.workspaceUrl;
if (!workspaceUrl) {
  throw new Error("Grading workspace URL is missing.");
}

createRoot(host).render(
  <StrictMode>
    <App workspaceUrl={workspaceUrl} />
  </StrictMode>
);
