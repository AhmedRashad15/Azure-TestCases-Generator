# Test Genius Project

A web app to generate and upload Azure DevOps test cases using Gemini AI.

## Features
- Generate test cases for a user story using Gemini AI
- Include related user stories for better coverage
- Edit and review test cases before upload
- Upload test cases directly to Azure DevOps Test Plans

## Prerequisites

Before you begin, ensure you have the following installed:
- **Python 3.11 or higher** (check with `python --version` or `python3 --version`)
- **pip** (Python package manager - usually comes with Python)
- **Git** (for cloning the repository)

> 📖 **New to the project?** Check out the detailed [SETUP_GUIDE.md](SETUP_GUIDE.md) for step-by-step instructions with troubleshooting tips.

## Setup Instructions

### Step 1: Clone the Repository

```bash
git clone https://github.com/AhmedRashad15/Azure-TestCases-Generator.git
cd Azure-TestCases-Generator
```

### Step 2: Create a Virtual Environment (Highly Recommended)

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
python -m venv venv
venv\Scripts\activate
```

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

> **Note:** If you get an error about execution policy on Windows PowerShell, run:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### Step 3: Install Python Dependencies

```bash
# Upgrade pip first (recommended)
pip install --upgrade pip

# Install all required packages
pip install -r requirements.txt
```

**Expected output:** You should see all packages installing successfully. If you encounter errors, see the Troubleshooting section below.

### Step 4: Set Up Environment Variables

**⚠️ CRITICAL:** The `.env` file is required for the application to run. Without it, the app will fail to start.

1. **Create a `.env` file** in the root directory of the project (same folder as `app.py`)

2. **Add the following content** to your `.env` file:

```env
# REQUIRED: Google Gemini API Key
# Get your API key from: https://makersuite.google.com/app/apikey
GEMINI_API_KEY=your-actual-gemini-api-key-here

# OPTIONAL: Anthropic Claude API Key (for Claude AI support)
# Get your API key from: https://console.anthropic.com/
# If not provided, Claude features will be unavailable
CLAUDE_API_KEY=your-claude-api-key-here
```

3. **Replace the placeholder values** with your actual API keys:
   - **GEMINI_API_KEY** (Required): Get from [Google AI Studio](https://makersuite.google.com/app/apikey)
   - **CLAUDE_API_KEY** (Optional): Get from [Anthropic Console](https://console.anthropic.com/)

> **Security Note:** Never commit your `.env` file to Git. It's already in `.gitignore` for your protection.

### Step 5: Verify Installation

Before running the app, verify everything is set up correctly:

```bash
# Check Python version (should be 3.11+)
python --version

# Verify Flask is installed
python -c "import flask; print('Flask version:', flask.__version__)"

# Verify environment variables are loaded
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('GEMINI_API_KEY:', 'SET' if os.getenv('GEMINI_API_KEY') else 'NOT SET')"
```

### Step 6: Run the Application

```bash
python app.py
```

You should see output like:
```
 * Serving Flask app 'app'
 * Debug mode: on
 * Running on http://127.0.0.1:5000
```

**Open your browser** and navigate to: `http://localhost:5000`

## Common Setup Issues & Solutions

### Issue 1: "GEMINI_API_KEY not found in .env file"

**Solution:**
- Make sure the `.env` file exists in the root directory (same folder as `app.py`)
- Check that the file is named exactly `.env` (not `.env.txt` or `env`)
- Verify the file contains: `GEMINI_API_KEY=your-actual-key-here`
- On Windows, make sure the file is not hidden and you can see it in File Explorer

### Issue 2: "ModuleNotFoundError" or "No module named 'flask'"

**Solution:**
- Make sure your virtual environment is activated (you should see `(venv)` in your terminal)
- Reinstall dependencies: `pip install -r requirements.txt`
- If using Python 3, try: `python3 -m pip install -r requirements.txt`

### Issue 3: "Python version not supported"

**Solution:**
- Install Python 3.11 or higher from [python.org](https://www.python.org/downloads/)
- Make sure you're using the correct Python version: `python --version`
- If you have multiple Python versions, use: `python3.11` or `py -3.11`

### Issue 4: "Permission denied" on Windows when activating venv

**Solution:**
```powershell
# Run PowerShell as Administrator, then:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Issue 5: Packages fail to install

**Solution:**
```bash
# Upgrade pip first
python -m pip install --upgrade pip

# Try installing with --user flag
pip install --user -r requirements.txt

# Or try with python -m pip
python -m pip install -r requirements.txt
```

### Issue 6: Port 5000 already in use

**Solution:**
- Close other applications using port 5000
- Or modify `app.py` last line to use a different port:
  ```python
  app.run(debug=True, port=5001)  # Use port 5001 instead
  ```

## Usage
1. Enter your Azure DevOps details and User Story ID.
2. Fetch the user story and select any related stories to include.
3. Generate test cases, review/edit as needed.
4. Enter your Test Plan and Suite IDs, then upload test cases to Azure DevOps.

## Deployment
- Push your changes to GitHub:
  ```bash
  git add .
  git commit -m "Update app and docs for deployment"
  git push
  ```

- For production deployment (Azure, Heroku, etc.), add a `Procfile` or `Dockerfile` as needed.

## Troubleshooting

### SSL Certificate Verification Error

If you encounter an error like:
```
SSLError: certificate verify failed: unable to get local issuer certificate
```

This is an environment-specific issue on your machine. Try these solutions:

**Solution 1: Install Python Certificates (Recommended)**
```bash
# Windows - Run PowerShell as Administrator
pip install --upgrade certifi

# Or install certificates manually
python -m pip install --upgrade certifi

# Then locate certificates and update system path if needed
python -c "import certifi; print(certifi.where())"
```

**Solution 2: Update Python SSL Certificates**
```bash
# Install certifi package
pip install certifi

# Windows: Download certificates bundle
# Visit: https://curl.se/ca/cacert.pem
# Save as: C:\Python\cacert.pem (or your Python installation path)
```

**Solution 3: For Corporate Networks**
If you're behind a corporate firewall/proxy:
- Contact your IT department for the corporate CA certificate
- Install it in your system's certificate store
- Or configure proxy settings in your environment

**Solution 4: Temporary Workaround (Not Recommended for Production)**
Only if above solutions don't work and you understand the security implications:
```bash
# Set environment variable (Windows PowerShell)
$env:PYTHONHTTPSVERIFY=0

# Or in Command Prompt
set PYTHONHTTPSVERIFY=0
```
⚠️ **Warning:** This disables SSL verification. Only use for testing, not production.

**Solution 5: Update Python**
Sometimes older Python versions have certificate issues:
```bash
# Download latest Python from python.org
# Make sure to select "Install certificates" option during installation
```

## Notes
- Never commit your PAT or API keys to the repository.
- SSL certificate errors are environment-specific and don't indicate a code issue.
- For issues, open a GitHub issue or contact the maintainer.

## Technologies Used
- Python, Flask
- Google Gemini API
- Azure DevOps Python SDK
- HTML/CSS/JS (frontend)

## Contact
For questions or support, open an issue or contact [Ahmed Rashad](mailto:ahmedmohamed255106@gmail.com).

You can also connect with me on [LinkedIn](https://www.linkedin.com/in/ahmed-rashad-27b1ba229/). 