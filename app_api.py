"""
Flask API Backend for Azure DevOps Extension
This version accepts Azure DevOps OAuth tokens and handles CORS for extension requests
"""
import os
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
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
import base64
from io import BytesIO
from PIL import Image

# Load environment variables
load_dotenv()

# Configure Gemini API
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    raise ValueError("GEMINI_API_KEY not found in .env file")
genai.configure(api_key=gemini_api_key)

# Flask App with CORS support
app = Flask(__name__)

# Enable CORS for Azure DevOps extension origins
CORS(app, origins=[
    "https://dev.azure.com",
    "https://*.visualstudio.com",
    "https://app.vssps.visualstudio.com"
], allow_headers=["Content-Type", "Authorization"], methods=["GET", "POST", "OPTIONS"])

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = Response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type, Authorization")
        response.headers.add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        return response

def extract_images_from_html(html_content):
    """Extract images from HTML content and return list of PIL Image objects and text with placeholders"""
    if not html_content:
        return [], ""
    
    soup = BeautifulSoup(html_content, 'html.parser')
    images = soup.find_all('img')
    
    image_objects = []
    
    # Process images and replace with placeholders
    for img in images:
        src = img.get('src', '')
        if src.startswith('data:image'):
            try:
                # Parse data URL: data:image/png;base64,<data>
                header, data = src.split(',', 1)
                
                # Decode base64
                image_bytes = base64.b64decode(data)
                image = Image.open(BytesIO(image_bytes))
                
                # Convert to RGB if necessary (Gemini requires RGB format)
                if image.mode in ('RGBA', 'LA'):
                    rgb_image = Image.new('RGB', image.size, (255, 255, 255))
                    rgb_image.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                    image = rgb_image
                elif image.mode == 'P':
                    image = image.convert('RGB')
                elif image.mode != 'RGB':
                    image = image.convert('RGB')
                
                image_objects.append(image)
                
                # Replace img tag with placeholder text
                alt_text = img.get('alt', 'image')
                img.replace_with(f"[Image {len(image_objects)}: {alt_text}]")
            except Exception as e:
                print(f"WARNING: Failed to process image: {e}")
                import traceback
                traceback.print_exc()
                alt_text = img.get('alt', 'image')
                img.replace_with(f"[Image: {alt_text} - failed to load]")
        else:
            # External image URL - keep as placeholder
            alt_text = img.get('alt', 'image')
            img.replace_with(f"[Image: {alt_text} - external URL]")
    
    # Get text content with placeholders
    text_content = soup.get_text(separator=' ', strip=True)
    
    return image_objects, text_content

def extract_text_only_from_html(html_content):
    """Extract only text from HTML, replacing images with placeholders"""
    if not html_content:
        return ""
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Replace img tags with text placeholders
    for img in soup.find_all('img'):
        alt_text = img.get('alt', 'image')
        img.replace_with(f"[Image: {alt_text}]")
    
    return soup.get_text(separator='\n', strip=True)

def get_azure_devops_connection(auth_token: str, org_url: str):
    """Create Azure DevOps connection using OAuth token"""
    # For OAuth tokens, use Basic auth with empty username and token as password
    credentials = BasicAuthentication('', auth_token)
    return Connection(base_url=org_url, creds=credentials)

@app.route('/', methods=['GET'])
def index():
    """Root endpoint - API information"""
    return jsonify({
        'message': 'Test Genius API - Azure DevOps Extension Backend',
        'version': '1.0.0',
        'endpoints': {
            'health': '/health',
            'analyze_story': '/analyze_story (POST)',
            'generate_test_cases': '/generate_test_cases (GET)'
        },
        'status': 'running'
    }), 200

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'}), 200

@app.route('/analyze_story', methods=['POST'])
def analyze_story():
    """Analyze a user story and provide structured review"""
    print("DEBUG: /analyze_story endpoint called")
    
    # Get Authorization header for Azure DevOps token (if provided)
    auth_header = request.headers.get('Authorization', '')
    azure_devops_token = None
    if auth_header.startswith('Bearer '):
        azure_devops_token = auth_header[7:]
    
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
        
        model = genai.GenerativeModel('gemini-flash-latest')  # Free tier model that supports images
        
        # Extract images and text from HTML fields
        desc_images, desc_text = extract_images_from_html(story_description)
        ac_images, ac_text = extract_images_from_html(acceptance_criteria)
        
        # Collect all images
        all_images = desc_images + ac_images
        print(f"DEBUG: Found {len(all_images)} images to send to Gemini")
        
        # Build the prompt for analysis
        test_cases_section = ""
        if related_test_cases:
            test_cases_section = f"\n\n**RELATED TEST CASES (if available):**\n{related_test_cases}"
        
        prompt = f"""You are an experienced software analyst and product owner assistant.

Your task is to review the following user story (and related test cases if available) and produce a simple, actionable, and UI-ready output for the development team.

**USER STORY:**
**Title:** {story_title}
**Description:** {desc_text}
**Acceptance Criteria:** {ac_text}
{test_cases_section}

**IMPORTANT ANALYSIS INSTRUCTIONS:**

1. **Acceptance Criteria Analysis:**
   - Review EACH individual rule, requirement, and condition stated in the acceptance criteria
   - Break down each acceptance criterion into its component parts
   - Check for completeness: Does each rule have enough detail to implement?
   - Check for testability: Can each rule be verified with clear pass/fail criteria?
   - Check for conflicts: Are there any contradictory requirements?
   - Check for missing information: What data, validation rules, error messages, or edge cases are not specified?

2. **Image Analysis (if images are provided):**
   - Carefully examine ALL images included with this user story
   - Analyze visual elements: UI components, layouts, workflows, diagrams, screenshots
   - Compare images with text requirements: Do images match what's described in text?
   - Identify visual ambiguities: 
     * Are there UI elements shown in images that aren't mentioned in acceptance criteria?
     * Are there visual states (hover, focus, error) not defined in text?
     * Are there design specifications (colors, sizes, spacing) visible but not documented?
     * Are there workflow steps shown visually that aren't explicitly stated?
   - Check for discrepancies: Do images contradict the written acceptance criteria?
   - Note missing visuals: Are critical UI states, error cases, or edge scenarios not shown in images?

3. **Cross-Reference Check:**
   - Compare images with acceptance criteria rules
   - Ensure every visible element in images has corresponding acceptance criteria
   - Ensure every acceptance criteria rule is reflected (if applicable) in images

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
**CRITICAL: You must thoroughly analyze EACH acceptance criteria rule AND ALL provided images.**

For each ambiguity found, provide:
- **Ambiguity:** Clear description of what's unclear, missing, or contradictory
- **Question:** Specific question to ask the Product Owner to clarify this

Analyze:
- Every acceptance criteria rule individually for completeness and clarity
- All images for visual elements not documented in text
- Any discrepancies between images and written requirements
- Missing information in acceptance criteria that images reveal
- UI states, validations, error handling, edge cases not explicitly stated

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
    <li><b>Ambiguity:</b> Image shows a "Cancel" button that is not mentioned in acceptance criteria.<br>
        <b>Question:</b> Should users be able to cancel the password reset process?</li>
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

**IMAGES PROVIDED:**
{len(all_images)} image(s) have been included with this user story. You MUST:
1. Examine each image carefully for visual requirements, UI elements, workflows, and states
2. Compare what you see in images against the acceptance criteria rules
3. Identify any visual elements, UI states, or design specifications shown in images that are NOT documented in the acceptance criteria
4. Note any discrepancies between images and written requirements
5. Flag missing visual documentation (error states, edge cases, different screen sizes, etc.)
6. Reference specific images when identifying ambiguities (e.g., "In Image 1, there is a [element] that is not mentioned in acceptance criteria...")
"""
        
        print(f"DEBUG: Calling Gemini API for analysis...")
        print(f"DEBUG: Prompt length: {len(prompt)}")
        print(f"DEBUG: Number of images: {len(all_images)}")
        
        # Build content array with text and images
        content_parts = [prompt]
        for image in all_images:
            content_parts.append(image)
        
        # Send to Gemini with multimodal content
        if len(all_images) > 0:
            response = model.generate_content(content_parts)
            print(f"DEBUG: Sent {len(all_images)} images to Gemini")
        else:
            response = model.generate_content(prompt)
        
        print(f"DEBUG: Gemini response type: {type(response)}")
        
        # Extract text from response
        try:
            if hasattr(response, 'text'):
                analysis_text = response.text.strip()
            else:
                # Try to get text from candidates
                print(f"DEBUG: Response doesn't have 'text' attribute, trying candidates...")
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
                    analysis_text = str(response).strip()
                    print(f"WARNING: Using fallback string conversion")
            
            if not analysis_text:
                raise ValueError("Empty analysis response from Gemini API")
            
            # Clean up the response - remove markdown code blocks if present
            analysis_text = analysis_text.strip()
            if analysis_text.startswith('```'):
                lines = analysis_text.split('\n')
                if lines[0].startswith('```'):
                    lines = lines[1:]
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                analysis_text = '\n'.join(lines).strip()
            
            print(f"DEBUG: Successfully extracted analysis text, length: {len(analysis_text)}")
            
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

def _generate_cases_for_type(model, story_title, story_description, acceptance_criteria, data_dictionary, case_type, related_stories=None, images=None):
    """Generate test cases for a specific type, optionally including images"""
    print(f"DEBUG: _generate_cases_for_type called for {case_type}. related_stories:", related_stories)
    if images:
        print(f"DEBUG: Including {len(images)} images in test case generation")
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

**IMAGES PROVIDED:**
If images are included with the user story, please analyze them carefully and reference their content when generating test cases. The images may show UI mockups, workflows, or visual requirements that should be covered in the test cases.

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
        # Build content array with text and images
        if images and len(images) > 0:
            content_parts = [prompt]
            content_parts.extend(images)
            response = model.generate_content(content_parts)
            print(f"DEBUG: Sent {len(images)} images to Gemini for {case_type} test cases")
        else:
            response = model.generate_content(prompt)
        
        print(f"Raw Gemini response for {case_type}:\n{response.text}\n--- End Response ---\n")
        # Clean the response to get a clean JSON array string
        clean_json_text = response.text.strip().replace('```json', '').replace('```', '').strip()
        return clean_json_text
    except Exception as e:
        import traceback
        print(f"Error generating {case_type} cases: {e}")
        traceback.print_exc()
        return "[]"

@app.route('/generate_test_cases', methods=['POST', 'GET'])
def generate_test_cases_stream():
    """Generate test cases with streaming support - supports both GET (legacy) and POST (for large payloads)"""
    print("DEBUG: /generate_test_cases endpoint called.")
    
    # Get Authorization header for Azure DevOps token (if provided)
    auth_header = request.headers.get('Authorization', '')
    azure_devops_token = None
    if auth_header.startswith('Bearer '):
        azure_devops_token = auth_header[7:]
    
    # Support both GET (legacy) and POST (for large payloads with images)
    if request.method == 'POST':
        try:
            data = request.json or {}
            if not data:
                return Response("Payload missing.", status=400)
        except Exception as e:
            return Response(f"Invalid JSON payload: {str(e)}", status=400), 400
    else:
        # GET request (legacy support)
        payload_str = request.args.get('payload')
        if not payload_str:
            return Response("Payload missing.", status=400)
        try:
            data = json.loads(unquote(payload_str))
        except json.JSONDecodeError as e:
            return Response(f"Invalid payload: {str(e)}", status=400), 400
    
    try:
        
        story_title = data.get('story_title')
        story_description = data.get('story_description', '')
        acceptance_criteria = data.get('acceptance_criteria')
        data_dictionary = data.get('data_dictionary', '')
        related_stories = data.get('related_stories', [])
        
        if not all([story_title, acceptance_criteria]):
            return Response("Story Title and Acceptance Criteria are required.", status=400)
        
        model = genai.GenerativeModel('gemini-flash-latest')  # Free tier model that supports images
        
        # Extract images and text from HTML fields
        desc_images, desc_text = extract_images_from_html(story_description)
        ac_images, ac_text = extract_images_from_html(acceptance_criteria)
        dict_images, dict_text = extract_images_from_html(data_dictionary)
        
        # Collect all images
        all_images = desc_images + ac_images + dict_images
        print(f"DEBUG: Found {len(all_images)} images for test case generation")
        
        def generate():
            case_types = ["Positive", "Negative", "Edge Case", "Data Flow"]
            all_test_cases = []

            for case_type in case_types:
                print(f"DEBUG: Calling _generate_cases_for_type for {case_type} with related_stories:", related_stories)
                # Generate cases for the current type, including images
                json_text_chunk = _generate_cases_for_type(model, story_title, desc_text, ac_text, dict_text, case_type, related_stories, all_images)
                
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
        
        response = Response(generate(), mimetype='text/event-stream')
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['X-Accel-Buffering'] = 'no'  # Disable buffering for nginx
        return response
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)

