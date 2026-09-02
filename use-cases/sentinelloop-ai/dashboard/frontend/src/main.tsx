import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import "../design-system/tokens.css";
import "../design-system/typography.css";
import "../design-system/primitives.css";
import "../design-system/layout.css";
import "./styles/base.css";
import "./styles/command-center.css";
import "./styles/incident-intel.css";
import "./styles/shell.css";
import "./styles/mobile.css";
import { App } from "./App";
import { applyOperatorPrefs } from "./demo/operatorPrefs";

applyOperatorPrefs();

const root = document.getElementById("root");
if (!root) {
  throw new Error("root element missing");
}

createRoot(root).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
