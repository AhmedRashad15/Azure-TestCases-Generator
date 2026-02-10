import React, { useState, useRef } from "react";
import { TestCase } from "../services/azureDevOpsService";
import azureDevOpsService from "../services/azureDevOpsService";

interface TestExecutionProps {
  testCases: TestCase[];
  userStoryId: string;
  userStoryTitle: string;
}

interface TestExecutionResult {
  testCaseId: string;
  status: "pass" | "fail" | "not_run";
  actualResult?: string;
  screenshotIds?: string[];
}

interface Screenshot {
  id: string;
  dataUrl: string;
  name: string;
}

const TestExecution: React.FC<TestExecutionProps> = ({
  testCases,
  userStoryId,
  userStoryTitle,
}) => {
  const [executionResults, setExecutionResults] = useState<Map<string, TestExecutionResult>>(
    new Map()
  );
  const [screenshots, setScreenshots] = useState<Screenshot[]>([]);
  const [showScreenshotAssignment, setShowScreenshotAssignment] = useState(false);
  const [creatingBugs, setCreatingBugs] = useState(false);
  const [bugCreationStatus, setBugCreationStatus] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pasteAreaRef = useRef<HTMLDivElement>(null);

  // Initialize execution results
  React.useEffect(() => {
    const initialResults = new Map<string, TestExecutionResult>();
    testCases.forEach((tc) => {
      initialResults.set(tc.id || `TC-${testCases.indexOf(tc)}`, {
        testCaseId: tc.id || `TC-${testCases.indexOf(tc)}`,
        status: "not_run",
      });
    });
    setExecutionResults(initialResults);
  }, [testCases]);

  const handleStatusChange = (testCaseId: string, status: "pass" | "fail" | "not_run") => {
    setExecutionResults((prev) => {
      const newMap = new Map(prev);
      const current = newMap.get(testCaseId) || {
        testCaseId,
        status: "not_run",
      };
      newMap.set(testCaseId, {
        ...current,
        status,
        actualResult: status === "fail" ? current.actualResult || "" : undefined,
        screenshotIds: status === "fail" ? current.screenshotIds || [] : undefined,
      });
      return newMap;
    });
  };

  const handleActualResultChange = (testCaseId: string, actualResult: string) => {
    setExecutionResults((prev) => {
      const newMap = new Map(prev);
      const current = newMap.get(testCaseId) || {
        testCaseId,
        status: "not_run",
      };
      newMap.set(testCaseId, {
        ...current,
        actualResult,
      });
      return newMap;
    });
  };

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files) return;

    Array.from(files).forEach((file) => {
      if (file.type.startsWith("image/")) {
        const reader = new FileReader();
        reader.onload = (e) => {
          const dataUrl = e.target?.result as string;
          const screenshot: Screenshot = {
            id: `screenshot-${Date.now()}-${Math.random()}`,
            dataUrl,
            name: file.name,
          };
          setScreenshots((prev) => [...prev, screenshot]);
        };
        reader.readAsDataURL(file);
      }
    });

    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handlePaste = (event: React.ClipboardEvent) => {
    const items = event.clipboardData.items;
    Array.from(items).forEach((item) => {
      if (item.type.startsWith("image/")) {
        const file = item.getAsFile();
        if (file) {
          const reader = new FileReader();
          reader.onload = (e) => {
            const dataUrl = e.target?.result as string;
            const screenshot: Screenshot = {
              id: `screenshot-${Date.now()}-${Math.random()}`,
              dataUrl,
              name: `Pasted Image ${new Date().toLocaleTimeString()}`,
            };
            setScreenshots((prev) => [...prev, screenshot]);
          };
          reader.readAsDataURL(file);
        }
      }
    });
  };

  const removeScreenshot = (screenshotId: string) => {
    setScreenshots((prev) => prev.filter((s) => s.id !== screenshotId));
    // Remove from test case assignments
    setExecutionResults((prev) => {
      const newMap = new Map(prev);
      newMap.forEach((result, key) => {
        if (result.screenshotIds?.includes(screenshotId)) {
          newMap.set(key, {
            ...result,
            screenshotIds: result.screenshotIds?.filter((id) => id !== screenshotId),
          });
        }
      });
      return newMap;
    });
  };

  const toggleScreenshotAssignment = (testCaseId: string, screenshotId: string) => {
    setExecutionResults((prev) => {
      const newMap = new Map(prev);
      const current = newMap.get(testCaseId) || {
        testCaseId,
        status: "fail",
        screenshotIds: [],
      };
      const currentScreenshots = current.screenshotIds || [];
      const newScreenshots = currentScreenshots.includes(screenshotId)
        ? currentScreenshots.filter((id) => id !== screenshotId)
        : [...currentScreenshots, screenshotId];

      newMap.set(testCaseId, {
        ...current,
        screenshotIds: newScreenshots,
      });
      return newMap;
    });
  };

  const getFailedTestCases = () => {
    return Array.from(executionResults.values()).filter((result) => result.status === "fail");
  };

  const allTestCasesMarked = () => {
    return Array.from(executionResults.values()).every(
      (result) => result.status === "pass" || result.status === "fail"
    );
  };

  const handleCreateBugs = async () => {
    const failedCases = getFailedTestCases();
    if (failedCases.length === 0) {
      setBugCreationStatus("No failed test cases to create bugs for.");
      return;
    }

    setCreatingBugs(true);
    setBugCreationStatus("Creating bugs...");

    try {
      const bugsToCreate = failedCases.map((result) => {
        const testCase = testCases.find(
          (tc) => (tc.id || `TC-${testCases.indexOf(tc)}`) === result.testCaseId
        );
        const assignedScreenshots = screenshots.filter((s) =>
          result.screenshotIds?.includes(s.id)
        );

        return {
          testCase: testCase!,
          actualResult: result.actualResult || "",
          screenshots: assignedScreenshots,
        };
      });

      const createdBugIds = await azureDevOpsService.createBugsFromFailedTestCases(
        bugsToCreate,
        userStoryId,
        userStoryTitle
      );

      setBugCreationStatus(
        `Successfully created ${createdBugIds.length} bug(s): ${createdBugIds.join(", ")}`
      );
    } catch (error: any) {
      setBugCreationStatus(`Error creating bugs: ${error.message}`);
      console.error("Error creating bugs:", error);
    } finally {
      setCreatingBugs(false);
    }
  };

  return (
    <div style={{ marginTop: "20px" }}>
      <h2>Test Execution</h2>
      <p>
        Mark each test case as Pass or Fail. For failed test cases, add actual results and
        screenshots.
      </p>

      {/* Screenshot Management Section */}
      <div style={{ marginBottom: "20px", padding: "15px", border: "1px solid #ddd", borderRadius: "5px" }}>
        <h3>Screenshots ({screenshots.length})</h3>
        <div style={{ display: "flex", gap: "10px", marginBottom: "10px", flexWrap: "wrap" }}>
          <button
            onClick={() => fileInputRef.current?.click()}
            style={{
              padding: "8px 15px",
              background: "#0078d4",
              color: "white",
              border: "none",
              borderRadius: "3px",
              cursor: "pointer",
            }}
          >
            Upload Screenshot
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            onChange={handleFileUpload}
            style={{ display: "none" }}
          />
          <div
            ref={pasteAreaRef}
            onPaste={handlePaste}
            style={{
              padding: "10px",
              border: "2px dashed #0078d4",
              borderRadius: "3px",
              cursor: "pointer",
              flex: 1,
              minWidth: "200px",
              textAlign: "center",
            }}
            onFocus={() => pasteAreaRef.current?.focus()}
            tabIndex={0}
          >
            Click here and paste screenshot (Ctrl+V)
          </div>
        </div>

        {screenshots.length > 0 && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))",
              gap: "10px",
              marginTop: "10px",
            }}
          >
            {screenshots.map((screenshot) => (
              <div
                key={screenshot.id}
                style={{
                  position: "relative",
                  border: "1px solid #ddd",
                  borderRadius: "3px",
                  padding: "5px",
                }}
              >
                <img
                  src={screenshot.dataUrl}
                  alt={screenshot.name}
                  style={{
                    width: "100%",
                    height: "100px",
                    objectFit: "cover",
                    borderRadius: "3px",
                  }}
                />
                <div style={{ fontSize: "11px", marginTop: "5px", wordBreak: "break-word" }}>
                  {screenshot.name}
                </div>
                <button
                  onClick={() => removeScreenshot(screenshot.id)}
                  style={{
                    position: "absolute",
                    top: "5px",
                    right: "5px",
                    background: "rgba(220, 53, 69, 0.9)",
                    color: "white",
                    border: "none",
                    borderRadius: "50%",
                    width: "20px",
                    height: "20px",
                    cursor: "pointer",
                    fontSize: "12px",
                  }}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Test Cases Execution */}
      <div style={{ marginBottom: "20px" }}>
        {testCases.map((tc, index) => {
          const testCaseId = tc.id || `TC-${index}`;
          const result = executionResults.get(testCaseId) || {
            testCaseId,
            status: "not_run" as const,
          };
          const isFailed = result.status === "fail";

          return (
            <div
              key={testCaseId}
              style={{
                marginBottom: "15px",
                padding: "15px",
                border: `2px solid ${isFailed ? "#dc3545" : result.status === "pass" ? "#28a745" : "#ddd"}`,
                borderRadius: "5px",
                background: isFailed ? "#fff5f5" : result.status === "pass" ? "#f0fff4" : "#fff",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", marginBottom: "10px" }}>
                <div>
                  <strong>{testCaseId}: {tc.title}</strong>
                  <div style={{ fontSize: "12px", color: "#666", marginTop: "5px" }}>
                    Priority: {tc.priority}
                  </div>
                </div>
                <div style={{ display: "flex", gap: "10px" }}>
                  <button
                    onClick={() => handleStatusChange(testCaseId, "pass")}
                    style={{
                      padding: "5px 15px",
                      background: result.status === "pass" ? "#28a745" : "#fff",
                      color: result.status === "pass" ? "#fff" : "#28a745",
                      border: "1px solid #28a745",
                      borderRadius: "3px",
                      cursor: "pointer",
                      fontWeight: result.status === "pass" ? "bold" : "normal",
                    }}
                  >
                    ✓ Pass
                  </button>
                  <button
                    onClick={() => handleStatusChange(testCaseId, "fail")}
                    style={{
                      padding: "5px 15px",
                      background: result.status === "fail" ? "#dc3545" : "#fff",
                      color: result.status === "fail" ? "#fff" : "#dc3545",
                      border: "1px solid #dc3545",
                      borderRadius: "3px",
                      cursor: "pointer",
                      fontWeight: result.status === "fail" ? "bold" : "normal",
                    }}
                  >
                    ✗ Fail
                  </button>
                </div>
              </div>

              <div style={{ marginTop: "10px", fontSize: "13px" }}>
                <div>
                  <strong>Steps:</strong> {tc.description}
                </div>
                <div style={{ marginTop: "5px" }}>
                  <strong>Expected Result:</strong> {tc.expectedResult}
                </div>
              </div>

              {isFailed && (
                <div style={{ marginTop: "15px", paddingTop: "15px", borderTop: "1px solid #ddd" }}>
                  <label style={{ display: "block", marginBottom: "5px", fontWeight: "bold" }}>
                    Actual Result:
                  </label>
                  <textarea
                    value={result.actualResult || ""}
                    onChange={(e) => handleActualResultChange(testCaseId, e.target.value)}
                    placeholder="Describe what actually happened..."
                    style={{
                      width: "100%",
                      minHeight: "80px",
                      padding: "8px",
                      border: "1px solid #ddd",
                      borderRadius: "3px",
                      fontSize: "13px",
                    }}
                  />

                  {screenshots.length > 0 && (
                    <div style={{ marginTop: "15px" }}>
                      <label style={{ display: "block", marginBottom: "5px", fontWeight: "bold" }}>
                        Assign Screenshots:
                      </label>
                      <div
                        style={{
                          display: "flex",
                          flexWrap: "wrap",
                          gap: "10px",
                          marginTop: "10px",
                        }}
                      >
                        {screenshots.map((screenshot) => {
                          const isAssigned = result.screenshotIds?.includes(screenshot.id);
                          return (
                            <div
                              key={screenshot.id}
                              onClick={() => toggleScreenshotAssignment(testCaseId, screenshot.id)}
                              style={{
                                position: "relative",
                                border: `2px solid ${isAssigned ? "#0078d4" : "#ddd"}`,
                                borderRadius: "3px",
                                padding: "5px",
                                cursor: "pointer",
                                background: isAssigned ? "#e3f2fd" : "#fff",
                              }}
                            >
                              <img
                                src={screenshot.dataUrl}
                                alt={screenshot.name}
                                style={{
                                  width: "100px",
                                  height: "60px",
                                  objectFit: "cover",
                                  borderRadius: "3px",
                                }}
                              />
                              {isAssigned && (
                                <div
                                  style={{
                                    position: "absolute",
                                    top: "5px",
                                    right: "5px",
                                    background: "#0078d4",
                                    color: "white",
                                    borderRadius: "50%",
                                    width: "20px",
                                    height: "20px",
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    fontSize: "12px",
                                  }}
                                >
                                  ✓
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Create Bugs Button */}
      {allTestCasesMarked() && getFailedTestCases().length > 0 && (
        <div style={{ marginTop: "20px", padding: "15px", background: "#f8f9fa", borderRadius: "5px" }}>
          <h3>Create Bugs for Failed Test Cases</h3>
          <p>
            {getFailedTestCases().length} test case(s) failed. Click below to create bugs in Azure
            DevOps.
          </p>
          <button
            onClick={handleCreateBugs}
            disabled={creatingBugs}
            style={{
              padding: "10px 20px",
              background: "#dc3545",
              color: "white",
              border: "none",
              borderRadius: "3px",
              cursor: creatingBugs ? "not-allowed" : "pointer",
              fontSize: "14px",
              fontWeight: "bold",
            }}
          >
            {creatingBugs ? "Creating Bugs..." : `Create ${getFailedTestCases().length} Bug(s)`}
          </button>
          {bugCreationStatus && (
            <div
              style={{
                marginTop: "10px",
                padding: "10px",
                background: bugCreationStatus.includes("Error") ? "#fff5f5" : "#f0fff4",
                border: `1px solid ${bugCreationStatus.includes("Error") ? "#dc3545" : "#28a745"}`,
                borderRadius: "3px",
                color: bugCreationStatus.includes("Error") ? "#dc3545" : "#28a745",
              }}
            >
              {bugCreationStatus}
            </div>
          )}
        </div>
      )}

      {allTestCasesMarked() && getFailedTestCases().length === 0 && (
        <div
          style={{
            marginTop: "20px",
            padding: "15px",
            background: "#f0fff4",
            border: "1px solid #28a745",
            borderRadius: "5px",
            color: "#28a745",
          }}
        >
          ✓ All test cases passed! No bugs to create.
        </div>
      )}
    </div>
  );
};

export default TestExecution;







