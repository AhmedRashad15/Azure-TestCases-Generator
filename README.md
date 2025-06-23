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
   - Create a `.env` file in the root directory (optional, for secrets).
   - Add your Gemini API key and any other secrets as needed.

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

## Notes
- Never commit your PAT or API keys to the repository.
- For issues, open a GitHub issue or contact the maintainer.

## Technologies Used
- Python, Flask
- Google Gemini API
- Azure DevOps Python SDK
- HTML/CSS/JS (frontend)

## Contact
For questions or support, open an issue or contact [Ahmed Rashad](mailto:ahmedmohamed255106@gmail.com).

You can also connect with me on [LinkedIn](https://www.linkedin.com/in/ahmed-rashad-27b1ba229/). 