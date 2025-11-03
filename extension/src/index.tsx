import * as SDK from "azure-devops-extension-sdk";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./components/App";
import "./styles/index.css";

// Initialize the SDK
SDK.init().then(() => {
  console.log("Azure DevOps SDK initialized");
  
  // Get the root element
  const rootElement = document.getElementById("root");
  if (!rootElement) {
    throw new Error("Root element not found");
  }

  // Render the app
  const root = ReactDOM.createRoot(rootElement);
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
}).catch((error) => {
  console.error("Failed to initialize SDK:", error);
  document.body.innerHTML = `<div style="padding: 20px; color: red;">
    <h2>Extension Initialization Failed</h2>
    <p>${error.message}</p>
  </div>`;
});

