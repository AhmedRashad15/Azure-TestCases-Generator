import React, { useState } from "react";
import StoryFetcher from "./StoryFetcher";
import StoryAnalysis from "./StoryAnalysis";
import TestCaseGenerator from "./TestCaseGenerator";
import RichTextEditor from "./RichTextEditor";
import { WorkItem } from "../services/azureDevOpsService";
import "./../styles/index.css";

const App: React.FC = () => {
  const [storyData, setStoryData] = useState<WorkItem | null>(null);
  const [currentWorkItemId, setCurrentWorkItemId] = useState<string>("");
  const [editableAcceptanceCriteria, setEditableAcceptanceCriteria] = useState<string>("");

  const handleStoryFetched = (story: WorkItem) => {
    setStoryData(story);
    setEditableAcceptanceCriteria(story.acceptance_criteria);
  };

  const handleWorkItemIdChange = (id: string) => {
    setCurrentWorkItemId(id);
    if (!id) {
      setStoryData(null);
    }
  };

  return (
    <div className="container">
      <h1>Test Genius - AI Test Case Generator</h1>
      
      <div className="card">
        <h2>1. Fetch User Story</h2>
        <StoryFetcher
          onStoryFetched={handleStoryFetched}
          onWorkItemIdChange={handleWorkItemIdChange}
        />
      </div>

      {storyData && (
        <>
          <div className="card">
            <h2>2. User Story Details</h2>
            <div>
              <label>Title:</label>
              <input type="text" value={storyData.title} readOnly />
              
              <label>Description:</label>
              <textarea value={storyData.description} readOnly />
              
              <label>Acceptance Criteria:</label>
              <RichTextEditor
                value={editableAcceptanceCriteria || storyData.acceptance_criteria}
                onChange={(html) => {
                  setEditableAcceptanceCriteria(html);
                  // Update story data with new acceptance criteria
                  setStoryData({ ...storyData, acceptance_criteria: html });
                }}
                readOnly={false}
                placeholder="Paste acceptance criteria here. You can paste images (screenshots) directly..."
              />
            </div>
          </div>

          <div className="card">
            <h2>2a. Story Analysis</h2>
            <StoryAnalysis storyData={storyData} />
          </div>

          <div className="card">
            <h2>3. Generate Test Cases</h2>
            <TestCaseGenerator
              storyData={storyData}
              workItemId={currentWorkItemId}
            />
          </div>
        </>
      )}
    </div>
  );
};

export default App;

