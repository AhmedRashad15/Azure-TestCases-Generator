import React, { useState } from "react";
import apiService from "../services/apiService";
import azureDevOpsService, { WorkItem, TestCase } from "../services/azureDevOpsService";
import RichTextEditor from "./RichTextEditor";

interface TestCaseGeneratorProps {
  storyData: WorkItem;
  workItemId: string;
}

const TestCaseGenerator: React.FC<TestCaseGeneratorProps> = ({
  storyData,
  workItemId,
}) => {
  const [loading, setLoading] = useState(false);
  const [testCases, setTestCases] = useState<TestCase[]>([]);
  const [error, setError] = useState<string>("");
  const [progress, setProgress] = useState<string>("");
  const [dataDictionary, setDataDictionary] = useState<string>("");
  const [testPlanId, setTestPlanId] = useState<string>("");
  const [testSuiteId, setTestSuiteId] = useState<string>("");
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string>("");
  const [aiProvider, setAiProvider] = useState<string>("gemini");
  const [ambiguityAware, setAmbiguityAware] = useState<boolean>(true);

  const handleGenerate = async () => {
    setLoading(true);
    setError("");
    setProgress("");
    setTestCases([]);

    try {
      const relatedStories = storyData.related_stories || [];

      await apiService.generateTestCases(
        storyData.title,
        storyData.description,
        storyData.acceptance_criteria,
        dataDictionary,
        relatedStories,
        (progressData) => {
          if (progressData.progress) {
            setProgress(progressData.progress);
          }
          if (progressData.cases) {
            setTestCases((prev) => [...prev, ...progressData.cases!]);
          }
          if (progressData.message) {
            setProgress(progressData.message);
          }
        },
        aiProvider,
        ambiguityAware
      );

      setProgress("All test cases generated successfully!");
    } catch (err: any) {
      setError(err.message || "Failed to generate test cases");
      console.error("Error generating test cases:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleUpload = async () => {
    if (!testPlanId || !testSuiteId) {
      setUploadStatus("Please enter Test Plan ID and Test Suite ID");
      return;
    }

    if (testCases.length === 0) {
      setUploadStatus("No test cases to upload. Please generate test cases first.");
      return;
    }

    setUploading(true);
    setUploadStatus("");

    try {
      await azureDevOpsService.uploadTestCases(
        testCases,
        parseInt(testPlanId),
        parseInt(testSuiteId)
      );

      setUploadStatus(`Successfully uploaded ${testCases.length} test cases!`);
    } catch (err: any) {
      setUploadStatus(`Error uploading test cases: ${err.message}`);
      console.error("Error uploading test cases:", err);
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteTestCase = (index: number) => {
    setTestCases((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <div>
      <div style={{ marginBottom: "10px" }}>
        <label htmlFor="ai-provider-generate" style={{ marginRight: "10px" }}>
          AI Provider:
        </label>
        <select
          id="ai-provider-generate"
          value={aiProvider}
          onChange={(e) => setAiProvider(e.target.value)}
          disabled={loading}
          style={{ padding: "5px", fontSize: "14px" }}
        >
          <option value="gemini">Google Gemini</option>
          <option value="claude">Anthropic Claude</option>
        </select>
      </div>
      <div style={{ marginBottom: "10px" }}>
        <label style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <input
            type="checkbox"
            checked={ambiguityAware}
            onChange={(e) => setAmbiguityAware(e.target.checked)}
            disabled={loading}
            style={{ width: "18px", height: "18px", cursor: "pointer" }}
          />
          <span>Enable ambiguity-aware test case generation</span>
        </label>
        <small style={{ display: "block", marginTop: "4px", color: "#666", fontSize: "12px" }}>
          When enabled, generates test cases that address ambiguities and contradictions in requirements (max 2-3 per ambiguity)
        </small>
      </div>
      <div>
        <label htmlFor="data-dictionary">Data Dictionary (Optional):</label>
        <RichTextEditor
          value={dataDictionary}
          onChange={(html) => setDataDictionary(html)}
          readOnly={false}
          placeholder="Enter data dictionary information..."
        />
      </div>

      <button onClick={handleGenerate} disabled={loading}>
        {loading && <span className="spinner" />}
        {loading ? "Generating..." : "Generate Test Cases"}
      </button>

      {progress && (
        <div className="status-message info" style={{ marginTop: "10px" }}>
          {progress}
        </div>
      )}

      {error && (
        <div className="status-message error" style={{ marginTop: "10px" }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {testCases.length > 0 && (
        <div style={{ marginTop: "20px" }}>
          <h3>Generated Test Cases ({testCases.length})</h3>
          {testCases.map((tc, index) => (
            <div key={index} className="test-case-item">
              <div className="test-case-header">
                <strong>{tc.id || `TC-${index + 1}`}: {tc.title}</strong>
                <button
                  onClick={() => handleDeleteTestCase(index)}
                  style={{
                    padding: "5px 10px",
                    fontSize: "12px",
                    background: "#dc3545",
                  }}
                >
                  Delete
                </button>
              </div>
              <div className="test-case-content">
                <p>
                  <strong>Priority:</strong> {tc.priority}
                </p>
                <p>
                  <strong>Description:</strong> {tc.description}
                </p>
                <p>
                  <strong>✅ Expected Result:</strong> ✅ {tc.expectedResult}
                </p>
              </div>
            </div>
          ))}

          <div style={{ marginTop: "20px" }}>
            <h3>Upload to Azure DevOps</h3>
            <label htmlFor="test-plan-id">Test Plan ID:</label>
            <input
              id="test-plan-id"
              type="text"
              value={testPlanId}
              onChange={(e) => setTestPlanId(e.target.value)}
              placeholder="Enter Test Plan ID"
            />

            <label htmlFor="test-suite-id">Test Suite ID:</label>
            <input
              id="test-suite-id"
              type="text"
              value={testSuiteId}
              onChange={(e) => setTestSuiteId(e.target.value)}
              placeholder="Enter Test Suite ID"
            />

            <button onClick={handleUpload} disabled={uploading}>
              {uploading && <span className="spinner" />}
              {uploading ? "Uploading..." : "Upload Test Cases"}
            </button>

            {uploadStatus && (
              <div
                className={`status-message ${
                  uploadStatus.includes("Error") ? "error" : "success"
                }`}
                style={{ marginTop: "10px" }}
              >
                {uploadStatus}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default TestCaseGenerator;

