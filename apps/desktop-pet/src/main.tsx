import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "./App";
import { SettingsApp } from "./SettingsApp";
import "./styles.css";

const view = new URLSearchParams(window.location.search).get("view");
const RootComponent = view === "settings" ? SettingsApp : App;

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <RootComponent />
  </React.StrictMode>
);
