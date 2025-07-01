// DOM Elements
const fetchStoryBtn = document.getElementById('fetch-story-btn');
const generateCasesBtn = document.getElementById('generate-cases-btn');
const uploadCasesBtn = document.getElementById('upload-cases-btn');

const storyDetails = document.getElementById('story-details');
const testCasesSection = document.getElementById('test-cases-section');
const loadingStory = document.getElementById('loading-story');
const loadingGenerator = document.getElementById('loading-generator');
const generationStatus = document.getElementById('generation-status');
const testCasesOutput = document.getElementById('test-cases-output');
const uploadStatus = document.getElementById('upload-status');
const relatedStoriesSection = document.getElementById('related-stories-section');
const relatedStoriesList = document.getElementById('related-stories-list');
const storyDetailsCard = document.getElementById('story-details-card');
const testCasesCard = document.getElementById('test-cases-section');

// Global state
let allTestCases = [];
let fetchedStoryData = null; // Store fetched story data globally

// Event Listeners
document.addEventListener('DOMContentLoaded', function() {
    // Disable buttons that require a story to be fetched first
    generateCasesBtn.disabled = true;
    uploadCasesBtn.disabled = true;
});

fetchStoryBtn.addEventListener('click', async function() {
    const storyId = document.getElementById('story-id').value;
    const orgUrl = document.getElementById('azure-devops-org-url').value;
    const projectName = document.getElementById('azure-devops-project-name').value;
    const pat = document.getElementById('azure-devops-pat').value;

    if (!storyId || !orgUrl || !projectName || !pat) {
        alert('Please fill in all Azure DevOps details and the User Story ID.');
        return;
    }

    // Show loading spinner for story fetching
    loadingStory.classList.remove('hidden');
    storyDetails.classList.add('hidden');
    relatedStoriesSection.classList.add('hidden');
    storyDetailsCard.classList.add('hidden');
    testCasesCard.classList.add('hidden');
    generateCasesBtn.disabled = true;
    
    try {
        const response = await fetch('/fetch_story', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                story_id: storyId,
                azure_devops_org_url: orgUrl,
                azure_devops_project_name: projectName,
                azure_devops_pat: pat
            }),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to fetch user story.');
        }

        const data = await response.json();
        fetchedStoryData = data; // Store data globally
        
        // Populate the read-only fields
        document.getElementById('story-title').value = data.title;
        document.getElementById('story-description').value = data.description;
        document.getElementById('acceptance-criteria').value = data.acceptance_criteria;

        // Populate related stories
        relatedStoriesList.innerHTML = ''; // Clear previous
        if (data.related_stories && data.related_stories.length > 0) {
            data.related_stories.forEach(story => {
                const storyElement = document.createElement('div');
                storyElement.className = 'related-story-item';
                storyElement.innerHTML = `
                    <div class="related-story-header">
                        <input type="checkbox" class="related-story-checkbox" data-story-id="${story.id}" checked>
                        <strong contenteditable="true" class="related-story-title">${story.title}</strong>
                    </div>
                    <div class="related-story-details">
                        <label>Description:</label>
                        <div contenteditable="true" class="related-story-description">${story.description}</div>
                        <label>Acceptance Criteria:</label>
                        <div contenteditable="true" class="related-story-ac">${story.acceptance_criteria}</div>
                    </div>
                `;
                relatedStoriesList.appendChild(storyElement);
            });
            relatedStoriesSection.classList.remove('hidden');
        }

        // Show the story details and enable the generate button
        storyDetails.classList.remove('hidden');
        storyDetailsCard.classList.remove('hidden');
        generateCasesBtn.disabled = false;
        
    } catch (error) {
        alert('Error: ' + error.message);
    } finally {
        // Hide loading spinner
        loadingStory.classList.add('hidden');
    }
});

generateCasesBtn.addEventListener('click', generateTestCases);
uploadCasesBtn.addEventListener('click', uploadTestCases);

// Functions
async function generateTestCases() {
    loadingGenerator.classList.remove('hidden');
    document.querySelector('.spinner').style.display = 'inline-block';
    document.getElementById('generation-success').style.display = 'none';
    generationStatus.textContent = 'Generating...';
    generateCasesBtn.disabled = true;
    testCasesSection.classList.add('hidden');
    allTestCases = []; // Reset test cases
    renderAllTestCases();

    const storyTitle = document.getElementById('story-title').value;
    const storyDescription = document.getElementById('story-description').value;
    const acceptanceCriteria = document.getElementById('acceptance-criteria').value;
    const dataDictionary = document.getElementById('data-dictionary').value;

    if (!storyTitle || !acceptanceCriteria) {
        alert('Story Title and Acceptance Criteria are required.');
        loadingGenerator.classList.add('hidden');
        generateCasesBtn.disabled = false;
        return;
    }

    // Collect selected and edited related stories from the DOM
    const relatedCheckboxes = document.querySelectorAll('.related-story-checkbox');
    let selectedRelated = [];
    relatedCheckboxes.forEach((cb) => {
        if (cb.checked) {
            const item = cb.closest('.related-story-item');
            const title = item.querySelector('.related-story-title').innerText;
            const description = item.querySelector('.related-story-description').innerText;
            const ac = item.querySelector('.related-story-ac').innerText;
            selectedRelated.push({ title, description, acceptance_criteria: ac });
        }
    });
    
    const payload = {
        story_title: storyTitle,
        story_description: storyDescription,
        acceptance_criteria: acceptanceCriteria,
        data_dictionary: dataDictionary,
        related_stories: selectedRelated
    };

    // Use EventSource for streaming
    const eventSource = new EventSource(`/generate_test_cases?payload=${encodeURIComponent(JSON.stringify(payload))}`);

    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);

        if (data.type === 'done') {
            generationStatus.textContent = '';
            document.querySelector('.spinner').style.display = 'none';
            document.getElementById('generation-success').style.display = 'flex';
            eventSource.close();
            
            setTimeout(function() {
                loadingGenerator.classList.add('hidden');
                // Reset for next time
                document.querySelector('.spinner').style.display = 'inline-block'; 
                document.getElementById('generation-success').style.display = 'none';
                generationStatus.textContent = 'Generating...';
            }, 2000);

            generateCasesBtn.disabled = false;
            if (allTestCases.length > 0) {
                uploadCasesBtn.disabled = false;
            }

        } else if (data.cases && Array.isArray(data.cases)) {
            allTestCases.push(...data.cases);
            renderAllTestCases();
            generationStatus.textContent = data.progress || 'Generating...';
        }
    };

    eventSource.onerror = function(err) {
        console.error("EventSource failed:", err);
        alert("An error occurred during test case generation. Please check the console.");
        loadingGenerator.classList.add('hidden');
        generateCasesBtn.disabled = false;
        eventSource.close();
    };
}


function renderAllTestCases() {
    testCasesOutput.innerHTML = '';
    if (allTestCases.length === 0) {
        testCasesSection.classList.add('hidden');
        return;
    }
    
    testCasesSection.classList.remove('hidden');
    testCasesCard.classList.remove('hidden');

    const caseGroups = {
        "Positive": [],
        "Negative": [],
        "Edge Case": [],
        "Data Flow": []
    };

    // Group test cases by type based on their ID prefix
    allTestCases.forEach(tc => {
        const id = (tc.id || '').toUpperCase();
        if (id.startsWith('TC-POS')) caseGroups["Positive"].push(tc);
        else if (id.startsWith('TC-NEG')) caseGroups["Negative"].push(tc);
        else if (id.startsWith('TC-EDGE')) caseGroups["Edge Case"].push(tc);
        else if (id.startsWith('TC-DF')) caseGroups["Data Flow"].push(tc);
    });

    // Render each group
    for (const [groupName, cases] of Object.entries(caseGroups)) {
        if (cases.length > 0) {
            const groupContainer = document.createElement('div');
            groupContainer.className = 'test-case-group';
            
            const groupTitle = document.createElement('h3');
            groupTitle.textContent = `${groupName} Test Cases (${cases.length})`;
            groupContainer.appendChild(groupTitle);

            cases.forEach(tc => {
                const accordion = createTestCaseAccordion(tc);
                groupContainer.appendChild(accordion);
            });
            
            testCasesOutput.appendChild(groupContainer);
        }
    }
    uploadCasesBtn.disabled = allTestCases.length === 0;
}

function createTestCaseAccordion(tc) {
    const container = document.createElement('div');
    container.className = 'accordion-container';

    const header = document.createElement('div');
    header.className = 'accordion-header';
    header.innerHTML = `
        <div class="title-group">
            <strong>${tc.title}</strong>
            <span>(Priority: ${tc.priority})</span>
        </div>
        <div class="actions">
            <button class="btn-sm btn-danger" onclick="deleteTestCase('${tc.id}')">Delete</button>
        </div>
    `;

    const content = document.createElement('div');
    content.className = 'accordion-content';
    
    // Safely format description and expected result
    const formatSteps = (steps) => {
        if (!steps) return '<p>N/A</p>';
        try {
            // Check if it's a stringified array
            if (typeof steps === 'string' && steps.startsWith('[') && steps.endsWith(']')) {
                steps = JSON.parse(steps);
            }
            if (Array.isArray(steps)) {
                return steps.map(step => `<p>${step}</p>`).join('');
            }
            // If it's just a string with newlines
            return steps.split('\n').map(line => `<p>${line}</p>`).join('');
        } catch(e) {
            // Fallback for simple strings or malformed JSON
            return `<p>${steps}</p>`;
        }
    };
    
    content.innerHTML = `
        <div class="readonly-content">
            <label>Description / Steps:</label>
            ${formatSteps(tc.description)}
            <label style="margin-top: 1em;">Expected Result:</label>
            <p>${tc.expectedResult || 'N/A'}</p>
        </div>
    `;
    
    header.addEventListener('click', (e) => {
        if (e.target.classList.contains('btn-danger')) {
            return; // Don't toggle accordion if delete button is clicked
        }
        content.classList.toggle('show');
    });

    container.appendChild(header);
    container.appendChild(content);

    return container;
}


function deleteTestCase(testCaseId) {
    allTestCases = allTestCases.filter(tc => tc.id !== testCaseId);
    renderAllTestCases();
    // Optional: add a confirmation
    console.log(`Deleted test case: ${testCaseId}`);
}

async function uploadTestCases() {
    const testPlanId = document.getElementById('test-plan-id').value;
    const testSuiteId = document.getElementById('test-suite-id').value;
    const orgUrl = document.getElementById('azure-devops-org-url').value;
    const projectName = document.getElementById('azure-devops-project-name').value;
    const pat = document.getElementById('azure-devops-pat').value;

    if (!testPlanId || !testSuiteId) {
        alert('Test Plan ID and Test Suite ID are required for upload.');
        return;
    }

    uploadCasesBtn.disabled = true;
    uploadStatus.textContent = 'Uploading...';
    uploadStatus.style.color = 'var(--text-color)';
    uploadStatus.classList.remove('hidden');

    try {
        const response = await fetch('/upload_test_cases', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                test_plan_id: testPlanId,
                test_suite_id: testSuiteId,
                test_cases: JSON.stringify(allTestCases), // Send the current list
                azure_devops_org_url: orgUrl,
                azure_devops_project_name: projectName,
                azure_devops_pat: pat
            }),
        });

        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.error || 'Unknown error during upload.');
        }

        uploadStatus.textContent = result.message || 'Upload complete!';
        uploadStatus.style.color = 'var(--success-color)';
        
    } catch (error) {
        uploadStatus.textContent = 'Error: ' + error.message;
        uploadStatus.style.color = 'var(--error-color)';
    } finally {
        uploadCasesBtn.disabled = allTestCases.length === 0;
    }
} 