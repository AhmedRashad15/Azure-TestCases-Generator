import os
from flask import Flask, render_template, request, jsonify, Response
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
import requests
from io import BytesIO
from PIL import Image

# Load environment variables from .env file
load_dotenv()

# --- Configure Gemini API ---
# Create a .env file in your project root and add your Gemini API key:
# GEMINI_API_KEY="YOUR_NEW_SECRET_API_KEY"
# OR provide it via UI (optional)
gemini_api_key = os.getenv("GEMINI_API_KEY")
if gemini_api_key:
    genai.configure(api_key=gemini_api_key)
    print("DEBUG: Gemini API configured from .env file")
else:
    print("WARNING: GEMINI_API_KEY not found in .env file. Users can provide it via UI.")

# --- Configure Claude API ---
claude_api_key = os.getenv("CLAUDE_API_KEY")
claude_client = None
if not claude_api_key:
    print("WARNING: CLAUDE_API_KEY not found in .env file. Claude features will be unavailable.")
else:
    try:
        claude_client = anthropic.Anthropic(api_key=claude_api_key)
        print("DEBUG: Claude API client initialized successfully")
    except Exception as e:
        print(f"ERROR: Failed to initialize Claude API client: {e}")
        print("WARNING: Claude features will be unavailable.")
        claude_client = None

# --- Azure DevOps Configuration ---
# The user will now provide these details in the UI.
# We will get them from the request body in each endpoint.

# --- Flask App ---
app = Flask(__name__)

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

def call_ai_provider(ai_provider, prompt, images=None, gemini_api_key=None, claude_api_key=None):
    """
    Call either Gemini or Claude API based on provider selection.
    Returns the text response from the AI.
    
    Args:
        ai_provider: 'gemini' or 'claude'
        prompt: The prompt text
        images: Optional list of PIL Image objects
        gemini_api_key: Optional Gemini API key (falls back to .env if not provided)
        claude_api_key: Optional Claude API key (falls back to .env if not provided)
    """
    ai_provider = ai_provider.lower() if ai_provider else 'gemini'
    
    if ai_provider == 'claude':
        # Use provided key or fall back to environment variable
        api_key = claude_api_key or os.getenv("CLAUDE_API_KEY")
        if not api_key:
            raise ValueError("Claude API key is required. Please provide CLAUDE_API_KEY in .env file or via UI.")
        
        # Create Claude client with the API key
        try:
            claude_client_instance = anthropic.Anthropic(api_key=api_key)
        except Exception as e:
            raise ValueError(f"Failed to initialize Claude API client: {e}")
        
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
        # Using latest available models (as of 2024-2025)
        # Note: Older models may not be available, so we prioritize newer ones
        claude_models = [
            "claude-3-5-sonnet-20241022",  # Latest Sonnet 3.5 (most capable)
            "claude-3-5-haiku-20241022",   # Latest Haiku 3.5 (faster, cheaper)
            "claude-3-5-sonnet-20240620",  # Fallback to older Sonnet 3.5
            "claude-3-opus-20240229",      # Opus 3.0 (if available)
        ]
        # Removed claude-3-sonnet-20240229 as it's deprecated and causing 404 errors
        
        last_error = None
        for model_name in claude_models:
            try:
                print(f"DEBUG: Trying Claude model: {model_name}")
                # Use higher max_tokens for test case generation (can be large JSON arrays)
                # Edge cases tend to generate more test cases, so use even higher limit
                is_test_case = 'test case' in str(prompt).lower() or 'json array' in str(prompt).lower()
                is_edge_case = 'edge case' in str(prompt).lower()
                if is_edge_case:
                    max_tokens = 16384  # Higher limit for edge cases which generate many test cases
                elif is_test_case:
                    max_tokens = 8192  # Standard limit for other test case types
                else:
                    max_tokens = 4096  # Lower limit for non-test-case operations
                print(f"DEBUG: Using max_tokens={max_tokens} for Claude API call")
                response = claude_client_instance.messages.create(
                    model=model_name,
                    max_tokens=max_tokens,
                    messages=messages
                )
                
                # Check if response was truncated
                stop_reason = getattr(response, 'stop_reason', None)
                if stop_reason == 'max_tokens':
                    print(f"WARNING: Claude response was truncated (hit max_tokens limit). Consider increasing max_tokens or simplifying the prompt.")
                
                # Extract text from Claude response
                if not hasattr(response, 'content') or not response.content:
                    raise ValueError(f"Claude API returned invalid response structure. Response object: {type(response)}")
                
                text_parts = []
                for content_block in response.content:
                    if not hasattr(content_block, 'text'):
                        print(f"WARNING: Content block missing 'text' attribute: {type(content_block)}")
                        continue
                    text_parts.append(content_block.text)
                
                result = ''.join(text_parts).strip()
                if not result:
                    raise ValueError("Claude API returned empty response. This may indicate an issue with the prompt or API configuration.")
                
                print(f"DEBUG: Successfully used Claude model: {model_name}, stop_reason: {stop_reason}, response length: {len(result)}")
                if stop_reason == 'max_tokens':
                    print(f"WARNING: Response may be incomplete due to max_tokens limit. Response ends with: ...{result[-200:]}")
                
                return result
            except Exception as e:
                last_error = e
                error_str = str(e)
                print(f"DEBUG: Claude API error for model {model_name}: {error_str}")
                import traceback
                traceback.print_exc()
                
                # If it's a model not found error, try next model
                if 'not_found_error' in error_str or '404' in error_str or 'model' in error_str.lower() or 'not found' in error_str.lower():
                    print(f"DEBUG: Model {model_name} not available, trying next model...")
                    continue
                # If it's an authentication error, don't try other models
                elif 'authentication' in error_str.lower() or '401' in error_str or '403' in error_str or 'api_key' in error_str.lower():
                    raise ValueError(f"Claude API authentication error: {error_str}. Please check your CLAUDE_API_KEY.")
                # If it's a rate limit error, don't try other models
                elif 'rate_limit' in error_str.lower() or '429' in error_str or 'quota' in error_str.lower():
                    raise ValueError(f"Claude API rate limit exceeded: {error_str}. Please try again later.")
                # If it's a content policy error, don't try other models
                elif 'content_policy' in error_str.lower() or 'safety' in error_str.lower():
                    raise ValueError(f"Claude API content policy violation: {error_str}. The prompt may contain content that violates Claude's usage policies.")
                else:
                    # For other errors, try next model but log the error
                    print(f"WARNING: Error with model {model_name}, trying next model...")
                    continue
        
        # If all models failed, raise a more descriptive error
        if last_error:
            error_str = str(last_error)
            # Check if all failures were due to model not found (404)
            if 'not_found_error' in error_str.lower() or '404' in error_str or ('model' in error_str.lower() and 'not found' in error_str.lower()):
                raise ValueError(f"None of the Claude models are available. The models may have been deprecated or your API key doesn't have access to them. Last error: {error_str}. Please check Anthropic's documentation for available models or contact support.")
            # Provide more specific error messages
            elif 'authentication' in error_str.lower() or '401' in error_str or '403' in error_str or 'api_key' in error_str.lower():
                raise ValueError(f"Claude API authentication failed: {error_str}. Please verify your CLAUDE_API_KEY is correct and has proper permissions.")
            elif 'rate_limit' in error_str.lower() or '429' in error_str or 'quota' in error_str.lower():
                raise ValueError(f"Claude API rate limit exceeded: {error_str}. Please wait a moment and try again, or check your API quota.")
            elif 'content_policy' in error_str.lower() or 'safety' in error_str.lower():
                raise ValueError(f"Claude API content policy violation: {error_str}. The prompt may contain content that violates Claude's usage policies.")
            else:
                raise ValueError(f"All Claude models failed. Last error: {error_str}. Please check your API key, network connection, and try again.")
        else:
            raise ValueError("Failed to get response from Claude API. No models responded successfully.")
    
    else:  # Default to Gemini
        try:
            # Use provided key or fall back to environment variable
            api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("Gemini API key is required. Please provide GEMINI_API_KEY in .env file or via UI.")
            
            # Configure Gemini with the API key
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-flash-latest')
            
            # Build content array with text and images
            content_parts = [prompt]
            if images and len(images) > 0:
                print(f"DEBUG: Adding {len(images)} images to Gemini request")
                for image in images:
                    content_parts.append(image)
            
            # Send to Gemini
            print(f"DEBUG: Sending request to Gemini with {len(content_parts)} content parts")
            if images and len(images) > 0:
                response = model.generate_content(content_parts)
            else:
                response = model.generate_content(prompt)
            
            print(f"DEBUG: Gemini response received, type: {type(response)}")
            
            # Extract text from Gemini response
            if hasattr(response, 'text'):
                result = response.text.strip()
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
        
        # Description and Acceptance Criteria are HTML, preserve them to keep images
        description_html = fields.get('System.Description', '')
        acceptance_criteria_html = fields.get('Microsoft.VSTS.Common.AcceptanceCriteria', '')
        
        # Convert Azure DevOps image URLs to base64 data URLs
        description_html = convert_azure_devops_images_to_base64(description_html, azure_devops_org_url, azure_devops_pat)
        acceptance_criteria_html = convert_azure_devops_images_to_base64(acceptance_criteria_html, azure_devops_org_url, azure_devops_pat)
        
        # Keep HTML for rich text editor (preserves images)
        description_text = description_html
        acceptance_criteria_text = acceptance_criteria_html

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

def _detect_steps_in_acceptance_criteria(acceptance_criteria):
    """Detect if acceptance criteria contains numbered steps or bullet points
    
    Returns:
        tuple: (has_steps: bool, steps_section: str)
    """
    if not acceptance_criteria:
        return False, ""
    
    # Check for numbered steps (1., 2., 3., etc. or 1), 2), 3), etc.)
    numbered_pattern = r'^\s*\d+[\.\)]\s+.+'
    # Check for bullet points (-, *, •)
    bullet_pattern = r'^\s*[-*•]\s+.+'
    # Check for step indicators (also consider these steps, steps:, etc.)
    step_indicator_pattern = r'(?i)(also\s+consider\s+(these\s+)?steps?|steps?:|initial\s+steps?|provided\s+steps?)'
    
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
        
        # Check if line matches step patterns
        if re.match(numbered_pattern, line_stripped) or re.match(bullet_pattern, line_stripped):
            in_steps_section = True
            steps_found.append(line_stripped)
        elif in_steps_section and (line_stripped.startswith('-') or line_stripped.startswith('*') or line_stripped.startswith('•') or re.match(r'^\d+[\.\)]', line_stripped)):
            # Continue collecting steps
            steps_found.append(line_stripped)
        elif found_step_indicator and in_steps_section:
            # If we found an indicator, continue collecting until we hit a non-step line
            # But only if we've already collected at least one step
            if len(steps_found) > 0:
                # Check if this looks like it could be a continuation (starts with common step words)
                if re.match(r'^\s*(navigate|click|select|enter|verify|check|open|close|submit|save|login|logout)', line_stripped, re.IGNORECASE):
                    steps_found.append(line_stripped)
                    continue
            # End of steps section
            break
        elif in_steps_section and not found_step_indicator:
            # End of steps section (only if no indicator was found)
            break
    
    # Also check for steps that might be anywhere in the text (not just sequential)
    if len(steps_found) == 0:
        # Try to find any numbered steps anywhere in the text
        for line in lines:
            line_stripped = line.strip()
            if re.match(numbered_pattern, line_stripped):
                steps_found.append(line_stripped)
    
    if len(steps_found) >= 1:  # At least 1 step to be considered a step list
        steps_text = '\n'.join(steps_found)
        return True, steps_text
    
    return False, ""

def _generate_cases_for_type(ai_provider, story_title, story_description, acceptance_criteria, data_dictionary, case_type, related_stories=None, images=None, ambiguity_aware=True, gemini_api_key=None, claude_api_key=None):
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
        gemini_api_key: Optional Gemini API key (falls back to .env if not provided)
        claude_api_key: Optional Claude API key (falls back to .env if not provided)
    """
    ai_provider = ai_provider.lower() if ai_provider else 'gemini'
    print(f"DEBUG: _generate_cases_for_type called for {case_type} using {ai_provider}. related_stories:", related_stories)
    print(f"DEBUG: Ambiguity-aware generation: {ambiguity_aware}")
    if images:
        print(f"DEBUG: Including {len(images)} images in test case generation")
    
    # Detect steps in acceptance criteria
    has_steps, steps_text = _detect_steps_in_acceptance_criteria(acceptance_criteria)
    steps_text_escaped = ""
    if has_steps:
        print(f"DEBUG: Detected steps in acceptance criteria. Steps found: {len(steps_text.split(chr(10)))}")
        # Escape the steps text for use in f-string
        steps_text_escaped = steps_text.replace('{', '{{').replace('}', '}}')
    guideline_map = {
        "Positive": """
**Positive Test Case Guidelines:**
- Verify the core functionality works as expected under normal conditions.
- Cover all acceptance criteria with positive test cases - create test cases for each acceptance criterion, prioritizing the most important scenarios.
- Test key valid input scenarios from the data dictionary - prioritize critical fields and common use cases rather than exhaustive combinations.
- Generate test cases for important valid combinations of inputs - focus on realistic, high-value scenarios.
- Include test cases for all successful workflows and happy paths - prioritize critical user journeys.
- **Pagination (for lists):** Generate positive test cases for key pagination scenarios (first/last pages, navigation controls) - prioritize the most important scenarios.
- **Boundary Values (for numeric fields):** Generate positive test cases for valid boundary values (minimum, maximum, zero if allowed) - focus on critical fields.
- **Generate 3-12 positive test cases** for most stories, focusing on core functionality and critical paths.
- **Title Examples:** "[Positive] User successfully creates account with valid information", "[Positive] System saves data when all required fields are completed", "[Positive] Pagination controls work correctly when navigating to page 2", "[Positive] System accepts minimum value (0) for quantity field".""",
        "Negative": """
**Negative Test Case Guidelines:**
- **CRITICAL: You MUST ALWAYS generate negative test cases, even for simple stories. Every user story has potential failure scenarios that need to be tested.**
- Test scenarios where inputs are invalid, missing, or unexpected.
- Create separate test cases for key types of invalid input - prioritize critical validation rules and common error scenarios.
- Generate test cases for important invalid scenarios (missing required fields, wrong format, wrong type, out of range) - focus on high-impact validation failures.
- Verify that appropriate error messages are displayed when failures occur - create test cases for critical error scenarios with expected error message in expectedResult.
- Cover key validation rules with negative test cases - prioritize the most important validations rather than exhaustive coverage.
- **If no explicit validation rules are mentioned in the story, generate negative test cases for common scenarios:**
  * Missing required fields/inputs
  * Invalid data formats (if applicable)
  * Empty/null values where data is expected
  * Invalid user actions or workflows
  * System errors or failure conditions
- **Boundary Value Violations (for numeric fields):** Generate negative test cases for critical invalid boundary values (below minimum, above maximum, negative if rejected) with expected error messages - prioritize important fields.
- **Pagination Errors (for lists):** Generate negative test cases for key pagination failures (invalid page number, navigation beyond last page) with expected error messages - focus on common error scenarios.
- **Generate 3-12 negative test cases** for most stories, focusing on critical validation rules and common error scenarios. **Minimum: Generate at least 3 negative test cases even for simple stories.**
- **Title Examples:** "[Negative] System shows error when email field is empty", "[Negative] Application prevents login with invalid password format", "[Negative] System rejects value below minimum (-1) for age field", "[Negative] System handles invalid page number correctly".""",
        "Edge Case": """
**Edge Case & Boundary Guidelines:**
- Test critical boundary conditions from the data dictionary (min/max values, just below min, just above max, etc.) - prioritize the most important boundaries and consolidate similar ones.
- **Numeric Field Boundaries:** For numeric fields, generate test cases for the most critical boundaries: minimum/maximum values, just below/above limits, zero (if applicable), and negative values (if rejected). Prioritize fields that are most critical to the story's functionality - avoid generating separate test cases for every minor variation.
- **Pagination Boundaries:** For lists/data displays, generate test cases for key scenarios: first/last pages, empty lists, single-page scenarios, and critical boundary conditions. Prioritize the most important pagination scenarios rather than exhaustive coverage.
- Include critical scenarios with unexpected user behavior or timing - focus on the most impactful edge cases rather than every possible variation.
- Test performance under important special circumstances (e.g., large data sets, slow networks) - prioritize scenarios most likely to occur or cause issues.
- Cover the most critical edge cases for key input fields, workflows, and system states - focus on high-impact scenarios.
- Generate test cases for unusual but possible scenarios that could cause significant issues - avoid minor edge cases that are unlikely to occur.
- **Generate 5-15 edge case test cases** for most stories, prioritizing critical boundaries and high-impact scenarios over exhaustive coverage.
- **Title Examples:** "[Edge Case] System handles maximum character limit in description field", "[Edge Case] Application maintains functionality during network interruption", "[Edge Case] System validates minimum value (0) for quantity field", "[Edge Case] Pagination works correctly when list contains exactly one page of items".""",
        "Data Flow": """
**Data Flow Guidelines:**
- Verify how data moves through the system from input to storage and output - create test cases for key data flow paths, prioritizing critical workflows.
- Track data through important workflows to verify integrity - generate test cases for the most critical complete workflows.
- Test data persistence (saving) and retrieval (loading) - create test cases for key persistence scenarios, focusing on critical data operations.
- Cover important data transformations, validations, and transfers - prioritize high-impact data flows rather than exhaustive coverage.
- Generate test cases for data flow through key system components and modules - focus on critical integration points.
- **Generate 2-8 data flow test cases** for most stories, focusing on critical data paths and important workflows.
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
When generating test cases, pay special attention to any ambiguities, contradictions, or unclear requirements in the acceptance criteria. These ambiguities should inform your test case generation with comprehensive coverage:

**COMPREHENSIVE COVERAGE APPROACH:**
- **Generate separate test cases for each interpretation** - Create distinct test cases for different ways an ambiguity could be resolved
- **Cover all critical contradictions** - Generate test cases for all logical inconsistencies that would cause implementation confusion
- **Create separate test cases for each scenario** - Do NOT consolidate similar scenarios; each unique condition should have its own test case
- **Comprehensive coverage over minimal sets** - Generate thorough test coverage to ensure all scenarios are tested
- **Cover all testable ambiguities** - Generate test cases for all ambiguities that can be verified through testing

1. **Contradictions and Logical Inconsistencies (HIGH PRIORITY):**
   - If you find contradictory statements (e.g., "status will be approved" but "no approval needed"), create **separate test cases** for each critical interpretation
   - Generate test cases that verify the most likely scenario AND all alternative interpretations
   - Focus on contradictions that would cause confusion during implementation
   - **Example:** "status will be approved (No need to be approved)" → Generate multiple test cases:
     * One verifying status becomes "approved" automatically (most likely interpretation)
     * One verifying the workflow doesn't require approval step (clarifying the contradiction)
     * One verifying the status transition behavior in edge cases

2. **Vague Terms and Multiple Interpretations (MEDIUM PRIORITY):**
   - If requirements use vague terms (e.g., "quickly", "appropriate", "user-friendly"), create **separate test cases** for each critical interpretation
   - Generate test cases for all boundary conditions that could cause issues
   - Cover vague terms that affect core functionality AND minor UI concerns

3. **Missing Information (MEDIUM PRIORITY):**
   - If information is missing (e.g., no error handling specified), create **separate test cases** for all critical missing scenarios
   - Generate test cases for missing information that affects core functionality, security, AND edge cases
   - Cover common edge cases AND uncommon scenarios that are still possible

4. **Status/State Ambiguities (HIGH PRIORITY):**
   - If status changes are ambiguous or contradictory, create **separate test cases** for all critical status transitions
   - Generate test cases for status changes that affect workflow, business logic, AND edge cases
   - Cover both contradictions AND simple ambiguities

5. **Permission/Role Ambiguities (HIGH PRIORITY):**
   - If permissions or roles are unclear, create **separate test cases** for all critical permission scenarios
   - Generate test cases for security-critical ambiguities AND non-critical permission scenarios
   - Cover scenarios that could lead to unauthorized access AND scenarios that verify proper access control
"""
    else:
        ambiguity_section = ""
    
    # Build steps section if steps are detected in acceptance criteria
    steps_section = ""
    if has_steps:
        steps_section = f"""
**CRITICAL: STEPS DETECTED IN ACCEPTANCE CRITERIA - MUST BE INCLUDED:**
The acceptance criteria contains explicit steps provided by the user. These steps MUST ALWAYS be included in every test case description. Follow these requirements:

1. **ALWAYS START WITH PROVIDED STEPS:** The steps from the acceptance criteria MUST be used as the INITIAL steps in every test case description. Do NOT skip, ignore, or replace these steps.

2. **Preserve Step Order and Content:** 
   - Use the provided steps EXACTLY as they appear, maintaining their original order
   - Keep the same numbering format (1., 2., 3., etc.)
   - Preserve the exact wording and details from the provided steps
   - These are the user's required initial steps and must appear first

3. **Complete the Workflow:** After including ALL the provided steps, ADD additional steps to complete the test case workflow based on the test case type ({case_type}):
   - For **Positive** test cases: Add steps showing successful completion after the provided steps
   - For **Negative** test cases: Add steps showing where validation fails or errors occur (after the provided steps)
   - For **Edge Case** test cases: Add steps showing boundary conditions or unusual scenarios (after the provided steps)
   - For **Data Flow** test cases: Add steps tracing data through the system (after the provided steps)

4. **Step Formatting:** Format all steps as numbered steps (e.g., "1. Step one\\n2. Step two\\n3. Step three"). The provided steps should be numbered starting from 1, and your additional steps should continue the numbering sequence.

5. **Steps from Acceptance Criteria (MUST BE INCLUDED AS INITIAL STEPS):**
{steps_text_escaped}

**CRITICAL REQUIREMENT:** Every test case description MUST begin with these exact steps in this exact order. Then, add additional steps to complete the test scenario. Never omit, skip, or replace the provided steps - they are mandatory initial steps that must appear in every test case.
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
4. **Balanced Test Coverage:** Generate an appropriate number of test cases based on story complexity:
   - **For simple stories (1-3 acceptance criteria, few fields):** Generate 3-8 test cases per type (Positive/Negative/Edge Case/Data Flow)
   - **For medium stories (4-7 acceptance criteria, moderate fields):** Generate 5-12 test cases per type
   - **For complex stories (8+ acceptance criteria, many fields/workflows):** Generate 8-20 test cases per type
   - **Prioritize critical scenarios:** Focus on high-priority test cases that verify core functionality and critical paths first
   - **Cover all acceptance criteria:** Create test cases for each acceptance criterion, but consolidate similar scenarios when they test the same underlying functionality
   - **Data dictionary coverage:** Generate test cases for key valid/invalid scenarios from the data dictionary, prioritizing the most important fields and validation rules
   - **Edge cases:** Include the most critical boundary conditions and error scenarios, but avoid generating excessive test cases for minor variations
   - **Avoid over-generation:** Do not create separate test cases for every minor variation - consolidate similar scenarios that test the same core functionality
   - **Quality over quantity:** Generate fewer, well-designed test cases that provide meaningful coverage rather than many redundant test cases

5. **Pagination Testing (for Lists):**
   - For LISTS (user lists, product lists, search results, reports, dashboards), generate test cases for key scenarios: first/last pages, empty lists, single-page scenarios, and critical boundary conditions. Prioritize the most important pagination scenarios (typically 2-4 test cases) rather than exhaustive coverage of every possible pagination variation.

6. **Boundary Value Testing (for Numeric Fields):**
   - For NUMERIC fields (integers, decimals, percentages, counts, amounts, ages, etc.), generate test cases for critical boundaries: minimum/maximum values, just below/above limits, zero (if applicable), and negative values (if rejected). Prioritize fields critical to the story's functionality - typically generate 2-5 boundary test cases per important numeric field rather than testing every possible boundary for every field.

7. **Error Messages for Invalid Values:**
   - For invalid field inputs, generate separate negative test cases verifying appropriate error messages are displayed. Each invalid scenario (empty fields, wrong format, wrong type, out of range, boundary violations) should have its own test case with the expected error message specified in the expectedResult field.

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

**IMPORTANT: Generate appropriate test coverage:**
- Generate a reasonable number of test cases proportional to the story complexity (see guidelines above)
- Prioritize critical scenarios and core functionality over minor variations
- Create separate test cases for distinct scenarios, but consolidate similar scenarios that test the same underlying functionality
- Each acceptance criterion should have test cases, but focus on the most important aspects rather than exhaustive coverage
- For data dictionary entries, prioritize key fields and critical validation rules rather than testing every possible combination
- Generate test cases for important workflows, critical error scenarios, and significant boundary conditions
- The goal is balanced, meaningful test coverage - avoid both minimal sets and excessive over-generation
- Do not generate duplicate test cases. Each test case must be unique in its condition, steps, and expected result.
- If the story is simple, generate fewer test cases. If complex, generate more, but always stay within reasonable bounds (typically 5-15 test cases per type for most stories).
- **FOR NEGATIVE TEST CASES SPECIFICALLY: You MUST generate at least 3 negative test cases. If you cannot identify explicit validation rules, generate negative test cases for common failure scenarios such as: missing required inputs, invalid data formats, empty/null values, invalid user actions, or system error conditions. Never return an empty array for negative test cases.**

**CRITICAL: You MUST return ONLY a valid JSON array. Do not include any explanatory text, markdown formatting, or code blocks. Return ONLY the JSON array starting with [ and ending with ].**
"""
    try:
        # Use the helper function to call the appropriate AI provider
        response_text = call_ai_provider(
            ai_provider, 
            prompt, 
            images if images and len(images) > 0 else None,
            gemini_api_key=gemini_api_key,
            claude_api_key=claude_api_key
        )
        
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
                            images if images and len(images) > 0 else None,
                            gemini_api_key=gemini_api_key,
                            claude_api_key=claude_api_key
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
            print(f"DEBUG: JSON error position: {getattr(json_err, 'pos', 'unknown')}")
            print(f"DEBUG: Attempted to parse (first 500 chars): {clean_json_text[:500]}...")
            print(f"DEBUG: Attempted to parse (last 500 chars): ...{clean_json_text[-500:]}")
            
            # Try to fix incomplete JSON array (might be truncated)
            if clean_json_text.strip().startswith('[') and not clean_json_text.strip().endswith(']'):
                print(f"WARNING: JSON array appears incomplete (starts with [ but doesn't end with ]). Response may have been truncated.")
                # Try to extract valid JSON objects before the truncation
                try:
                    # Find the last complete JSON object
                    last_comma = clean_json_text.rfind(',')
                    if last_comma > 0:
                        # Try to close the array
                        potential_json = clean_json_text[:last_comma] + ']'
                        test_parse = json.loads(potential_json)
                        if isinstance(test_parse, list) and len(test_parse) > 0:
                            print(f"WARNING: Recovered {len(test_parse)} test cases from truncated response")
                            return json.dumps(test_parse)
                except:
                    pass
            
            return "[]"
        
        return clean_json_text
    except ValueError as ve:
        # Re-raise ValueError (these are user-friendly error messages)
        import traceback
        print(f"ERROR generating {case_type} cases: {ve}")
        traceback.print_exc()
        raise  # Re-raise to be caught by the streaming endpoint
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"ERROR generating {case_type} cases: {error_msg}")
        traceback.print_exc()
        # Return empty array but log the error for debugging
        return "[]"

@app.route('/generate_test_cases', methods=['POST', 'GET'])
def generate_test_cases_stream():
    """Generate test cases with streaming support - supports both GET (legacy) and POST (for large payloads)"""
    print("DEBUG: /generate_test_cases endpoint called.")
    
    try:
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

        story_title = data.get('story_title')
        story_description = data.get('story_description', '')
        acceptance_criteria = data.get('acceptance_criteria')
        data_dictionary = data.get('data_dictionary', '')
        related_stories = data.get('related_stories', [])
        ai_provider = data.get('ai_provider', 'gemini')  # Default to Gemini
        ambiguity_aware = data.get('ambiguity_aware', True)  # Default to True for backward compatibility
        if isinstance(ambiguity_aware, str):
            ambiguity_aware = ambiguity_aware.lower() in ('true', '1', 'yes', 'on')
        
        # Extract optional API keys from request
        gemini_api_key = data.get('gemini_api_key', '').strip() or None
        claude_api_key = data.get('claude_api_key', '').strip() or None

        print("DEBUG: related_stories received in endpoint:", related_stories)
        print(f"DEBUG: AI Provider: {ai_provider}")
        print(f"DEBUG: Ambiguity-aware generation: {ambiguity_aware}")
        print(f"DEBUG: API keys provided via UI - Gemini: {'Yes' if gemini_api_key else 'No'}, Claude: {'Yes' if claude_api_key else 'No'}")

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

                for case_type in case_types:
                    try:
                        print(f"DEBUG: Calling _generate_cases_for_type for {case_type} with related_stories:", related_stories)
                        # Generate cases for the current type, including images
                        json_text_chunk = _generate_cases_for_type(
                            ai_provider, story_title, desc_text, ac_text, dict_text, case_type, 
                            related_stories, all_images, ambiguity_aware,
                            gemini_api_key=gemini_api_key,
                            claude_api_key=claude_api_key
                        )
                        
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
                    except ValueError as ve:
                        # ValueError from call_ai_provider - these are user-friendly messages
                        import traceback
                        print(f"ERROR generating {case_type} cases: {ve}")
                        traceback.print_exc()
                        # Send detailed error to client
                        error_data = {
                            "type": "error",
                            "case_type": case_type,
                            "error": f"Failed to generate {case_type} cases",
                            "message": str(ve),
                            "is_critical": True  # Mark as critical so frontend can show it prominently
                        }
                        yield f"data: {json.dumps(error_data)}\n\n"
                        # For critical errors (auth, rate limit), stop processing
                        if 'authentication' in str(ve).lower() or 'rate limit' in str(ve).lower() or 'quota' in str(ve).lower():
                            yield "data: {\"type\": \"done\", \"message\": \"Generation stopped due to critical error.\"}\n\n"
                            return
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
        print(f"CRITICAL ERROR in generate_test_cases_stream endpoint: {e}")
        traceback.print_exc()
        # Return a proper error response instead of letting the connection reset
        error_response = jsonify({
            'error': 'Failed to initialize test case generation',
            'message': str(e)
        })
        error_response.status_code = 500
        error_response.headers['Access-Control-Allow-Origin'] = '*'
        return error_response

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

@app.route('/analyze_story', methods=['POST', 'GET'])
def analyze_story():
    """Analyze a user story and provide structured review"""
    print("DEBUG: /analyze_story endpoint called")
    try:
        # Support both GET (legacy) and POST (for large payloads with images)
        if request.method == 'POST':
            try:
                data = request.json or {}
                if not data:
                    error_response = jsonify({'error': 'Payload missing.'})
                    error_response.headers['Access-Control-Allow-Origin'] = '*'
                    error_response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
                    error_response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                    return error_response, 400
            except Exception as e:
                error_response = jsonify({'error': f'Invalid JSON payload: {str(e)}'})
                error_response.headers['Access-Control-Allow-Origin'] = '*'
                error_response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
                error_response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                return error_response, 400
        else:
            # GET request (legacy support)
            payload_str = request.args.get('payload')
            if not payload_str:
                error_response = jsonify({'error': 'Payload missing.'})
                error_response.headers['Access-Control-Allow-Origin'] = '*'
                error_response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
                error_response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                return error_response, 400
            try:
                data = json.loads(unquote(payload_str))
            except json.JSONDecodeError as e:
                error_response = jsonify({'error': f'Invalid payload: {str(e)}'})
                error_response.headers['Access-Control-Allow-Origin'] = '*'
                error_response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
                error_response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                return error_response, 400
        
        print(f"DEBUG: Request data keys: {data.keys() if data else 'None'}")
        
        story_title = data.get('story_title')
        story_description = data.get('story_description', '')
        acceptance_criteria = data.get('acceptance_criteria', '')
        related_test_cases = data.get('related_test_cases', '')
        ai_provider = data.get('ai_provider', 'gemini')  # Default to Gemini
        
        # Extract optional API keys from request
        gemini_api_key = data.get('gemini_api_key', '').strip() or None
        claude_api_key = data.get('claude_api_key', '').strip() or None
        
        print(f"DEBUG: Story title: {story_title}")
        print(f"DEBUG: Story description length: {len(story_description)}")
        print(f"DEBUG: Acceptance criteria length: {len(acceptance_criteria)}")
        print(f"DEBUG: AI Provider: {ai_provider}")
        print(f"DEBUG: API keys provided via UI - Gemini: {'Yes' if gemini_api_key else 'No'}, Claude: {'Yes' if claude_api_key else 'No'}")
        
        if not story_title:
            print("ERROR: Story title is missing")
            error_response = jsonify({'error': 'Story Title is required.'})
            error_response.headers['Access-Control-Allow-Origin'] = '*'
            error_response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            error_response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
            return error_response, 400
        
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

For each ambiguity found, provide ONLY:
- **Ambiguity:** Clear description of what's unclear, missing, or contradictory (specifically highlight contradictions if found)
- **Question:** Specific question to ask the Product Owner to clarify this

**IMPORTANT:** Do NOT include type labels, categories, or priority levels (e.g., "HIGH PRIORITY", "Contradictions", "Status/State Ambiguities", etc.) in the output. Only provide the ambiguity description and the question.

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

### 🎨 UI Rendering Guidelines
Return your final output formatted as **HTML** (not markdown), following these visual and structural rules:

- Each section should be wrapped in a `<div>` with a unique color-coded header:
  - **1. Summary:** Blue header (`#0078D7`)
  - **2. Key Functional Points:** Green header (`#28a745`)
  - **3. Ambiguities & Questions:** Yellow header (`#ffc107`)
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
</div>
```

**IMPORTANT:** 
- Return ONLY the HTML code, starting with `<div class="review-container">` and ending with `</div>`.
- Do NOT include markdown formatting, code blocks with triple backticks, or any text outside the HTML structure.
- Make sure all HTML is properly formatted and ready to be inserted directly into a webpage.

**IMAGES PROVIDED:**
If images are included with the user story (either embedded in HTML or provided separately), you MUST:
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
            analysis_text = call_ai_provider(
                ai_provider, 
                prompt, 
                all_images if len(all_images) > 0 else None,
                gemini_api_key=gemini_api_key,
                claude_api_key=claude_api_key
            )
            
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
        
        response = jsonify({'analysis': analysis_text})
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        return response
    except Exception as e:
        import traceback
        print(f"Error generating analysis: {e}")
        traceback.print_exc()
        error_response = jsonify({'error': str(e)})
        error_response.headers['Access-Control-Allow-Origin'] = '*'
        error_response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        error_response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        return error_response, 500

def convert_azure_devops_images_to_base64(html_content, org_url, pat_token):
    """Convert Azure DevOps image URLs to base64 data URLs for display in rich text editor"""
    if not html_content:
        return html_content
    
    soup = BeautifulSoup(html_content, 'html.parser')
    images = soup.find_all('img')
    
    for img in images:
        src = img.get('src', '')
        if not src:
            continue
        
        # Skip if already a data URL
        if src.startswith('data:image'):
            continue
        
        try:
            image_url = src
            
            # Convert vstfs:// URLs to REST API URLs
            if src.startswith('vstfs:///'):
                # Extract attachment ID from vstfs URL
                # vstfs:///Attachments/Attachments/[attachment-id]/filename
                match = re.match(r'/Attachments/([^/]+)', src)
                if match and match.group(1):
                    attachment_id = match.group(1)
                    filename = img.get('alt', 'image.png')
                    image_url = f"{org_url}/_apis/wit/attachments/{attachment_id}?fileName={filename}"
                else:
                    print(f"WARNING: Could not parse vstfs URL: {src}")
                    continue
            
            # Make relative URLs absolute
            if image_url.startswith('/'):
                image_url = f"{org_url}{image_url}"
            
            # Only process Azure DevOps URLs (skip external URLs)
            if not ('/_apis/' in image_url or 'visualstudio.com' in image_url or 'dev.azure.com' in image_url):
                continue
            
            # Fetch image and convert to base64
            headers = {
                'Authorization': f'Basic {base64.b64encode(f":{pat_token}".encode()).decode()}'
            }
            response = requests.get(image_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                # Determine content type
                content_type = response.headers.get('Content-Type', 'image/png')
                if not content_type.startswith('image/'):
                    content_type = 'image/png'
                
                # Convert to base64
                image_base64 = base64.b64encode(response.content).decode('utf-8')
                data_url = f"data:{content_type};base64,{image_base64}"
                img['src'] = data_url
                print(f"Successfully converted Azure DevOps image to base64")
            else:
                print(f"WARNING: Failed to fetch Azure DevOps image: {image_url} (Status: {response.status_code})")
        except Exception as e:
            print(f"ERROR: Failed to convert Azure DevOps image to base64: {e}")
            # Keep original URL as fallback
    
    return str(soup)

@app.route('/test_error')
def test_error():
    raise Exception("This is a test error!")

if __name__ == '__main__':
    app.run(debug=True) 