import React, { useState, useEffect } from "react";
import * as SDK from "azure-devops-extension-sdk";
import azureDevOpsService, { WorkItem } from "../services/azureDevOpsService";

interface StoryFetcherProps {
  onStoryFetched: (story: WorkItem) => void;
  onWorkItemIdChange: (id: string) => void;
}

const StoryFetcher: React.FC<StoryFetcherProps> = ({
  onStoryFetched,
  onWorkItemIdChange,
}) => {
  const [workItemId, setWorkItemId] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");
  const [currentWorkItemId, setCurrentWorkItemId] = useState<string>("");

  // Try to get work item ID from extension context
  useEffect(() => {
    const getContext = async () => {
      try {
        const context = SDK.getExtensionContext();
        // Try to get work item ID from URL parameters or context
        const urlParams = new URLSearchParams(window.location.search);
        const id = urlParams.get("workItemId");
        if (id) {
          setWorkItemId(id);
          setCurrentWorkItemId(id);
          onWorkItemIdChange(id);
        }
      } catch (error) {
        console.log("Could not get work item ID from context:", error);
      }
    };

    getContext();
  }, [onWorkItemIdChange]);

  const handleFetch = async () => {
    if (!workItemId.trim()) {
      setError("Please enter a work item ID");
      return;
    }

    const id = parseInt(workItemId);
    if (isNaN(id)) {
      setError("Work item ID must be a number");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const story = await azureDevOpsService.getWorkItem(id);
      onStoryFetched(story);
      setCurrentWorkItemId(workItemId);
      onWorkItemIdChange(workItemId);
    } catch (err: any) {
      setError(err.message || "Failed to fetch work item");
      console.error("Error fetching work item:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <label htmlFor="work-item-id">Work Item ID:</label>
      <input
        id="work-item-id"
        type="text"
        value={workItemId}
        onChange={(e) => setWorkItemId(e.target.value)}
        placeholder="Enter User Story ID"
        disabled={loading}
      />
      <button onClick={handleFetch} disabled={loading || !workItemId.trim()}>
        {loading && <span className="spinner" />}
        {loading ? "Fetching..." : "Fetch User Story"}
      </button>

      {error && (
        <div className="status-message error">
          <strong>Error:</strong> {error}
        </div>
      )}

      {currentWorkItemId && (
        <div className="status-message success" style={{ marginTop: "10px" }}>
          Work Item {currentWorkItemId} loaded successfully
        </div>
      )}
    </div>
  );
};

export default StoryFetcher;

