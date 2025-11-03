import React, { useState } from "react";
import apiService from "../services/apiService";
import { WorkItem } from "../services/azureDevOpsService";

interface StoryAnalysisProps {
  storyData: WorkItem;
}

const StoryAnalysis: React.FC<StoryAnalysisProps> = ({ storyData }) => {
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState<string>("");
  const [error, setError] = useState<string>("");

  const handleAnalyze = async () => {
    setLoading(true);
    setError("");
    setAnalysis("");

    try {
      const response = await apiService.analyzeStory(
        storyData.title,
        storyData.description,
        storyData.acceptance_criteria
      );

      // Clean up HTML response
      let htmlContent = response.analysis.trim();
      htmlContent = htmlContent.replace(/```html\s*/g, "");
      htmlContent = htmlContent.replace(/```\s*/g, "");
      htmlContent = htmlContent.trim();

      // Extract HTML if wrapped in code blocks
      const htmlMatch = htmlContent.match(/<div class="review-container">[\s\S]*<\/div>/);
      if (htmlMatch) {
        htmlContent = htmlMatch[0];
      }

      setAnalysis(htmlContent);
    } catch (err: any) {
      setError(err.message || "Failed to analyze story");
      console.error("Error analyzing story:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    const textArea = document.createElement("textarea");
    textArea.value = document.getElementById("analysis-content")?.textContent || "";
    document.body.appendChild(textArea);
    textArea.select();
    try {
      document.execCommand("copy");
      alert("Analysis copied to clipboard!");
    } catch (err) {
      console.error("Failed to copy:", err);
    }
    document.body.removeChild(textArea);
  };

  return (
    <div>
      <button onClick={handleAnalyze} disabled={loading}>
        {loading && <span className="spinner" />}
        {loading ? "Analyzing..." : "Analyze User Story"}
      </button>

      {error && (
        <div className="status-message error">
          <strong>Error:</strong> {error}
        </div>
      )}

      {analysis && (
        <div style={{ marginTop: "20px" }}>
          <button onClick={handleCopy} style={{ marginBottom: "10px" }}>
            Copy Analysis to Clipboard
          </button>
          <div
            id="analysis-content"
            dangerouslySetInnerHTML={{ __html: analysis }}
          />
        </div>
      )}

      {loading && !analysis && (
        <div className="status-message info" style={{ marginTop: "10px" }}>
          Generating analysis... This may take a moment.
        </div>
      )}
    </div>
  );
};

export default StoryAnalysis;

