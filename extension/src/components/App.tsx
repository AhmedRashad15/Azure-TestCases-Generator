import React, { useState } from "react";
import StoryFetcher from "./StoryFetcher";
import StoryAnalysis from "./StoryAnalysis";
import TestCaseGenerator from "./TestCaseGenerator";
import TestExecution from "./TestExecution";
import RichTextEditor from "./RichTextEditor";
import { WorkItem, TestCase } from "../services/azureDevOpsService";
import "./../styles/index.css";

const App: React.FC = () => {
  const [storyData, setStoryData] = useState<WorkItem | null>(null);
  const [currentWorkItemId, setCurrentWorkItemId] = useState<string>("");
  const [editableAcceptanceCriteria, setEditableAcceptanceCriteria] = useState<string>("");
  const [generatedTestCases, setGeneratedTestCases] = useState<TestCase[]>([]);

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
              <RichTextEditor
                value={storyData.description}
                onChange={(html) => {
                  // Update story data with new description
                  setStoryData({ ...storyData, description: html });
                }}
                readOnly={false}
                placeholder="Enter story description..."
              />
              
              <label>Acceptance Criteria:</label>
              <RichTextEditor
                value={editableAcceptanceCriteria || storyData.acceptance_criteria}
                onChange={(html) => {
                  setEditableAcceptanceCriteria(html);
                  // Update story data with new acceptance criteria
                  setStoryData({ ...storyData, acceptance_criteria: html });
                }}
                readOnly={false}
                placeholder="Enter acceptance criteria..."
              />
            </div>
          </div>

          {storyData.related_stories && storyData.related_stories.length > 0 && (
            <div className="card">
              <h2>2b. Related User Stories</h2>
              <div style={{ marginTop: "10px" }}>
                {storyData.related_stories.map((relatedStory, index) => (
                  <div
                    key={relatedStory.id || index}
                    style={{
                      border: "1px solid #dee2e6",
                      borderRadius: "6px",
                      padding: "15px",
                      marginBottom: "15px",
                      backgroundColor: "#fafbfc",
                    }}
                  >
                    <h3 style={{ marginTop: "0", marginBottom: "10px" }}>
                      {relatedStory.title} {relatedStory.id && `(ID: ${relatedStory.id})`}
                    </h3>
                    
                    <div style={{ marginBottom: "15px" }}>
                      <label style={{ fontWeight: "bold", display: "block", marginBottom: "5px" }}>
                        Description:
                      </label>
                      <RichTextEditor
                        value={relatedStory.description}
                        onChange={(html) => {
                          // Update related story description
                          const updatedRelatedStories = [...(storyData.related_stories || [])];
                          updatedRelatedStories[index] = {
                            ...updatedRelatedStories[index],
                            description: html,
                          };
                          setStoryData({ ...storyData, related_stories: updatedRelatedStories });
                        }}
                        readOnly={false}
                        placeholder="Related story description..."
                      />
                    </div>
                    
                    <div>
                      <label style={{ fontWeight: "bold", display: "block", marginBottom: "5px" }}>
                        Acceptance Criteria:
                      </label>
                      <RichTextEditor
                        value={relatedStory.acceptance_criteria}
                        onChange={(html) => {
                          // Update related story acceptance criteria
                          const updatedRelatedStories = [...(storyData.related_stories || [])];
                          updatedRelatedStories[index] = {
                            ...updatedRelatedStories[index],
                            acceptance_criteria: html,
                          };
                          setStoryData({ ...storyData, related_stories: updatedRelatedStories });
                        }}
                        readOnly={false}
                        placeholder="Related story acceptance criteria..."
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="card">
            <h2>2a. Story Analysis</h2>
            <StoryAnalysis storyData={storyData} />
          </div>

          <div className="card">
            <h2>3. Generate Test Cases</h2>
            <TestCaseGenerator
              storyData={storyData}
              workItemId={currentWorkItemId}
              onTestCasesGenerated={setGeneratedTestCases}
            />
          </div>

          {generatedTestCases.length > 0 && (
            <div className="card">
              <h2>4. Execute Test Cases & Create Bugs</h2>
              <TestExecution
                testCases={generatedTestCases}
                userStoryId={currentWorkItemId}
                userStoryTitle={storyData.title}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default App;

