import React from "react";
import ReactDOM from "react-dom/client";

import { ErrorBoundary } from "./ErrorBoundary";
import { SettingsApp } from "./SettingsApp";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ErrorBoundary>
      <SettingsApp />
    </ErrorBoundary>
  </React.StrictMode>
);
