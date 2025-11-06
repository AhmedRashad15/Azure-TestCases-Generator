# Test Genius Project

A web app to generate and upload Azure DevOps test cases using Gemini AI.

## Features
- Generate test cases for a user story using Gemini AI
- Include related user stories for better coverage
- Edit and review test cases before upload
- Upload test cases directly to Azure DevOps Test Plans

## Setup

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd <repo-folder>
   ```

2. **Create a virtual environment (recommended):**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   - Create a `.env` file in the root directory.
   - **Required:** Add your Gemini API key:
     ```
     GEMINI_API_KEY=your-actual-api-key-here
     ```
   - Get your Gemini API key from: https://makersuite.google.com/app/apikey
   - **Note:** The `.env` file is not included in the repository for security reasons. Each user must create their own.

5. **Run the app:**
   ```bash
   python app.py
   ```
   The app will be available at `http://localhost:5000`.

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