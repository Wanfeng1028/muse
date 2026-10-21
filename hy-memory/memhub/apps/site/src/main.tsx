import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./site.css";

const container = document.getElementById("root");
if (container === null) {
  throw new Error("root container missing");
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
