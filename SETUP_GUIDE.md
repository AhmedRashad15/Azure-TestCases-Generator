# Complete Setup Guide for Team Members

This guide will help you set up the Test Genius Project on your local machine.

## 📋 Quick Checklist

Before starting, make sure you have:
- [ ] Python 3.11 or higher installed
- [ ] Git installed
- [ ] Access to Google Gemini API (or Claude API)
- [ ] Internet connection

## 🚀 Step-by-Step Setup

### 1. Clone the Repository

```bash
git clone https://github.com/AhmedRashad15/Azure-TestCases-Generator.git
cd Azure-TestCases-Generator
```

### 2. Verify Python Installation

```bash
# Check Python version (must be 3.11 or higher)
python --version
# OR
python3 --version
```

**If Python is not installed:**
- Download from [python.org](https://www.python.org/downloads/)
- **Important:** During installation, check "Add Python to PATH"

### 3. Create Virtual Environment

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

**If you get execution policy error on Windows PowerShell:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 4. Install Dependencies

```bash
# Upgrade pip first
pip install --upgrade pip

# Install all required packages
pip install -r requirements.txt
```

**Expected packages:**
- Flask==3.0.0
- google-generativeai==0.3.1
- anthropic==0.18.1
- azure-devops==7.1.0
- beautifulsoup4==4.12.2
- Pillow==10.1.0
- And others...

### 5. Create .env File

**⚠️ THIS IS REQUIRED - The app will not work without it!**

1. In the root directory (same folder as `app.py`), create a new file named `.env`

2. Copy this template into your `.env` file:

```env
# REQUIRED: Google Gemini API Key
# Get your API key from: https://makersuite.google.com/app/apikey
GEMINI_API_KEY=your-actual-gemini-api-key-here

# OPTIONAL: Anthropic Claude API Key
# Get your API key from: https://console.anthropic.com/
# If not provided, Claude features will be unavailable
CLAUDE_API_KEY=your-claude-api-key-here
```

3. **Replace the placeholder** with your actual API key:
   - Remove `your-actual-gemini-api-key-here`
   - Paste your real API key (no quotes needed)

**How to get API keys:**
- **Gemini API Key:** Visit [Google AI Studio](https://makersuite.google.com/app/apikey) and create a new API key
- **Claude API Key (Optional):** Visit [Anthropic Console](https://console.anthropic.com/) and create an API key

### 6. Verify Setup

Run these commands to verify everything is correct:

```bash
# Check Python version
python --version

# Verify Flask is installed
python -c "import flask; print('✅ Flask installed')"

# Check if .env file is loaded
python -c "from dotenv import load_dotenv; import os; load_dotenv(); key = os.getenv('GEMINI_API_KEY'); print('✅ GEMINI_API_KEY:', 'SET' if key else '❌ NOT SET')"
```

### 7. Run the Application

```bash
python app.py
```

You should see:
```
 * Serving Flask app 'app'
 * Debug mode: on
 * Running on http://127.0.0.1:5000
```

**Open your browser** and go to: `http://localhost:5000`

## 🔧 Troubleshooting

### Problem: "GEMINI_API_KEY not found in .env file"

**Solutions:**
1. Make sure `.env` file exists in the root directory (same folder as `app.py`)
2. Check the file name is exactly `.env` (not `.env.txt` or `env.txt`)
3. On Windows, make sure file extensions are visible:
   - File Explorer → View → Show file extensions
4. Verify the content looks like: `GEMINI_API_KEY=your-key-here` (no spaces around `=`)
5. Make sure you saved the file after editing

### Problem: "ModuleNotFoundError: No module named 'flask'"

**Solutions:**
1. Make sure virtual environment is activated (you should see `(venv)` in terminal)
2. Reinstall dependencies: `pip install -r requirements.txt`
3. Try: `python -m pip install -r requirements.txt`

### Problem: "Python version not supported"

**Solutions:**
1. Install Python 3.11 or higher from [python.org](https://www.python.org/downloads/)
2. Make sure Python is added to PATH during installation
3. Restart your terminal after installation

### Problem: "Port 5000 already in use"

**Solutions:**
1. Close other applications using port 5000
2. Or change the port in `app.py` (last line):
   ```python
   app.run(debug=True, port=5001)
   ```

### Problem: Packages fail to install

**Solutions:**
```bash
# Try upgrading pip first
python -m pip install --upgrade pip

# Try installing with --user flag
pip install --user -r requirements.txt

# If on Windows and getting errors, try:
python -m pip install -r requirements.txt --no-cache-dir
```

### Problem: SSL Certificate Error

If you see SSL errors when the app tries to connect to APIs:

```bash
# Install/upgrade certifi
pip install --upgrade certifi
```

## ✅ Verification Checklist

Before reporting issues, verify:

- [ ] Python 3.11+ is installed and accessible
- [ ] Virtual environment is created and activated
- [ ] All packages from `requirements.txt` are installed
- [ ] `.env` file exists in root directory
- [ ] `.env` file contains `GEMINI_API_KEY=your-actual-key`
- [ ] No typos in `.env` file (especially around the `=` sign)
- [ ] Terminal/command prompt is in the project root directory
- [ ] Virtual environment is activated (see `(venv)` in prompt)

## 📞 Need Help?

If you're still having issues:
1. Check the main [README.md](README.md) for more details
2. Open an issue on GitHub
3. Contact the team lead

## 🔒 Security Reminders

- **Never commit your `.env` file to Git**
- **Never share your API keys** in chat, email, or screenshots
- **The `.env` file is already in `.gitignore`** - don't remove it
- If you accidentally commit API keys, rotate them immediately

