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

def extract_table_from_html(table_element):
    """Extract and format a table element into readable text format"""
    if not table_element:
        return ""
    
    rows = table_element.find_all('tr')
    if not rows:
        return ""
    
    table_text = []
    table_text.append("\n[TABLE START]")
    
    for row in rows:
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue
        
        # Extract text from each cell, preserving structure
        cell_texts = []
        for cell in cells:
            # Get all text nodes and join them properly
            # Use get_text with separator to handle nested elements
            cell_text = cell.get_text(separator=' ', strip=True)
            
            # Aggressively normalize all whitespace - this is critical for related stories
            # Replace all types of whitespace (spaces, tabs, newlines, etc.) with single space
            cell_text = re.sub(r'\s+', ' ', cell_text)
            
            # Remove leading/trailing whitespace
            cell_text = cell_text.strip()
            
            # Only add non-empty cells
            if cell_text:
                cell_texts.append(cell_text)
        
        # Only add row if it has cells
        if cell_texts:
            # Join cells with pipe separator (with spaces for readability)
            row_text = " | ".join(cell_texts)
            table_text.append(row_text)
    
    table_text.append("[TABLE END]\n")
    # Join all rows with newlines, ensuring no extra spaces
    result = "\n".join(table_text)
    # Final cleanup: ensure no multiple consecutive spaces anywhere
    result = re.sub(r' {2,}', ' ', result)
    return result

def extract_images_from_html(html_content):
    """Extract images and tables from HTML content and return list of PIL Image objects and text with placeholders"""
    if not html_content:
        return [], ""
    
    # Normalize HTML content - remove extra whitespace but preserve structure
    # This helps with tables that might have inconsistent spacing, especially from related stories
    # First, normalize whitespace within table tags specifically
    html_content = re.sub(r'(<table[^>]*>)\s+', r'\1', html_content, flags=re.IGNORECASE)
    html_content = re.sub(r'\s+(</table>)', r'\1', html_content, flags=re.IGNORECASE)
    html_content = re.sub(r'(<tr[^>]*>)\s+', r'\1', html_content, flags=re.IGNORECASE)
    html_content = re.sub(r'\s+(</tr>)', r'\1', html_content, flags=re.IGNORECASE)
    html_content = re.sub(r'(<td[^>]*>)\s+', r'\1', html_content, flags=re.IGNORECASE)
    html_content = re.sub(r'\s+(</td>)', r'\1', html_content, flags=re.IGNORECASE)
    html_content = re.sub(r'(<th[^>]*>)\s+', r'\1', html_content, flags=re.IGNORECASE)
    html_content = re.sub(r'\s+(</th>)', r'\1', html_content, flags=re.IGNORECASE)
    # Then normalize general whitespace
    html_content = re.sub(r'[ \t]+', ' ', html_content)
    # Normalize multiple newlines to single newline
    html_content = re.sub(r'\n\s*\n+', '\n', html_content)
    
    soup = BeautifulSoup(html_content, 'html.parser')
    images = soup.find_all('img')
    tables = soup.find_all('table')
    
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
    
    # Process tables and replace with formatted text
    # Replace tables with their extracted text directly, but normalize surrounding whitespace
    for table in tables:
        table_text = extract_table_from_html(table)
        if table_text:
            # Replace table with the formatted text
            # The table text already has proper newlines, so we just replace directly
            table.replace_with(table_text)
    
    # Get text content - use newline separator to preserve structure for step detection
    # But we'll clean up extra whitespace afterwards
    text_content = soup.get_text(separator='\n', strip=True)
    
    # Final cleanup: normalize multiple consecutive newlines and spaces
    # This is critical for related stories that may have extra whitespace
    text_content = re.sub(r'\n\s*\n+', '\n\n', text_content)  # Max 2 newlines
    text_content = re.sub(r'[ \t]+', ' ', text_content)  # Multiple spaces/tabs to single space
    text_content = re.sub(r' \n', '\n', text_content)  # Remove space before newline
    text_content = re.sub(r'\n ', '\n', text_content)  # Remove space after newline
    # Remove any remaining multiple spaces (shouldn't happen, but just in case)
    text_content = re.sub(r' {2,}', ' ', text_content)
    # Clean up spaces around table markers
    text_content = re.sub(r' +\[TABLE', '\n[TABLE', text_content)
    text_content = re.sub(r'\[TABLE +', '[TABLE ', text_content)
    text_content = re.sub(r' +TABLE END\]', ' TABLE END]\n', text_content)
    text_content = re.sub(r'TABLE END\] +', 'TABLE END]\n', text_content)
    
    return image_objects, text_content

def extract_text_only_from_html(html_content):
    """Extract only text from HTML, replacing images with placeholders and formatting tables"""
    if not html_content:
        return ""
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Replace img tags with text placeholders
    for img in soup.find_all('img'):
        alt_text = img.get('alt', 'image')
        img.replace_with(f"[Image: {alt_text}]")
    
    # Process tables and replace with formatted text
    for table in soup.find_all('table'):
        table_text = extract_table_from_html(table)
        if table_text:
            table.replace_with(table_text)
    
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
            error_str = str(gemini_error)
            
            # Check for quota/rate limit errors
            if '429' in error_str or 'quota' in error_str.lower() or 'rate limit' in error_str.lower() or 'exceeded' in error_str.lower():
                # Try to extract retry delay if available
                retry_delay = None
                if 'retry' in error_str.lower() or 'seconds' in error_str.lower():
                    import re
                    delay_match = re.search(r'(\d+)\s*seconds?', error_str, re.IGNORECASE)
                    if delay_match:
                        retry_delay = int(delay_match.group(1))
                
                error_msg = f"Gemini API quota/rate limit exceeded: {error_str}"
                if retry_delay:
                    error_msg += f"\n\nPlease wait approximately {retry_delay} seconds before retrying, or switch to Claude API provider."
                else:
                    error_msg += "\n\nPlease wait a few minutes before retrying, or switch to Claude API provider."
                raise ValueError(error_msg)
            # Check for authentication errors
            elif '401' in error_str or '403' in error_str or 'authentication' in error_str.lower() or 'api_key' in error_str.lower():
                raise ValueError(f"Gemini API authentication error: {error_str}. Please check your GEMINI_API_KEY.")
            else:
                raise ValueError(f"Gemini API error: {error_str}")

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
        
        prompt = f"""**Role:** You are a Senior Expert Quality Control (QC) Engineer mentoring a team of testers.

**Objective:** Take the provided User Story and break it down so thoroughly and clearly that a QC Engineer can trust your explanation 100%. Your output must be the "single source of truth." The tester should **not need to read the original Azure ticket** to understand exactly what needs to be tested, why it matters, and how it works.

**Analytical Directives:**
1. **Translate for QC:** Do not just parrot the product owner's text. Explain the feature's workflow, business value, and mechanics specifically through the lens of testing.
2. **Deconstruct Functionality:** Identify the explicit happy paths and core business logic step-by-step.
3. **Hunt for Edge Cases (Negative Testing):** Think critically about boundary values, invalid inputs, timeouts, concurrent user actions, and error handling. What happens when things go wrong? Feed findings into section 3 (Edge Cases & Risks).
4. **Evaluate Automation Readiness:** Assess if the acceptance criteria are deterministic enough for automated testing scripts. Are there predictable states, clear setup/teardown requirements, and explicit data needs? Mention gaps in section 3 or 4 as appropriate.
5. **Non-Functional Requirements (NFRs):** Look for missing performance, security, UI/UX consistency, or accessibility constraints.

**User Story to Analyze:**
**Title:** {story_title}
**Description:** {desc_text}
**Acceptance Criteria:** {ac_text}
{test_cases_section}

**Additional analysis (apply throughout all sections):**
- Review EACH acceptance criteria rule for completeness, testability, conflicts, and missing data/validation/error handling.
- **Contradictions:** Flag contradictory statements within the same rule (including text in parentheses or notes that contradict the main statement), status/workflow inconsistencies, and permission conflicts. Capture these in section 4 with **Ambiguity:** and **Question:**.
- **Images (if provided):** Examine all images; compare UI to text; note elements, states, or workflows in images not documented in acceptance criteria; flag discrepancies. Reference images in Edge Cases, Risks, or Ambiguities as relevant.
- If related test cases were provided, briefly tie them into section 1 or 2 where they clarify scope.

### 🎨 UI Rendering Guidelines
Return your final output formatted strictly as **HTML** (not markdown), following these visual and structural rules:
- Each section should be wrapped in a `<div>` with a unique color-coded header:
  - **1. Story Explanation for QC:** Blue header (`#0078D7`)
  - **2. Key Functional Points:** Green header (`#28a745`)
  - **3. Edge Cases & Risks:** Red header (`#dc3545`)
  - **4. Ambiguities & Clarification Questions:** Yellow header (`#ffc107`)
- Headers must have **bold white text**, padding (8px), and rounded corners.
- Each bullet point should use **Bold labels** (like **Ambiguity:** / **Risk:** / **Question:** / **Scenario:**).
- Alternating font colors: header text white; content dark gray (`#333`); key terms/questions navy blue (`#004080`) via `<span class="navy-text">` where helpful.
- Wrap all sections inside a main `<div class="review-container">` with light background (`#f9f9f9`), padding 15px, border-radius 8px, small shadow.
- Use semantic HTML: `<h2>`, `<ul>`, `<li>`, and `<p>`, plus `<b>` for key labels.
- Keep the text short, sharp, and easy to scan — avoid long paragraphs.
- Do NOT include type labels or priority banners in the body (e.g. "HIGH PRIORITY"); use only the four sections above.

Here is the preferred HTML structure template (use this exact formatting; include the `<style>` block inside `review-container`):

<div class="review-container">
  <style>
    .header {{ padding: 8px; border-radius: 4px; color: white; font-weight: bold; margin-bottom: 10px; }}
    .blue {{ background-color: #0078D7; }}
    .green {{ background-color: #28a745; }}
    .red {{ background-color: #dc3545; }}
    .yellow {{ background-color: #ffc107; color: #333; }}
    .review-container {{ background-color: #f9f9f9; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); font-family: sans-serif; color: #333; line-height: 1.5; }}
    .navy-text {{ color: #004080; }}
  </style>

  <h2 class="header blue">1. Story Explanation for QC</h2>
  <p><b>Context & Goal:</b> [Explain the business reason for this feature so the tester understands the "why".]</p>
  <p><b>How it Works:</b> [Explain the technical/UI workflow clearly so the tester knows exactly what to look for, replacing the need to read the Azure ticket.]</p>

  <h2 class="header green">2. Key Functional Points</h2>
  <ul>
    <li><b>[Feature/Step]:</b> Brief description of the expected behavior for test case creation.</li>
  </ul>

  <h2 class="header red">3. Edge Cases & Risks</h2>
  <ul>
    <li><b>Risk:</b> Potential system failure point or boundary issue.<br>
        <b>Scenario:</b> <span class="navy-text">What happens if [condition] occurs?</span></li>
  </ul>

  <h2 class="header yellow">4. Ambiguities & Clarification Questions</h2>
  <ul>
    <li><b>Ambiguity:</b> Missing detail in AC or design that blocks testing.<br>
        <b>Question:</b> <span class="navy-text">Specific question to ask the PO/Dev before signing off on test readiness.</span></li>
  </ul>
</div>

**IMPORTANT:**
- Return ONLY the HTML code, starting with `<div class="review-container">` and ending with `</div>` (the closing tag of the outermost review-container).
- Do NOT wrap your response in markdown code fences (triple backticks) and do not add any text outside the HTML structure.
- Replace the bracketed placeholders in section 1 with real paragraphs derived from the user story; do not leave "[Explain...]" as literal text in your output.
- Make sure all HTML is properly formatted and ready to be inserted directly into a webpage.

**IMAGES PROVIDED:**
{len(all_images)} image(s) have been included with this user story. You MUST:
1. Examine each image carefully for visual requirements, UI elements, workflows, and states
2. Compare what you see in images against the acceptance criteria rules
3. Identify any visual elements, UI states, or design specifications shown in images that are NOT documented in the acceptance criteria
4. Note any discrepancies between images and written requirements
5. Flag missing visual documentation (error states, edge cases, different screen sizes, etc.)
6. Reference specific images when identifying risks or ambiguities (e.g., "In Image 1, there is a [element] that is not mentioned in acceptance criteria...")
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

def _ac_step_body(line):
    return re.sub(r'^\s*\d+[\.\)\-]\s*', '', (line or '').strip()).strip()


def _ac_line_looks_like_test_step(line):
    """True if a line is likely a real UI or data-setup step, not a template heading (e.g. filter names only)."""
    body = _ac_step_body(line)
    if not body:
        return False
    procedural = re.compile(
        r'\b(navigate|login|log in|click|select|enter|verify|check|open|close|submit|save|'
        r'add|delete|create|observe|go to|access|fill|type|choose|press|expand|collapse|'
        r'generate|call|use|set|update|backdate|prepare|insert|configure|ensure|execute|apply|'
        r'load|wait|confirm|tap|swipe|apply filter|search)\b',
        re.IGNORECASE,
    )
    data_setup = re.compile(
        r'\b(api|database|db\b|sql|endpoint|backdate|fixture|invoke|graphql|stored procedure|'
        r'postman|swagger|seed)\b',
        re.IGNORECASE,
    )
    if procedural.search(body):
        return True
    if data_setup.search(body):
        return True
    if len(body) >= 95:
        return True
    return False


def _strip_leading_non_actionable_ac_steps(normalized_steps):
    out = list(normalized_steps or [])
    while out and not _ac_line_looks_like_test_step(out[0]):
        out.pop(0)
    return out


def _normalize_generated_test_case(tc):
    """Merge optional preConditions into description for a single textarea / Azure steps."""
    if not isinstance(tc, dict):
        return tc
    pre = tc.get('preConditions') or tc.get('preconditions')
    if isinstance(pre, list):
        pre = '\n'.join(str(x).strip() for x in pre if isinstance(x, str) and x.strip())
    pre = (pre or '').strip() if isinstance(pre, str) else ''
    if not pre:
        return tc
    desc = tc.get('description', '')
    if isinstance(desc, list):
        desc = '\n'.join(str(x) for x in desc)
    desc = (desc or '').strip()
    merged = 'Pre-conditions (Data Setup):\n' + pre
    if desc:
        merged += '\n\nDescription (Main Steps):\n' + desc
    tc['description'] = merged.strip()
    tc.pop('preConditions', None)
    tc.pop('preconditions', None)
    return tc


def _detect_steps_in_acceptance_criteria(acceptance_criteria):
    """Detect if acceptance criteria contains numbered steps or bullet points
    
    Returns:
        tuple: (has_steps: bool, steps_section: str)
    """
    if not acceptance_criteria:
        return False, ""
    
    # Check if user mentions "steps" anywhere in the text (context-aware detection)
    text_lower = acceptance_criteria.lower()
    mentions_steps = bool(re.search(r'\b(step|steps)\b', text_lower))
    
    # Check for numbered steps (1., 2., 3., etc. or 1), 2), 3), etc. or 1-, 2-, 3-, etc.)
    numbered_pattern = r'^\s*\d+[\.\)\-]\s*.+'
    # Check for bullet points (-, *, •)
    bullet_pattern = r'^\s*[-*•]\s+.+'
    # Check for step indicators (also consider these steps, consider the following steps, steps:, etc.)
    step_indicator_pattern = r'(?i)(also\s+consider\s+(these\s+)?steps?|consider\s+the\s+following\s+steps?|steps?:|initial\s+steps?|provided\s+steps?|following\s+steps?)'
    
    lines = acceptance_criteria.split('\n')
    steps_found = []
    in_steps_section = False
    found_step_indicator = False
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped:
            # Allow blank lines within steps section
            if in_steps_section:
                continue
            else:
                continue
        
        # Check for step indicators
        if re.search(step_indicator_pattern, line_stripped):
            found_step_indicator = True
            in_steps_section = True
            continue  # Skip the indicator line itself
        
        # Check if line matches step patterns (including 1- format)
        if re.match(numbered_pattern, line_stripped) or re.match(bullet_pattern, line_stripped):
            in_steps_section = True
            steps_found.append(line_stripped)
        elif in_steps_section and (line_stripped.startswith('-') or line_stripped.startswith('*') or line_stripped.startswith('•') or re.match(r'^\d+[\.\)\-]', line_stripped)):
            # Continue collecting steps
            steps_found.append(line_stripped)
        elif found_step_indicator and in_steps_section:
            # If we found an indicator, continue collecting until we hit a non-step line
            # But only if we've already collected at least one step
            if len(steps_found) > 0:
                # Check if this looks like it could be a continuation (starts with common step words)
                if re.match(r'^\s*(navigate|click|select|enter|verify|check|open|close|submit|save|login|logout|access)', line_stripped, re.IGNORECASE):
                    steps_found.append(line_stripped)
                    continue
            # End of steps section
            break
        elif in_steps_section and not found_step_indicator:
            # End of steps section (only if no indicator was found)
            break
    
    # Also check for steps that might be anywhere in the text (not just sequential)
    # Especially if user mentioned "steps" in context
    if len(steps_found) == 0 or (mentions_steps and len(steps_found) < 2):
        # Try to find any numbered steps anywhere in the text (skip headings / labels)
        for line in lines:
            line_stripped = line.strip()
            if re.match(r'^\s*\d+[\.\)\-]\s*.+', line_stripped) and _ac_line_looks_like_test_step(line_stripped):
                if line_stripped not in steps_found:
                    steps_found.append(line_stripped)
    
    # Normalize step format: convert "1-" to "1." for consistency
    normalized_steps = []
    for step in steps_found:
        # Convert "1-" format to "1." format for better AI understanding
        normalized_step = re.sub(r'^(\s*\d+)\-(\s*)', r'\1.\2', step)
        normalized_steps.append(normalized_step)

    # Sequential scan often stops at a section heading before real UI steps are collected
    if normalized_steps and not any(_ac_line_looks_like_test_step(s) for s in normalized_steps):
        recovered = []
        for line in lines:
            line_stripped = line.strip()
            if re.match(numbered_pattern, line_stripped) and _ac_line_looks_like_test_step(line_stripped):
                normalized_step = re.sub(r'^(\s*\d+)\-(\s*)', r'\1.\2', line_stripped)
                if normalized_step not in recovered:
                    recovered.append(normalized_step)
        if recovered:
            normalized_steps = recovered
    
    if len(normalized_steps) >= 1:  # At least 1 step to be considered a step list
        # When there are multiple "blocks" (e.g. category list then procedural steps),
        # prefer the block that looks like concrete procedural steps (Navigate, Login, Click, etc.)
        procedural_verbs = re.compile(
            r'\b(navigate|login|log in|click|select|enter|verify|check|open|close|submit|save|'
            r'add|delete|create|observe|go to|access|fill|type|choose|press|expand|collapse)\b',
            re.IGNORECASE
        )
        blocks = []
        current_block = []
        for step in normalized_steps:
            m = re.match(r'^\s*(\d+)[\.\)\-]', step)
            num = int(m.group(1)) if m else 0
            if num == 1 and len(current_block) > 0:
                blocks.append(current_block)
                current_block = []
            current_block.append(step)
        if current_block:
            blocks.append(current_block)
        if len(blocks) > 1:
            # Prefer block with most procedural verbs (user's actual test steps)
            best = max(blocks, key=lambda b: sum(1 for s in b if procedural_verbs.search(s)))
            normalized_steps = best
            print(f"DEBUG: _detect_steps_in_acceptance_criteria: Multiple blocks found, using procedural block ({len(normalized_steps)} steps)")
        normalized_steps = _strip_leading_non_actionable_ac_steps(normalized_steps)
        if not normalized_steps:
            print(f"DEBUG: _detect_steps_in_acceptance_criteria: No actionable steps after filtering")
            return False, ""
        steps_text = '\n'.join(normalized_steps)
        print(f"DEBUG: _detect_steps_in_acceptance_criteria: Found {len(normalized_steps)} steps")
        return True, steps_text
    
    print(f"DEBUG: _detect_steps_in_acceptance_criteria: No steps found")
    return False, ""

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
    
    # Detect steps in acceptance criteria, or in story description if none in acceptance criteria
    has_steps, steps_text = _detect_steps_in_acceptance_criteria(acceptance_criteria)
    if not has_steps and story_description:
        has_steps, steps_text = _detect_steps_in_acceptance_criteria(story_description)
        if has_steps:
            print(f"DEBUG: Detected steps in story description (none in acceptance criteria). Steps found: {len(steps_text.splitlines())}")
    steps_text_escaped = ""
    if has_steps:
        step_count = len(steps_text.split('\n'))
        print(f"DEBUG: Detected steps in acceptance criteria/description. Steps found: {step_count}")
        print(f"DEBUG: Steps content (first 500 chars): {steps_text[:500]}")
        # Escape the steps text for use in f-string
        steps_text_escaped = steps_text.replace('{', '{{').replace('}', '}}')
    else:
        print(f"DEBUG: No steps detected in acceptance criteria. Content preview: {acceptance_criteria[:200] if acceptance_criteria else 'None'}")
    
    guideline_map = {
        "Positive": """
**Positive Test Case Guidelines:**
- Verify the core functionality works as expected under normal conditions.
- **CRITICAL: Generate comprehensive positive test cases with NO LIMIT based on the user story requirements.**
- **Cover ALL acceptance criteria:** Create separate positive test cases for EACH acceptance criterion. If there are 10 acceptance criteria, generate at least 10 positive test cases (one per criterion, plus additional test cases for variations and workflows).
- **Cover ALL valid scenarios:** Generate test cases for ALL valid input scenarios from the data dictionary - create separate test cases for each valid field, valid combination, and valid workflow.
- **Cover ALL successful workflows:** Include test cases for ALL successful workflows and happy paths described in the user story title, description, and acceptance criteria.
- **Pagination (for lists):** Generate positive test cases for ALL pagination scenarios (first page, last page, middle pages, navigation controls, page size variations) - create separate test cases for each scenario.
- **Boundary Values (for numeric fields):** Generate positive test cases for ALL valid boundary values (minimum, maximum, zero if allowed, just within limits) - create separate test cases for each boundary value.
- **NO ARTIFICIAL LIMITS:** Do NOT limit the number of positive test cases. Generate as many test cases as needed to comprehensively cover:
  * Every acceptance criterion (at least one test case per criterion, often more)
  * Every valid input scenario from the data dictionary
  * Every successful workflow and happy path
  * Every valid combination of inputs that is meaningful
  * Every valid boundary value for numeric fields
  * Every pagination scenario for lists
- **Comprehensive Coverage Principle:** The goal is to ensure that every aspect of the user story (title, description, acceptance criteria) is covered by positive test cases. Generate enough test cases to provide complete coverage without any artificial constraints.
- **Title Examples:** "[Positive] User successfully creates account with valid information", "[Positive] System saves data when all required fields are completed", "[Positive] Pagination controls work correctly when navigating to page 2", "[Positive] System accepts minimum value (0) for quantity field".""",
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
    
    # Build steps section if steps are detected in acceptance criteria
    steps_section = ""
    if has_steps:
        steps_section = f"""
**CRITICAL: USER-PROVIDED UI STEPS — MANDATORY BEGINNING OF `description`:**
The steps below were detected as concrete user-provided steps. Every test case `description` MUST start with these steps exactly (same order and wording), then continue with more numbered steps until the scenario in the **title** and **expectedResult** is fully covered.

1. **ALWAYS START WITH THE PROVIDED STEPS** in `description` (not in `preConditions`).

2. **THEN ADD STEPS** that complete the specific test case (filters, search, assertions on screen). Do NOT add standalone filter names or section headings as steps.

3. **FORBIDDEN:** Do NOT prepend lines like "Policy Expiry Range" or "Renewal Status" as standalone steps unless they are part of a full imperative sentence.

4. **Numbering:** One continuous sequence (1., 2., …). Provided steps keep their numbers; your added steps continue.

5. **Steps provided by user (MUST appear first in `description`, then add more):**
{steps_text_escaped}

**VALIDATION CHECK:** Each test case's `description` must begin with the provided steps above, then additional actionable UI steps. Put data setup in `preConditions` when you use that field (see JSON format).
"""

    else:
        steps_section = f"""
**GENERATE STEPS ACCORDING TO EACH TEST CASE TITLE AND CONTEXT:**
The user has not provided explicit mandatory steps. Generate appropriate steps for each test case. The `description` field must be **specific to that test case** and aligned with its **title** and **type** ({case_type}).

1. **Title-driven steps:** Concrete, actionable steps in logical order. Do not use two-word labels or template headings as steps.

2. **Context:** Use the user story title, description, acceptance criteria, and data dictionary.

3. **Format:** Number steps (1., 2., 3., …). Typically 3–8 steps per test case.

4. **Consistency:** `description`, `preConditions` (if any), and `expectedResult` must align with the `title`.
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
{steps_section}
{ambiguity_section}
**Universal Guidelines:**
1. **Descriptive Titles:** Create specific, action-oriented titles that clearly describe what functionality is being tested. Avoid generic titles like "Test login" - instead use "User can successfully login with valid email and password".
2. **Consistency First:** For any '{case_type}' test, the `title`, `description`, and `expectedResult` must all be consistent with that scenario. For example, a 'Negative' test's title must describe a failure condition, and its expected result must describe the correct error handling.
3. **Single Condition:** Each test case must focus on verifying exactly ONE condition or scenario. Do not combine multiple test conditions.
4. **Test Coverage Guidelines:**
   - **FOR POSITIVE TEST CASES:** Generate comprehensive test cases with NO LIMIT. Create separate test cases for:
     * Each acceptance criterion (at least one per criterion, often more for variations)
     * Each valid input scenario from the data dictionary
     * Each successful workflow and happy path
     * Each valid combination of inputs
     * Each valid boundary value for numeric fields
     * Each pagination scenario for lists
     * Do NOT consolidate or limit positive test cases - comprehensive coverage is the priority
   - **FOR OTHER TEST TYPES (Negative/Edge Case/Data Flow):** Generate an appropriate number based on story complexity and prioritize critical scenarios
   - **Ambiguity Coverage (for all test types):** When ambiguities exist, create test cases that help clarify them through testing:
     * **For Positive test cases:** Generate separate test cases for each interpretation without limits
     * **For other test types:** Focus on critical contradictions and high-impact ambiguities, consolidate similar scenarios

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
- `description`: Numbered **main execution / UI steps only**. **If mandatory steps were detected above:** start `description` with those exact steps, then continue numbering. Otherwise generate steps from the test case **title**. Never use bare filter or column names as steps.
- `preConditions` (optional string): When instructions distinguish data setup from UI steps, use a numbered list (2–4 lines) of how data is prepared **for this test case title** (flows, API/DB, dates). Omit if not applicable.
- `expectedResult`: A specific and verifiable outcome (exact statuses, visibility vs hidden, or exact empty-state text when requested).

**ID Naming Convention:**
- Positive cases: `TC-POS-[number]`
- Negative cases: `TC-NEG-[number]`
- Edge cases: `TC-EDGE-[number]`
- Data flow cases: `TC-DF-[number]`

Now, generate ONLY the `{case_type}` test cases based on all these instructions.

**IMPORTANT: Generate appropriate test coverage:**
- **FOR POSITIVE TEST CASES - NO LIMITS:**
  * Generate comprehensive positive test cases with NO ARTIFICIAL LIMITS
  * Create AT LEAST one positive test case for EACH acceptance criterion
  * Generate separate positive test cases for EACH valid input scenario from the data dictionary
  * Generate separate positive test cases for EACH successful workflow and happy path
  * Generate separate positive test cases for EACH valid combination of inputs
  * Generate separate positive test cases for EACH valid boundary value (minimum, maximum, zero if allowed, etc.)
  * Generate separate positive test cases for EACH pagination scenario (first page, last page, navigation, etc.)
  * If there are 5 acceptance criteria, generate at least 5 positive test cases (one per criterion) plus additional test cases for variations and workflows
  * If there are 10 acceptance criteria, generate at least 10 positive test cases (one per criterion) plus additional test cases for variations and workflows
  * If there are 20 acceptance criteria, generate at least 20 positive test cases (one per criterion) plus additional test cases for variations and workflows
  * Do NOT consolidate similar positive test cases - each unique scenario should have its own test case
  * Do NOT limit the number of positive test cases - comprehensive coverage is the priority
  * The goal is to ensure every aspect of the user story (title, description, acceptance criteria) is thoroughly covered by positive test cases
- **FOR OTHER TEST TYPES (Negative/Edge Case/Data Flow):**
  * Generate a reasonable number of test cases proportional to the story complexity
  * Prioritize critical scenarios and core functionality
  * Create separate test cases for distinct scenarios, but consolidate similar scenarios that test the same underlying functionality
  * Focus on the most important aspects rather than exhaustive coverage
  * The goal is balanced, meaningful test coverage
- **GENERAL RULES:**
  * Do not generate duplicate test cases. Each test case must be unique in its condition, steps, and expected result.
  * **FOR NEGATIVE TEST CASES SPECIFICALLY: You MUST generate at least 3 negative test cases. If you cannot identify explicit validation rules, generate negative test cases for common failure scenarios such as: missing required inputs, invalid data formats, empty/null values, invalid user actions, or system error conditions. Never return an empty array for negative test cases.**

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
        
        # Process related stories to extract images and tables
        related_stories_processed = []
        related_images = []
        if related_stories:
            print(f"DEBUG: Processing {len(related_stories)} related stories")
            for idx, related_story in enumerate(related_stories):
                related_desc = related_story.get('description', '')
                related_ac = related_story.get('acceptance_criteria', '')
                
                print(f"DEBUG: Related story {idx+1} - Description length: {len(related_desc)}, AC length: {len(related_ac)}")
                print(f"DEBUG: Related story {idx+1} - Description preview (first 200 chars): {related_desc[:200] if related_desc else 'EMPTY'}")
                print(f"DEBUG: Related story {idx+1} - AC preview (first 200 chars): {related_ac[:200] if related_ac else 'EMPTY'}")
                
                # Extract images and text (including tables) from related story HTML
                rel_desc_images, rel_desc_text = extract_images_from_html(related_desc)
                rel_ac_images, rel_ac_text = extract_images_from_html(related_ac)
                
                print(f"DEBUG: Related story {idx+1} - After extraction - Desc text length: {len(rel_desc_text)}, AC text length: {len(rel_ac_text)}")
                if '[TABLE' in rel_desc_text or '[TABLE' in rel_ac_text:
                    print(f"DEBUG: Related story {idx+1} - TABLES DETECTED in extracted text!")
                    # Show table sections for debugging
                    if '[TABLE' in rel_desc_text:
                        table_start = rel_desc_text.find('[TABLE')
                        table_end = rel_desc_text.find('TABLE END]', table_start) + 10
                        if table_end > table_start:
                            print(f"DEBUG: Related story {idx+1} - Table in description: {rel_desc_text[table_start:min(table_end+50, len(rel_desc_text))]}")
                    if '[TABLE' in rel_ac_text:
                        table_start = rel_ac_text.find('[TABLE')
                        table_end = rel_ac_text.find('TABLE END]', table_start) + 10
                        if table_end > table_start:
                            print(f"DEBUG: Related story {idx+1} - Table in AC: {rel_ac_text[table_start:min(table_end+50, len(rel_ac_text))]}")
                
                # Collect images from related stories
                related_images.extend(rel_desc_images)
                related_images.extend(rel_ac_images)
                
                # Create processed related story with extracted text (tables included)
                related_stories_processed.append({
                    'title': related_story.get('title', ''),
                    'description': rel_desc_text,  # Now includes formatted tables
                    'acceptance_criteria': rel_ac_text  # Now includes formatted tables
                })
        
        # Debug: Check if steps are detected in acceptance criteria (after HTML extraction)
        has_steps_debug, steps_text_debug = _detect_steps_in_acceptance_criteria(ac_text)
        print(f"DEBUG: Acceptance criteria text length: {len(ac_text) if ac_text else 0}")
        print(f"DEBUG: Steps detected in acceptance criteria: {has_steps_debug}")
        if has_steps_debug:
            print(f"DEBUG: Detected steps preview: {steps_text_debug[:300]}")
        else:
            print(f"DEBUG: No steps detected. AC preview: {ac_text[:300] if ac_text else 'None'}")
        
        # Collect all images (main story + related stories)
        all_images = desc_images + ac_images + dict_images + related_images
        print(f"DEBUG: Found {len(all_images)} images for test case generation ({len(desc_images + ac_images + dict_images)} from main story, {len(related_images)} from related stories)")
        
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
                        print(f"DEBUG: Calling _generate_cases_for_type for {case_type} with related_stories:", related_stories_processed)
                        # Generate cases for the current type, including images
                        json_text_chunk = _generate_cases_for_type(ai_provider, story_title, desc_text, ac_text, dict_text, case_type, related_stories_processed, all_images, ambiguity_aware)
                        
                        # The API might return an empty or invalid string, so we validate it
                        try:
                            # Validate if it's proper JSON
                            parsed_chunk = json.loads(json_text_chunk)
                            if isinstance(parsed_chunk, list):
                                if parsed_chunk:
                                    for _tc in parsed_chunk:
                                        _normalize_generated_test_case(_tc)
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

