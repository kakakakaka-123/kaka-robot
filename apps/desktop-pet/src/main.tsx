import React from "react";
import ReactDOM from "react-dom/client";
import { getCurrentWindow } from "@tauri-apps/api/window";

import { App } from "./App";
import { SettingsApp } from "./SettingsApp";
import "./styles.css";

type ErrorBoundaryState = {
  error: Error | null;
};

class ErrorBoundary extends React.Component<React.PropsWithChildren, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <main className="app-error-shell">
          <h1>窗口加载失败</h1>
          <p>{this.state.error.message || "前端运行时出现异常。"}</p>
        </main>
      );
    }

    return this.props.children;
  }
}

const searchView = new URLSearchParams(window.location.search).get("view");
const hashView = window.location.hash.replace(/^#\/?/, "");

function getTauriWindowLabel() {
  try {
    return getCurrentWindow().label;
  } catch {
    return null;
  }
}

const windowLabel = getTauriWindowLabel();
const RootComponent = searchView === "settings" || hashView === "settings" || windowLabel === "settings" ? SettingsApp : App;

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ErrorBoundary>
      <RootComponent />
    </ErrorBoundary>
  </React.StrictMode>
);
