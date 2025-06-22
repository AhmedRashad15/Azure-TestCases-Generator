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
    data = request.json or {}
    story_id = data.get('story_id')
    azure_devops_org_url = data.get('azure_devops_org_url')
    azure_devops_project_name = data.get('azure_devops_project_name')
    azure_devops_pat = data.get('azure_devops_pat')

    if not all([story_id, azure_devops_org_url, azure_devops_project_name, azure_devops_pat]):
        return jsonify({'error': 'Azure DevOps details and User Story ID are required.'}), 400

    try:
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

        story_details = {
            'title': fields.get('System.Title', ''),
            'description': description_text,
            'acceptance_criteria': acceptance_criteria_text
        }
        return jsonify(story_details)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def _generate_cases_for_type(model, story_title, story_description, acceptance_criteria, data_dictionary, case_type):
    """Helper function to generate test cases for a specific type (e.g., Positive, Negative)."""

    guideline_map = {
        "Positive": """
**Positive Test Case Guidelines:**
- Verify the core functionality works as expected under normal conditions.
- Cover all acceptance criteria with at least one positive test case.
- Test each valid input scenario from the data dictionary separately.""",
        "Negative": """
**Negative Test Case Guidelines:**
- Test scenarios where inputs are invalid, missing, or unexpected.
- Create SEPARATE test cases for each type of invalid input.
- Verify that appropriate error messages are displayed when failures occur.""",
        "Edge Case": """
**Edge Case & Boundary Guidelines:**
- Test boundary conditions from the data dictionary (min/max values, etc.).
- Include scenarios with unexpected user behavior or timing.
- Test performance under special circumstances (e.g., large data sets, slow networks).""",
        "Data Flow": """
**Data Flow Guidelines:**
- Verify how data moves through the system from input to storage and output.
- Track data through an entire workflow to verify integrity.
- Test data persistence (saving) and retrieval (loading)."""
    }
    
    specific_guidelines = guideline_map.get(case_type, "- Follow standard best practices for this test type.")

    prompt = f"""
You are an expert test case generator for Azure DevOps with a focus on comprehensive test coverage. Your task is to generate a JSON array of ONLY the **{case_type}** test cases for the user story below.

**User Story Details:**
- **Title:** {story_title}
- **Description:** {story_description}
- **Acceptance Criteria:** {acceptance_criteria}
- **Data Dictionary:** {data_dictionary}

**Universal Guidelines:**
1. **Consistency First:** For any '{case_type}' test, the `title`, `description`, and `expectedResult` must all be consistent with that scenario. For example, a 'Negative' test's title must describe a failure condition, and its expected result must describe the correct error handling.
2. **Single Condition:** Each test case must focus on verifying exactly ONE condition or scenario. Do not combine multiple test conditions.

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
- `title`: A clear and descriptive title, including the type of test (e.g., "[Positive]").
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
        # Clean the response to get a clean JSON array string
        clean_json_text = response.text.strip().replace('```json', '').replace('```', '').strip()
        return clean_json_text
    except Exception as e:
        print(f"Error generating {case_type} cases: {e}")
        return "[]" # Return an empty array on error

@app.route('/generate_test_cases', methods=['GET'])
def generate_test_cases_stream():
    # Payload is now sent as a URL parameter
    payload_str = request.args.get('payload')
    if not payload_str:
        return Response("Payload missing.", status=400)
    
    data = json.loads(unquote(payload_str))

    story_title = data.get('story_title')
    story_description = data.get('story_description', '')
    acceptance_criteria = data.get('acceptance_criteria')
    data_dictionary = data.get('data_dictionary', '')

    if not all([story_title, acceptance_criteria]):
        return Response("Story Title and Acceptance Criteria are required.", status=400)

    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    
    def generate():
        case_types = ["Positive", "Negative", "Edge Case", "Data Flow"]
        all_test_cases = []

        for case_type in case_types:
            print(f"--- Generating {case_type} test cases... ---")
            # Generate cases for the current type
            json_text_chunk = _generate_cases_for_type(model, story_title, story_description, acceptance_criteria, data_dictionary, case_type)
            
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
        if not final_title_base.lower().startswith('verify that'):
            final_title = "Verify that " + final_title_base
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

if __name__ == '__main__':
    app.run(debug=True) 