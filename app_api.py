"""
Flask API Backend for Azure DevOps Extension
This version accepts Azure DevOps OAuth tokens and handles CORS for extension requests
"""
import os
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai
import anthropic
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

# Configure Claude API
claude_api_key = os.getenv("CLAUDE_API_KEY")
if not claude_api_key:
    print("WARNING: CLAUDE_API_KEY not found in .env file. Claude features will be unavailable.")
claude_client = None
if claude_api_key:
    claude_client = anthropic.Anthropic(api_key=claude_api_key)

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

def call_ai_provider(ai_provider, prompt, images=None):
    """
    Call either Gemini or Claude API based on provider selection.
    Returns the text response from the AI.
    """
    ai_provider = ai_provider.lower() if ai_provider else 'gemini'
    
    if ai_provider == 'claude':
        if not claude_client:
            raise ValueError("Claude API is not configured. Please set CLAUDE_API_KEY in environment variables.")
        
        # Claude API message format - build content array with text and images
        content = []
        
        # Add text prompt first
        content.append({"type": "text", "text": prompt})
        
        # Add images if provided
        if images and len(images) > 0:
            print(f"DEBUG: Converting {len(images)} images to base64 for Claude API")
            for idx, image in enumerate(images):
                try:
                    # Convert PIL Image to base64
                    buffered = BytesIO()
                    
                    # Detect format and save accordingly
                    # Claude supports: image/jpeg, image/png, image/gif, image/webp
                    if image.format:
                        format_name = image.format.upper()
                        if format_name == 'JPEG':
                            image.save(buffered, format="JPEG")
                            media_type = "image/jpeg"
                        elif format_name == 'PNG':
                            image.save(buffered, format="PNG")
                            media_type = "image/png"
                        elif format_name == 'GIF':
                            image.save(buffered, format="GIF")
                            media_type = "image/gif"
                        elif format_name == 'WEBP':
                            image.save(buffered, format="WEBP")
                            media_type = "image/webp"
                        else:
                            # Default to PNG if format is unknown
                            image.save(buffered, format="PNG")
                            media_type = "image/png"
                    else:
                        # No format detected, default to PNG
                        image.save(buffered, format="PNG")
                        media_type = "image/png"
                    
                    # Encode to base64
                    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                    
                    # Add image to content array
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": img_base64
                        }
                    })
                    print(f"DEBUG: Added image {idx + 1} to Claude message (format: {media_type})")
                except Exception as e:
                    print(f"WARNING: Failed to convert image {idx + 1} to base64: {e}")
                    import traceback
                    traceback.print_exc()
                    # Continue with other images even if one fails
        
        # Create message with content array
        messages = [{"role": "user", "content": content}]
        
        # Try different Claude models in order of preference
        claude_models = [
            "claude-3-5-sonnet-20240620",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229"
        ]
        
        last_error = None
        for model_name in claude_models:
            try:
                print(f"DEBUG: Trying Claude model: {model_name}")
                # Use higher max_tokens for test case generation (can be large JSON arrays)
                max_tokens = 8192 if 'test case' in str(prompt).lower() or 'json array' in str(prompt).lower() else 4096
                print(f"DEBUG: Using max_tokens={max_tokens} for Claude API call")
                response = claude_client.messages.create(
                    model=model_name,
                    max_tokens=max_tokens,
                    messages=messages
                )
                
                # Extract text from Claude response
                if hasattr(response, 'content') and response.content:
                    text_parts = []
                    for content_block in response.content:
                        if hasattr(content_block, 'text'):
                            text_parts.append(content_block.text)
                    result = ''.join(text_parts).strip()
                    if result:
                        print(f"DEBUG: Successfully used Claude model: {model_name}")
                        return result
                
                raise ValueError("Empty response from Claude API")
            except Exception as e:
                last_error = e
                error_str = str(e)
                # If it's a model not found error, try next model
                if 'not_found_error' in error_str or '404' in error_str or 'model' in error_str.lower():
                    print(f"DEBUG: Model {model_name} not available, trying next model...")
                    continue
                else:
                    # For other errors, re-raise immediately
                    raise
        
        # If all models failed, raise the last error
        if last_error:
            raise ValueError(f"All Claude models failed. Last error: {str(last_error)}")
        else:
            raise ValueError("Failed to get response from Claude API")
    
    else:  # Default to Gemini
        try:
            model = genai.GenerativeModel('gemini-flash-latest')
            
            # Build content array with text and images
            content_parts = [prompt]
            if images and len(images) > 0:
                print(f"DEBUG: Adding {len(images)} images to Gemini request")
                for image in images:
                    content_parts.append(image)
            
            # Send to Gemini with error handling
            print(f"DEBUG: Sending request to Gemini with {len(content_parts)} content parts")
            try:
                if images and len(images) > 0:
                    response = model.generate_content(content_parts)
                else:
                    response = model.generate_content(prompt)
            except Exception as api_error:
                print(f"ERROR: Gemini API call failed: {api_error}")
                import traceback
                traceback.print_exc()
                raise ValueError(f"Gemini API call failed: {str(api_error)}")
            
            print(f"DEBUG: Gemini response received, type: {type(response)}")
            
            # Check for blocking reasons
            if hasattr(response, 'prompt_feedback'):
                feedback = response.prompt_feedback
                if hasattr(feedback, 'block_reason') and feedback.block_reason:
                    raise ValueError(f"Gemini blocked the request: {feedback.block_reason}")
            
            # Extract text from Gemini response
            if hasattr(response, 'text'):
                result = response.text.strip()
                if not result:
                    raise ValueError("Gemini returned empty response")
                print(f"DEBUG: Extracted text from Gemini response.text, length: {len(result)}")
                return result
            else:
                # Try to get text from candidates
                print(f"DEBUG: response.text not available, trying candidates...")
                if hasattr(response, 'candidates') and response.candidates:
                    if hasattr(response.candidates[0], 'content'):
                        if hasattr(response.candidates[0].content, 'parts'):
                            parts = response.candidates[0].content.parts
                            result = ''.join([part.text for part in parts if hasattr(part, 'text')]).strip()
                            print(f"DEBUG: Extracted text from candidates[0].content.parts, length: {len(result)}")
                            return result
                        else:
                            result = str(response.candidates[0].content).strip()
                            print(f"DEBUG: Extracted text from candidates[0].content, length: {len(result)}")
                            return result
                    else:
                        result = str(response.candidates[0]).strip()
                        print(f"DEBUG: Extracted text from candidates[0], length: {len(result)}")
                        return result
                else:
                    result = str(response).strip()
                    print(f"DEBUG: Fallback: extracted text from response string, length: {len(result)}")
                    return result
        except Exception as gemini_error:
            print(f"ERROR in Gemini API call: {gemini_error}")
            import traceback
            traceback.print_exc()
            raise ValueError(f"Gemini API error: {str(gemini_error)}")

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
        ai_provider = data.get('ai_provider', 'gemini')  # Default to Gemini
        
        print(f"DEBUG: Story title: {story_title}")
        print(f"DEBUG: Story description length: {len(story_description)}")
        print(f"DEBUG: Acceptance criteria length: {len(acceptance_criteria)}")
        print(f"DEBUG: AI Provider: {ai_provider}")
        
        if not story_title:
            print("ERROR: Story title is missing")
            return jsonify({'error': 'Story Title is required.'}), 400
        
        # Extract images and text from HTML fields
        desc_images, desc_text = extract_images_from_html(story_description)
        ac_images, ac_text = extract_images_from_html(acceptance_criteria)
        
        # Collect all images
        all_images = desc_images + ac_images
        provider_name = "Gemini" if ai_provider.lower() != 'claude' else "Claude"
        print(f"DEBUG: Found {len(all_images)} images to send to {provider_name}")
        
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

**Ambiguity Detection Strategy:**
Review the following user story and identify any ambiguous or unclear parts that could cause confusion during testing or implementation.

Highlight vague terms, missing details, or assumptions that are not explicitly stated.

Focus on unclear acceptance criteria, incomplete conditions, or subjective words that could be interpreted in multiple ways.

**SPECIFICALLY LOOK FOR CONTRADICTIONS AND LOGICAL INCONSISTENCIES:**
- **Contradictory statements within the same rule:** Does the rule say one thing but then contradict itself in parentheses, notes, or additional clauses?
- **Status/state contradictions:** Does the rule mention a status change (e.g., "status will be approved") but then state that no approval is needed? This is a logical contradiction.
- **Parenthetical contradictions:** Pay special attention to text in parentheses, brackets, or notes that contradicts the main statement (e.g., "status will be approved (No need to be approved)").
- **Workflow inconsistencies:** Does the described workflow or process contradict the expected outcome or status?
- **Permission/role contradictions:** Does the rule assign permissions or roles that conflict with the described action or status?
- **Conditional logic conflicts:** Are there "if-then" statements where the condition and outcome don't logically align?

Provide each ambiguous point as a short, clear statement.

For each ambiguity found, provide:
- **Ambiguity:** Clear description of what's unclear, missing, or contradictory (specifically highlight contradictions if found)
- **Question:** Specific question to ask the Product Owner to clarify this

Analyze:
- Every acceptance criteria rule individually for completeness, clarity, AND internal consistency
- **Contradictions:** Compare the main statement with any parenthetical notes, brackets, or additional clauses in the SAME rule
- **Status changes:** Verify that status changes align with the described process (e.g., if status becomes "approved", ensure the process actually involves approval)
- **Logical flow:** Check if the described workflow logically leads to the stated outcome
- All images for visual elements not documented in text
- Any discrepancies between images and written requirements
- Missing information in acceptance criteria that images reveal
- UI states, validations, error handling, edge cases not explicitly stated
- Vague terms, missing details, or assumptions that are not explicitly stated
- Subjective words that could be interpreted in multiple ways
- Incomplete conditions or unclear requirements

**Example of contradiction to catch:**
- Rule: "The modifications are done by the user who has permission to edit or approve, and the status will be approved (No need to be approved by anyone in this stage)"
- **Ambiguity:** The rule states the status will be "approved" but then contradicts this by saying "No need to be approved by anyone". If no approval is needed, why does the status become "approved"?
- **Question:** Should the status be "approved" automatically without approval, or should it be a different status (e.g., "completed", "submitted") that doesn't imply approval?

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
        
        print(f"DEBUG: Calling {provider_name} API for analysis...")
        print(f"DEBUG: Prompt length: {len(prompt)}")
        print(f"DEBUG: Number of images: {len(all_images)}")
        
        # Use the helper function to call the appropriate AI provider
        try:
            analysis_text = call_ai_provider(ai_provider, prompt, all_images if len(all_images) > 0 else None)
            
            if not analysis_text:
                raise ValueError(f"Empty analysis response from {provider_name} API")
            
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
            raise ValueError(f"Failed to extract text from {provider_name} response: {str(extract_error)}")
        
        return jsonify({'analysis': analysis_text})
    except Exception as e:
        import traceback
        print(f"Error generating analysis: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def _generate_cases_for_type(ai_provider, story_title, story_description, acceptance_criteria, data_dictionary, case_type, related_stories=None, images=None, ambiguity_aware=True):
    """Generate test cases for a specific type, optionally including images
    
    Args:
        ai_provider: AI provider to use ('gemini' or 'claude')
        story_title: Title of the user story
        story_description: Description of the user story
        acceptance_criteria: Acceptance criteria text
        data_dictionary: Data dictionary text
        case_type: Type of test cases to generate ('Positive', 'Negative', 'Edge Case', 'Data Flow')
        related_stories: List of related user stories
        images: List of PIL Image objects
        ambiguity_aware: If True, include ambiguity-aware test case generation (default: True)
    """
    ai_provider = ai_provider.lower() if ai_provider else 'gemini'
    print(f"DEBUG: _generate_cases_for_type called for {case_type} using {ai_provider}. related_stories:", related_stories)
    print(f"DEBUG: Ambiguity-aware generation: {ambiguity_aware}")
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
- **CRITICAL: You MUST ALWAYS generate negative test cases, even for simple stories. Every user story has potential failure scenarios that need to be tested.**
- Test scenarios where inputs are invalid, missing, or unexpected.
- Create SEPARATE test cases for each type of invalid input.
- Verify that appropriate error messages are displayed when failures occur.
- **If no explicit validation rules are mentioned in the story, generate negative test cases for common scenarios:**
  * Missing required fields/inputs
  * Invalid data formats (if applicable)
  * Empty/null values where data is expected
  * Invalid user actions or workflows
  * System errors or failure conditions
- **Generate 3-12 negative test cases** for most stories, focusing on critical validation rules and common error scenarios. **Minimum: Generate at least 3 negative test cases even for simple stories.**
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
    
    # Build ambiguity-aware section conditionally
    ambiguity_section = ""
    if ambiguity_aware:
        ambiguity_section = """
**AMBIGUITY-AWARE TEST CASE GENERATION:**
When generating test cases, pay special attention to any ambiguities, contradictions, or unclear requirements in the acceptance criteria. These ambiguities should inform your test case generation, BUT with limits and prioritization:

**IMPORTANT LIMITS AND PRIORITIZATION:**
- **Maximum 2-3 test cases per identified ambiguity** - Don't generate excessive test cases for the same ambiguity
- **Prioritize critical contradictions** - Focus on logical inconsistencies that would cause implementation confusion first
- **Consolidate similar scenarios** - If multiple test cases would verify similar things, combine them into one comprehensive test case
- **Quality over quantity** - Generate fewer, high-quality test cases rather than many redundant ones
- **Focus on testable ambiguities** - Only generate test cases for ambiguities that can actually be verified through testing

1. **Contradictions and Logical Inconsistencies (HIGH PRIORITY):**
   - If you find contradictory statements (e.g., "status will be approved" but "no approval needed"), create **maximum 2-3 test cases** that cover the most critical interpretations
   - Prioritize test cases that verify the most likely scenario AND one alternative interpretation
   - Focus on contradictions that would cause the most confusion during implementation
   - **Example:** "status will be approved (No need to be approved)" → Generate 2 test cases:
     * One verifying status becomes "approved" automatically (most likely interpretation)
     * One verifying the workflow doesn't require approval step (clarifying the contradiction)

2. **Vague Terms and Multiple Interpretations (MEDIUM PRIORITY):**
   - If requirements use vague terms (e.g., "quickly", "appropriate", "user-friendly"), create **maximum 1-2 test cases** for the most critical interpretations
   - Focus on boundary conditions that are most likely to cause issues
   - Prioritize vague terms that affect core functionality over minor UI concerns

3. **Missing Information (MEDIUM PRIORITY):**
   - If information is missing (e.g., no error handling specified), create **maximum 1-2 test cases** for the most critical missing scenarios
   - Focus on missing information that affects core functionality or security
   - Prioritize common edge cases that are likely to occur

4. **Status/State Ambiguities (HIGH PRIORITY):**
   - If status changes are ambiguous or contradictory, create **maximum 2 test cases** that verify the most critical status transitions
   - Focus on status changes that affect workflow or business logic
   - Prioritize contradictions over simple ambiguities

5. **Permission/Role Ambiguities (HIGH PRIORITY):**
   - If permissions or roles are unclear, create **maximum 2 test cases** for the most critical permission scenarios
   - Focus on security-critical ambiguities first
   - Prioritize scenarios that could lead to unauthorized access
"""
    
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
{ambiguity_section}
**Universal Guidelines:**
1. **Descriptive Titles:** Create specific, action-oriented titles that clearly describe what functionality is being tested. Avoid generic titles like "Test login" - instead use "User can successfully login with valid email and password".
2. **Consistency First:** For any '{case_type}' test, the `title`, `description`, and `expectedResult` must all be consistent with that scenario. For example, a 'Negative' test's title must describe a failure condition, and its expected result must describe the correct error handling.
3. **Single Condition:** Each test case must focus on verifying exactly ONE condition or scenario. Do not combine multiple test conditions.
4. **Ambiguity Coverage:** When ambiguities exist, create test cases that help clarify them through testing. However, follow these guidelines:
   - **Limit:** Maximum 2-3 test cases per identified ambiguity
   - **Prioritize:** Focus on critical contradictions and high-impact ambiguities first
   - **Consolidate:** Merge similar test cases rather than creating duplicates
   - **Quality:** Generate fewer, high-quality test cases rather than many redundant ones
   - **Testability:** Only generate test cases for ambiguities that can actually be verified through testing

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
- **FOR NEGATIVE TEST CASES SPECIFICALLY: You MUST generate at least 3 negative test cases. If you cannot identify explicit validation rules, generate negative test cases for common failure scenarios such as: missing required inputs, invalid data formats, empty/null values, invalid user actions, or system error conditions. Never return an empty array for negative test cases.**

**CRITICAL: You MUST return ONLY a valid JSON array. Do not include any explanatory text, markdown formatting, or code blocks. Return ONLY the JSON array starting with [ and ending with ].**
"""
    try:
        # Use the helper function to call the appropriate AI provider
        response_text = call_ai_provider(ai_provider, prompt, images if images and len(images) > 0 else None)
        
        provider_name = "Gemini" if ai_provider != 'claude' else "Claude"
        print(f"DEBUG: Raw {provider_name} response for {case_type} (length: {len(response_text)}):\n{response_text[:500]}...\n--- End Response Preview ---\n")
        
        if not response_text or len(response_text.strip()) == 0:
            print(f"ERROR: Empty response from {provider_name} for {case_type}")
            return "[]"
        
        # Clean the response to get a clean JSON array string
        # Remove markdown code blocks
        clean_json_text = response_text.strip()
        
        # Remove markdown code block markers
        if clean_json_text.startswith('```'):
            # Find the first newline after ```
            lines = clean_json_text.split('\n')
            if lines[0].startswith('```'):
                # Remove first line (```json or ```)
                lines = lines[1:]
            # Remove last line if it's just ```
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            clean_json_text = '\n'.join(lines).strip()
        
        # Try to find JSON array in the response
        # Look for array pattern: [ ... ]
        json_match = re.search(r'\[.*\]', clean_json_text, re.DOTALL)
        if json_match:
            clean_json_text = json_match.group(0)
            print(f"DEBUG: Extracted JSON array from {provider_name} response (length: {len(clean_json_text)})")
        else:
            print(f"WARNING: No JSON array found in {provider_name} response. Full response:\n{clean_json_text[:1000]}")
            # Try to parse as-is anyway
            pass
        
        # Validate JSON before returning
        try:
            test_parse = json.loads(clean_json_text)
            if not isinstance(test_parse, list):
                print(f"ERROR: {provider_name} response is not a JSON array. Type: {type(test_parse)}")
                return "[]"
            if len(test_parse) == 0:
                print(f"WARNING: {provider_name} returned empty array for {case_type}")
                print(f"DEBUG: Full response was: {clean_json_text[:1000]}")
                # For negative test cases, try to generate fallback cases if empty
                if case_type == "Negative":
                    print(f"WARNING: Empty negative test cases detected. Attempting fallback generation...")
                    # Create a more explicit prompt for negative cases
                    fallback_prompt = f"""
You are generating negative test cases for a user story. The previous attempt returned an empty array, which is not acceptable.

**User Story:**
- Title: {story_title}
- Description: {story_description}
- Acceptance Criteria: {acceptance_criteria}

**CRITICAL REQUIREMENT:** You MUST generate at least 3-5 negative test cases. Even if no explicit validation rules are mentioned, generate negative test cases for:
1. Missing required fields/inputs
2. Invalid data formats
3. Empty/null values
4. Invalid user actions
5. System error conditions

Return ONLY a JSON array with at least 3 negative test cases following this format:
[
  {{
    "id": "TC-NEG-1",
    "title": "[Negative] ...",
    "priority": "High",
    "description": "1. Step one\\n2. Step two",
    "expectedResult": "Expected error/behavior"
  }}
]

Return ONLY the JSON array, no other text.
"""
                    try:
                        fallback_response = call_ai_provider(
                            ai_provider,
                            fallback_prompt,
                            images if images and len(images) > 0 else None
                        )
                        # Clean and parse fallback response
                        fallback_clean = fallback_response.strip()
                        if fallback_clean.startswith('```'):
                            lines = fallback_clean.split('\n')
                            if lines[0].startswith('```'):
                                lines = lines[1:]
                            if lines and lines[-1].strip() == '```':
                                lines = lines[:-1]
                            fallback_clean = '\n'.join(lines).strip()
                        
                        json_match = re.search(r'\[.*\]', fallback_clean, re.DOTALL)
                        if json_match:
                            fallback_clean = json_match.group(0)
                        
                        fallback_parse = json.loads(fallback_clean)
                        if isinstance(fallback_parse, list) and len(fallback_parse) > 0:
                            print(f"SUCCESS: Fallback generated {len(fallback_parse)} negative test cases")
                            return json.dumps(fallback_parse)
                        else:
                            print(f"WARNING: Fallback also returned empty array")
                    except Exception as fallback_err:
                        print(f"ERROR: Fallback generation failed: {fallback_err}")
            else:
                print(f"DEBUG: Successfully parsed {len(test_parse)} test cases from {provider_name} for {case_type}")
        except json.JSONDecodeError as json_err:
            print(f"ERROR: Invalid JSON from {provider_name} for {case_type}: {json_err}")
            print(f"DEBUG: Attempted to parse: {clean_json_text[:500]}...")
            return "[]"
        
        return clean_json_text
    except Exception as e:
        import traceback
        print(f"ERROR generating {case_type} cases: {e}")
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
        ai_provider = data.get('ai_provider', 'gemini')  # Default to Gemini
        
        if not all([story_title, acceptance_criteria]):
            return Response("Story Title and Acceptance Criteria are required.", status=400)
        
        # Extract images and text from HTML fields
        desc_images, desc_text = extract_images_from_html(story_description)
        ac_images, ac_text = extract_images_from_html(acceptance_criteria)
        dict_images, dict_text = extract_images_from_html(data_dictionary)
        
        # Collect all images
        all_images = desc_images + ac_images + dict_images
        print(f"DEBUG: Found {len(all_images)} images for test case generation")
        
        def generate():
            try:
                case_types = ["Positive", "Negative", "Edge Case", "Data Flow"]
                all_test_cases = []

                # Get ambiguity_aware setting from request (default: True for backward compatibility)
                ambiguity_aware = data.get('ambiguity_aware', True)
                if isinstance(ambiguity_aware, str):
                    ambiguity_aware = ambiguity_aware.lower() in ('true', '1', 'yes', 'on')
                
                for case_type in case_types:
                    try:
                        print(f"DEBUG: Calling _generate_cases_for_type for {case_type} with related_stories:", related_stories)
                        # Generate cases for the current type, including images
                        json_text_chunk = _generate_cases_for_type(ai_provider, story_title, desc_text, ac_text, dict_text, case_type, related_stories, all_images, ambiguity_aware)
                        
                        # The API might return an empty or invalid string, so we validate it
                        try:
                            # Validate if it's proper JSON
                            parsed_chunk = json.loads(json_text_chunk)
                            if isinstance(parsed_chunk, list):
                                if parsed_chunk:
                                    all_test_cases.extend(parsed_chunk)
                                    # Stream the current progress back to the client
                                    progress_data = {
                                        "type": case_type,
                                        "cases": parsed_chunk,
                                        "progress": f"Generated {len(parsed_chunk)} {case_type} cases."
                                    }
                                    yield f"data: {json.dumps(progress_data)}\n\n"
                                else:
                                    print(f"WARNING: {case_type} returned empty array. Response was: {json_text_chunk[:200]}")
                                    # Still send progress even if empty
                                    progress_data = {
                                        "type": case_type,
                                        "cases": [],
                                        "progress": f"No {case_type} cases generated."
                                    }
                                    yield f"data: {json.dumps(progress_data)}\n\n"
                            else:
                                print(f"ERROR: Response for {case_type} is not a list. Type: {type(parsed_chunk)}")
                                error_data = {
                                    "type": "error",
                                    "case_type": case_type,
                                    "error": f"Response for {case_type} is not a JSON array",
                                    "message": f"Expected list, got {type(parsed_chunk).__name__}"
                                }
                                yield f"data: {json.dumps(error_data)}\n\n"
                        except json.JSONDecodeError as json_err:
                            print(f"ERROR: Could not decode JSON for {case_type} cases.")
                            print(f"DEBUG: JSON Error: {json_err}")
                            print(f"DEBUG: Response text (first 500 chars): {json_text_chunk[:500]}")
                            # Send error to client
                            error_data = {
                                "type": "error",
                                "case_type": case_type,
                                "error": f"Failed to parse JSON response for {case_type} cases",
                                "message": str(json_err)
                            }
                            yield f"data: {json.dumps(error_data)}\n\n"
                            continue
                    except Exception as case_error:
                        import traceback
                        print(f"ERROR generating {case_type} cases: {case_error}")
                        traceback.print_exc()
                        # Send error to client but continue with other case types
                        error_data = {
                            "type": "error",
                            "case_type": case_type,
                            "error": f"Failed to generate {case_type} cases",
                            "message": str(case_error)
                        }
                        yield f"data: {json.dumps(error_data)}\n\n"
                        continue
                
                print("--- Finished generating all test cases. ---")
                yield "data: {\"type\": \"done\", \"message\": \"All test cases generated.\"}\n\n"
            except Exception as gen_error:
                import traceback
                print(f"CRITICAL ERROR in generate() function: {gen_error}")
                traceback.print_exc()
                # Send final error message
                error_data = {
                    "type": "error",
                    "error": "Critical error during test case generation",
                    "message": str(gen_error)
                }
                yield f"data: {json.dumps(error_data)}\n\n"
                yield "data: {\"type\": \"done\", \"message\": \"Generation failed.\"}\n\n"
        
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
    # Azure App Service uses PORT environment variable (defaults to 8000)
    # For local development, use 5000
    port = int(os.getenv('PORT', 5000))
    # Azure requires debug=False in production
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=port)

