import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles/globals.css";

// In Tauri, intercept external link clicks and open them in the system browser
if ("__TAURI__" in window) {
  document.addEventListener(
    "click",
    (e) => {
      const link = (e.target as HTMLElement).closest("a[href]") as HTMLAnchorElement | null;
      if (!link) return;
      const href = link.getAttribute("href");
      if (href?.startsWith("http://") || href?.startsWith("https://")) {
        e.preventDefault();
        import("@tauri-apps/plugin-shell").then(({ open }) => open(href));
      }
    },
    true
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
