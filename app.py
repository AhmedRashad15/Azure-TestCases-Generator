import os
from flask import Flask, render_template, request, jsonify, Response
from dotenv import load_dotenv
import google.generativeai as genai
from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
import json
import re
from bs4 import BeautifulSoup
from urllib.parse import unquote
import ast
import html
import unicodedata
import string

# Load environment variables from .env file
load_dotenv()

# --- Configure Gemini API ---
# Create a .env file in your project root and add your Gemini API key:
# GEMINI_API_KEY="YOUR_NEW_SECRET_API_KEY"
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    raise ValueError("GEMINI_API_KEY not found in .env file")
genai.configure(api_key=gemini_api_key)

# --- Azure DevOps Configuration ---
# The user will now provide these details in the UI.
# We will get them from the request body in each endpoint.

# --- Flask App ---
app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/fetch_story', methods=['POST'])
def fetch_story():
    print("fetch_story called")
    data = request.json or {}
    story_id = data.get('story_id')
    azure_devops_org_url = data.get('azure_devops_org_url')
    azure_devops_project_name = data.get('azure_devops_project_name')
    azure_devops_pat = data.get('azure_devops_pat')

    if not all([story_id, azure_devops_org_url, azure_devops_project_name, azure_devops_pat]):
        return jsonify({'error': 'Azure DevOps details and User Story ID are required.'}), 400

    try:
        print("About to fetch work item")
        credentials = BasicAuthentication('', azure_devops_pat or '')
        connection = Connection(base_url=azure_devops_org_url, creds=credentials)
        work_item_tracking_client = connection.get_client('azure.devops.v7_1.work_item_tracking.work_item_tracking_client.WorkItemTrackingClient')
        
        work_item = work_item_tracking_client.get_work_item(id=story_id, project=azure_devops_project_name, expand='All')
        
        fields = work_item.fields
        
        # Description and Acceptance Criteria can be HTML, so we parse them to get plain text.
        description_html = fields.get('System.Description', '')
        acceptance_criteria_html = fields.get('Microsoft.VSTS.Common.AcceptanceCriteria', '')
        
        description_text = BeautifulSoup(description_html, "html.parser").get_text(separator="\n").strip()
        acceptance_criteria_text = BeautifulSoup(acceptance_criteria_html, "html.parser").get_text(separator="\n").strip()

        # Fetch related user stories (work item links)
        related_stories = []
        if hasattr(work_item, 'relations'):
            for rel in work_item.relations:
                if rel.rel in ["System.LinkTypes.Related", "System.LinkTypes.Hierarchy-Forward", "System.LinkTypes.Hierarchy-Reverse"]:
                    url = rel.url
                    related_id = url.split('/')[-1]
                    try:
                        related_item = work_item_tracking_client.get_work_item(id=related_id, project=azure_devops_project_name, expand='All')
                        r_fields = related_item.fields
                        if r_fields.get('System.WorkItemType', '') != 'User Story':
                            continue
                        r_title = r_fields.get('System.Title', '')
                        r_desc_html = r_fields.get('System.Description', '')
                        r_ac_html = r_fields.get('Microsoft.VSTS.Common.AcceptanceCriteria', '')
                        r_desc = BeautifulSoup(r_desc_html, "html.parser").get_text(separator="\n").strip()
                        r_ac = BeautifulSoup(r_ac_html, "html.parser").get_text(separator="\n").strip()
                        related_stories.append({
                            'id': related_id,
                            'title': r_title,
                            'description': r_desc,
                            'acceptance_criteria': r_ac
                        })
                    except Exception as e:
                        continue

        story_details = {
            'title': fields.get('System.Title', ''),
            'description': description_text,
            'acceptance_criteria': acceptance_criteria_text,
            'related_stories': related_stories
        }
        return jsonify(story_details)
    except Exception as e:
        print("Exception occurred in fetch_story:", e)
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            print("Azure DevOps response body:", e.response.text)
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def _generate_cases_for_type(model, story_title, story_description, acceptance_criteria, data_dictionary, case_type, related_stories=None):
    print(f"DEBUG: _generate_cases_for_type called for {case_type}. related_stories:", related_stories)
    guideline_map = {
        "Positive": """
**Positive Test Case Guidelines:**
- Verify the core functionality works as expected under normal conditions.
- Cover all acceptance criteria with at least one positive test case.
- Test each valid input scenario from the data dictionary separately.
- **Title Examples:** "[Positive] User successfully creates account with valid information", "[Positive] System saves data when all required fields are completed".""",
        "Negative": """
**Negative Test Case Guidelines:**
- Test scenarios where inputs are invalid, missing, or unexpected.
- Create SEPARATE test cases for each type of invalid input.
- Verify that appropriate error messages are displayed when failures occur.
- **Title Examples:** "[Negative] System shows error when email field is empty", "[Negative] Application prevents login with invalid password format".""",
        "Edge Case": """
**Edge Case & Boundary Guidelines:**
- Test boundary conditions from the data dictionary (min/max values, etc.).
- Include scenarios with unexpected user behavior or timing.
- Test performance under special circumstances (e.g., large data sets, slow networks).
- **Title Examples:** "[Edge Case] System handles maximum character limit in description field", "[Edge Case] Application maintains functionality during network interruption".""",
        "Data Flow": """
**Data Flow Guidelines:**
- Verify how data moves through the system from input to storage and output.
- Track data through an entire workflow to verify integrity.
- Test data persistence (saving) and retrieval (loading).
- **Title Examples:** "[Data Flow] User data persists correctly through complete registration workflow", "[Data Flow] System maintains data integrity when transferring between modules"."""
    }
    
    specific_guidelines = guideline_map.get(case_type, "- Follow standard best practices for this test type.")
    related_block = ""
    if related_stories and len(related_stories) > 0:
        related_instruction = "When generating test cases, take into account not only the main user story but also the context and requirements described in the related user stories below."
        related_block = f"\n**Instruction:** {related_instruction}\n**Related User Stories:**\n" + "\n".join([
            f"- Title: {r.get('title', '')}\n  Description: {r.get('description', '')}\n  Acceptance Criteria: {r.get('acceptance_criteria', '')}" for r in related_stories
        ])
    prompt = f"""
You are an expert test case generator for Azure DevOps with a focus on comprehensive test coverage. Your task is to generate a JSON array of ONLY the **{case_type}** test cases for the user story below.

**User Story Details:**
- **Title:** {story_title}
- **Description:** {story_description}
- **Acceptance Criteria:** {acceptance_criteria}
- **Data Dictionary:** {data_dictionary}
{related_block}

**Universal Guidelines:**
1. **Descriptive Titles:** Create specific, action-oriented titles that clearly describe what functionality is being tested. Avoid generic titles like "Test login" - instead use "User can successfully login with valid email and password".
2. **Consistency First:** For any '{case_type}' test, the `title`, `description`, and `expectedResult` must all be consistent with that scenario. For example, a 'Negative' test's title must describe a failure condition, and its expected result must describe the correct error handling.
3. **Single Condition:** Each test case must focus on verifying exactly ONE condition or scenario. Do not combine multiple test conditions.

**Mobile Application Guidelines (Apply if context is a mobile app):**
- If a scenario applies to both iOS and Android, write a single, consolidated test case.
- Create separate, platform-specific test cases ONLY for behaviors that differ (e.g., native UI, permissions).
- Prefix platform-specific titles with `[iOS]` or `[Android]`.
- Assume only one iOS and one Android device are available. Do not create tests requiring multiple devices of the same platform.
- Include mobile-specific edge cases: network interruptions, orientation changes, notifications, permissions, etc.

{specific_guidelines}

**JSON Output Format:**
Each test case in the JSON array must have the following fields:
- `id`: A unique identifier following the convention for the test type (e.g., "TC-POS-1", "TC-NEG-1").
- `title`: A clear and descriptive title that specifically describes what is being tested. The title should:
  * Be concise but descriptive (aim for 60-100 characters)
  * Clearly indicate the specific functionality or scenario being tested
  * Include the type of test in brackets (e.g., "[Positive]", "[Negative]", "[Edge Case]", "[Data Flow]")
  * Use action-oriented language that describes the expected behavior
  * Examples: "[Positive] User can successfully login with valid credentials", "[Negative] System displays error when required field is empty", "[Edge Case] Application handles maximum character limit in text field"
- `priority`: "High", "Medium", or "Low".
- `description`: A numbered list of steps, e.g., "1. Step one.\\n2. Step two.".
- `expectedResult`: A specific and verifiable outcome.

**ID Naming Convention:**
- Positive cases: `TC-POS-[number]`
- Negative cases: `TC-NEG-[number]`
- Edge cases: `TC-EDGE-[number]`
- Data flow cases: `TC-DF-[number]`

Now, generate ONLY the `{case_type}` test cases based on all these instructions.

- Do not generate duplicate test cases. Each test case must be unique in its condition, steps, and expected result.
"""
    try:
        response = model.generate_content(prompt)
        print(f"Raw Gemini response for {case_type}:\n{response.text}\n--- End Response ---\n")
        # Clean the response to get a clean JSON array string
        clean_json_text = response.text.strip().replace('```json', '').replace('```', '').strip()
        return clean_json_text
    except Exception as e:
        import traceback
        print(f"Error generating {case_type} cases: {e}")
        traceback.print_exc()
        return "[]" # Return an empty array on error

@app.route('/generate_test_cases', methods=['GET'])
def generate_test_cases_stream():
    print("DEBUG: /generate_test_cases endpoint called.")
    # Payload is now sent as a URL parameter
    payload_str = request.args.get('payload')
    if not payload_str:
        return Response("Payload missing.", status=400)
    
    data = json.loads(unquote(payload_str))

    story_title = data.get('story_title')
    story_description = data.get('story_description', '')
    acceptance_criteria = data.get('acceptance_criteria')
    data_dictionary = data.get('data_dictionary', '')
    related_stories = data.get('related_stories', [])

    print("DEBUG: related_stories received in endpoint:", related_stories)

    if not all([story_title, acceptance_criteria]):
        return Response("Story Title and Acceptance Criteria are required.", status=400)

    model = genai.GenerativeModel('gemini-flash-latest')
    
    def generate():
        case_types = ["Positive", "Negative", "Edge Case", "Data Flow"]
        all_test_cases = []

        for case_type in case_types:
            print(f"DEBUG: Calling _generate_cases_for_type for {case_type} with related_stories:", related_stories)
            # Generate cases for the current type
            json_text_chunk = _generate_cases_for_type(model, story_title, story_description, acceptance_criteria, data_dictionary, case_type, related_stories)
            
            # The API might return an empty or invalid string, so we validate it
            try:
                # Validate if it's proper JSON
                parsed_chunk = json.loads(json_text_chunk)
                if isinstance(parsed_chunk, list) and parsed_chunk:
                    all_test_cases.extend(parsed_chunk)
                    # Stream the current progress back to the client
                    progress_data = {
                        "type": case_type,
                        "cases": parsed_chunk,
                        "progress": f"Generated {len(parsed_chunk)} {case_type} cases."
                    }
                    yield f"data: {json.dumps(progress_data)}\n\n"
            except json.JSONDecodeError:
                print(f"Warning: Could not decode JSON for {case_type} cases. Skipping.")
                continue
        
        print("--- Finished generating all test cases. ---")
        yield "data: {\"type\": \"done\", \"message\": \"All test cases generated.\"}\n\n"

    return Response(generate(), mimetype='text/event-stream')

@app.route('/upload_test_cases', methods=['POST'])
def upload_test_cases():
    data = request.json or {}
    test_plan_id = data.get('test_plan_id')
    test_suite_id = data.get('test_suite_id')
    test_cases_str = data.get('test_cases')
    azure_devops_org_url = data.get('azure_devops_org_url')
    azure_devops_project_name = data.get('azure_devops_project_name')
    azure_devops_pat = data.get('azure_devops_pat')

    if not all([test_plan_id, test_suite_id, test_cases_str, azure_devops_org_url, azure_devops_project_name, azure_devops_pat]):
        return jsonify({'error': 'All fields, including Azure DevOps details, are required.'}), 400

    try:
        test_cases = json.loads(test_cases_str or '[]')
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON format for test cases.'}), 400

    # De-duplicate test cases by normalized final title (after all processing)
    unique_test_cases = []
    seen_titles = set()
    for tc in test_cases:
        title_from_ai = (tc.get('title') or '').strip()
        # Remove test type prefixes if present
        prefix_pattern = r'^\s*\[(Positive|Negative|Edge Case|Data Flow)\]\s*'
        title_without_prefix = re.sub(prefix_pattern, '', title_from_ai, flags=re.IGNORECASE).strip()
        if not title_without_prefix:
            # fallback logic (first step, expected result, etc.)
            description_raw = tc.get('description', '')
            expected_result_raw = tc.get('expectedResult', '')
            title_without_prefix = ''
            if isinstance(description_raw, list):
                first_step = next((s for s in description_raw if isinstance(s, str) and s.strip()), None)
                if first_step:
                    title_without_prefix = re.sub(r'^\s*\d+\.\s*', '', first_step.strip()).strip()
            elif isinstance(description_raw, str) and description_raw.strip():
                first_line = description_raw.strip().split('\n')[0].strip()
                title_without_prefix = re.sub(r'^\s*\d+\.\s*', '', first_line).strip()
            if not title_without_prefix and isinstance(expected_result_raw, str) and expected_result_raw.strip():
                title_without_prefix = f"Test for: {expected_result_raw.strip()}"
            if not title_without_prefix:
                title_without_prefix = "Untitled Test Case"
        # Truncate if needed
        final_title_base = (title_without_prefix[:120] + '...') if len(title_without_prefix) > 120 else title_without_prefix
        if not final_title_base.lower().startswith('verify'):
            final_title = "Verify " + final_title_base
        else:
            final_title = final_title_base
        print(f"Final constructed title: {final_title}")
        norm_title = normalize_title(final_title)
        if norm_title and norm_title not in seen_titles:
            tc['title'] = final_title
            unique_test_cases.append(tc)
            seen_titles.add(norm_title)

    try:
        credentials = BasicAuthentication('', azure_devops_pat or '')
        connection = Connection(base_url=azure_devops_org_url, creds=credentials)
        work_item_tracking_client = connection.get_client('azure.devops.v7_1.work_item_tracking.work_item_tracking_client.WorkItemTrackingClient')
        test_plan_client = connection.get_client('azure.devops.v7_1.test_plan.test_plan_client.TestPlanClient')

        created_test_case_ids = []
        for tc in unique_test_cases:
            final_title = tc.get('title', '').strip()
            description_raw = tc.get('description', '')
            expected_result_raw = tc.get('expectedResult', '')
            # 4. Map text priority to integer value
            priority_input = tc.get('priority', 'Medium')
            priority_text = str(priority_input).lower().strip()
            priority_map = {
                'critical': 1, '1': 1,
                'high': 2, '2': 2,
                'medium': 3, '3': 3,
                'low': 4, '4': 4
            }
            priority_value = priority_map.get(priority_text, 3) # Default to Medium (3)
            # 5. Format the Test Case Steps into XML
            steps_list = []
            if isinstance(description_raw, list):
                steps_list = description_raw
            elif isinstance(description_raw, str) and description_raw.strip():
                if description_raw.strip().startswith('[') and description_raw.strip().endswith(']'):
                    try:
                        steps_list = ast.literal_eval(description_raw.strip())
                    except:
                        steps_list = [s.strip() for s in description_raw.split('\n') if s.strip()]
                else:
                    steps_list = [s.strip() for s in description_raw.split('\n') if s.strip()]
            steps_list = [str(s) for s in steps_list if s]
            steps_xml_parts = []
            # Case 1: No description, but there is an expected result
            if not steps_list and expected_result_raw:
                action_text = "Execute test steps"
                expected_text = html.escape(str(expected_result_raw))
                steps_xml_parts.append(
                    "<step id='1' type='ActionStep'>"
                    f"<parameterizedString isformatted='true'>{action_text}</parameterizedString>"
                    f"<parameterizedString isformatted='true'>{expected_text}</parameterizedString>"
                    "</step>"
                )
            elif steps_list:
                step_count = len(steps_list)
                for i, step_action in enumerate(steps_list, 1):
                    cleaned_action = re.sub(r'^\s*\d+\.\s*', '', str(step_action)).strip()
                    action_text = html.escape(cleaned_action)
                    expected_text_for_step = ""
                    if i == step_count and expected_result_raw:
                        expected_text_for_step = html.escape(str(expected_result_raw))
                    steps_xml_parts.append(
                        f"<step id='{i}' type='ActionStep'>"
                        f"<parameterizedString isformatted='true'>{action_text}</parameterizedString>"
                        f"<parameterizedString isformatted='true'>{expected_text_for_step}</parameterizedString>"
                        "</step>"
                    )
            step_count = len(steps_xml_parts)
            steps_xml = f"<steps id='0' last='{step_count}'>" + ''.join(steps_xml_parts) + "</steps>" if step_count > 0 else ""
            # 6. Create the Test Case Work Item patch document
            patch_document = [
                {"op": "add", "path": "/fields/System.Title", "value": final_title},
                {"op": "add", "path": "/fields/Microsoft.VSTS.Common.Priority", "value": priority_value},
            ]
            # Only add the steps field if we have some steps to add.
            if steps_xml:
                patch_document.append(
                    {"op": "add", "path": "/fields/Microsoft.VSTS.TCM.Steps", "value": steps_xml}
                )
            created_work_item = work_item_tracking_client.create_work_item(
                document=patch_document,
                project=azure_devops_project_name,
                type="Test Case"
            )
            created_test_case_ids.append(created_work_item.id)

        # 2. Add Test Cases to Test Suite
        test_cases_to_add = [{"workItem": {"id": tc_id}} for tc_id in created_test_case_ids]
        test_plan_client.add_test_cases_to_suite(
            project=azure_devops_project_name,
            plan_id=int(test_plan_id or 0),
            suite_id=int(test_suite_id or 0),
            suite_test_case_create_update_parameters=test_cases_to_add
        )

        return jsonify({'message': f'Successfully uploaded {len(created_test_case_ids)} test cases.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def normalize_title(title):
    # Remove all whitespace, lowercase, strip punctuation, and normalize unicode
    title = ''.join(title.split()).lower()
    title = ''.join(ch for ch in title if ch not in string.punctuation)
    title = unicodedata.normalize('NFKD', title)
    title = ''.join(ch for ch in title if not unicodedata.category(ch).startswith('C'))  # Remove control chars
    return title

@app.route('/analyze_story', methods=['POST'])
def analyze_story():
    """Analyze a user story and provide structured review"""
    print("DEBUG: /analyze_story endpoint called")
    try:
        data = request.json or {}
        print(f"DEBUG: Request data keys: {data.keys() if data else 'None'}")
        
        story_title = data.get('story_title')
        story_description = data.get('story_description', '')
        acceptance_criteria = data.get('acceptance_criteria', '')
        related_test_cases = data.get('related_test_cases', '')
        
        print(f"DEBUG: Story title: {story_title}")
        print(f"DEBUG: Story description length: {len(story_description)}")
        print(f"DEBUG: Acceptance criteria length: {len(acceptance_criteria)}")
        
        if not story_title:
            print("ERROR: Story title is missing")
            return jsonify({'error': 'Story Title is required.'}), 400
        
        model = genai.GenerativeModel('gemini-flash-latest')
        
        # Build the prompt for analysis
        test_cases_section = ""
        if related_test_cases:
            test_cases_section = f"\n\n**RELATED TEST CASES (if available):**\n{related_test_cases}"
        
        prompt = f"""You are an experienced software analyst and product owner assistant.

Your task is to review the following user story (and related test cases if available) and produce a simple, actionable, and UI-ready output for the development team.

**USER STORY:**
**Title:** {story_title}
**Description:** {story_description}
**Acceptance Criteria:** {acceptance_criteria}
{test_cases_section}

Please analyze and respond using the structure below.

---

### 🟦 1. User Story Summary
Provide a short, simple summary (2–3 sentences) describing the purpose of the user story.  
If related stories exist, mention their connection briefly.

---

### 🟩 2. Key Functional Points
List the main actions, goals, or behaviors that this user story describes.  
Keep these as **short, clear bullet points**.

---

### 🟨 3. Ambiguities & Clarification Questions
Identify any unclear, missing, or ambiguous parts of the user story.  
For each one, provide:
- **Ambiguity:** short description of what's unclear  
- **Question:** the specific question that should be asked to the Product Owner to clarify this

Keep this section clear and easy to read — one ambiguity and one question per bullet point.

---

### 🟧 4. Recommendations
Provide 2–4 short, actionable suggestions to make the story clearer, more complete, or easier to test.

---

### 🎨 UI Rendering Guidelines
Return your final output formatted as **HTML** (not markdown), following these visual and structural rules:

- Each section should be wrapped in a `<div>` with a unique color-coded header:
  - **1. Summary:** Blue header (`#0078D7`)
  - **2. Key Functional Points:** Green header (`#28a745`)
  - **3. Ambiguities & Questions:** Yellow header (`#ffc107`)
  - **4. Recommendations:** Orange header (`#fd7e14`)
- Headers must have **bold white text**, padding (8px), and rounded corners.
- Each bullet point should use:
  - **Bold labels** (like "Ambiguity:" / "Question:")
  - Alternating font colors for readability:
    - Header text: white
    - Content text: dark gray (`#333`)
    - Key terms/questions: navy blue (`#004080`)
- Wrap all sections inside a main `<div class="review-container">` with:
  - Light background (`#f9f9f9`)
  - Padding: 15px
  - Border-radius: 8px
  - Small shadow for readability
- Use semantic HTML: `<h2>` for headers, `<ul>` and `<li>` for lists, `<b>` for key labels.
- Keep the text short and easy to scan — avoid long paragraphs.

Here is the preferred HTML structure template (use this for formatting your response):

```html
<div class="review-container">
  <h2 class="header blue">1. User Story Summary</h2>
  <p>This story allows users to reset their password using an email link...</p>

  <h2 class="header green">2. Key Functional Points</h2>
  <ul>
    <li><b>Reset Password:</b> User can trigger password reset via email.</li>
    <li><b>Validation:</b> Check if the email exists before sending reset link.</li>
  </ul>

  <h2 class="header yellow">3. Ambiguities & Clarification Questions</h2>
  <ul>
    <li><b>Ambiguity:</b> No email content defined.<br>
        <b>Question:</b> What should the reset email include?</li>
    <li><b>Ambiguity:</b> No mention of link expiration.<br>
        <b>Question:</b> How long should the reset link remain valid?</li>
  </ul>

  <h2 class="header orange">4. Recommendations</h2>
  <ul>
    <li>Add acceptance criteria for email content and expiration time.</li>
  </ul>
</div>
```

**IMPORTANT:** 
- Return ONLY the HTML code, starting with `<div class="review-container">` and ending with `</div>`.
- Do NOT include markdown formatting, code blocks with triple backticks, or any text outside the HTML structure.
- Make sure all HTML is properly formatted and ready to be inserted directly into a webpage.
"""
        
        print(f"DEBUG: Calling Gemini API for analysis...")
        print(f"DEBUG: Prompt length: {len(prompt)}")
        
        response = model.generate_content(prompt)
        print(f"DEBUG: Gemini response type: {type(response)}")
        
        # Extract text from response - use the same pattern as test case generation
        try:
            if hasattr(response, 'text'):
                analysis_text = response.text.strip()
            else:
                # Try to get text from candidates (backup method)
                print(f"DEBUG: Response doesn't have 'text' attribute, trying candidates...")
                print(f"DEBUG: Response attributes: {dir(response)}")
                if hasattr(response, 'candidates') and response.candidates:
                    if hasattr(response.candidates[0], 'content'):
                        if hasattr(response.candidates[0].content, 'parts'):
                            parts = response.candidates[0].content.parts
                            analysis_text = ''.join([part.text for part in parts if hasattr(part, 'text')]).strip()
                        else:
                            analysis_text = str(response.candidates[0].content).strip()
                    else:
                        analysis_text = str(response.candidates[0]).strip()
                else:
                    # Last resort: convert entire response to string
                    analysis_text = str(response).strip()
                    print(f"WARNING: Using fallback string conversion")
            
            if not analysis_text:
                raise ValueError("Empty analysis response from Gemini API")
            
            # Clean up the response - remove markdown code blocks if present
            analysis_text = analysis_text.strip()
            # Remove ```html or ``` markers
            if analysis_text.startswith('```'):
                # Remove opening code block
                lines = analysis_text.split('\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                analysis_text = '\n'.join(lines).strip()
            
            print(f"DEBUG: Successfully extracted analysis text, length: {len(analysis_text)}")
            print(f"DEBUG: First 200 chars: {analysis_text[:200]}")
            
        except Exception as extract_error:
            print(f"ERROR extracting text from response: {extract_error}")
            import traceback
            traceback.print_exc()
            raise ValueError(f"Failed to extract text from Gemini response: {str(extract_error)}")
        
        return jsonify({'analysis': analysis_text})
    except Exception as e:
        import traceback
        print(f"Error generating analysis: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/test_error')
def test_error():
    raise Exception("This is a test error!")

if __name__ == '__main__':
    app.run(debug=True) 