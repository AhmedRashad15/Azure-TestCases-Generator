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
  
  // Notify that the extension has loaded successfully
  SDK.notifyLoadSucceeded();
}).catch((error) => {
  console.error("Failed to initialize SDK:", error);
  
  // Notify that the extension failed to load
  SDK.notifyLoadFailed(error);
  
  // Show error message
  const rootElement = document.getElementById("root");
  if (rootElement) {
    rootElement.innerHTML = `<div style="padding: 20px; color: red;">
      <h2>Extension Initialization Failed</h2>
      <p>${error.message || String(error)}</p>
      <p>Please check browser console (F12) for more details.</p>
    </div>`;
  }
});

