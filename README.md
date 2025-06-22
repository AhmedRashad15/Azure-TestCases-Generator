# Azure DevOps Test Case Generator

A web application to automatically generate and upload high-quality test cases for Azure DevOps user stories using Google Gemini AI.

## Features
- Modern Flask web app UI
- Secure Azure DevOps integration (PAT, org, project, etc. via UI)
- Uses Gemini API for advanced test case generation (positive, negative, edge, data flow)
- Real-time streaming of generated test cases
- Robust de-duplication and error handling
- Uploads test cases directly to Azure DevOps Test Plans
- Mobile app awareness and platform-specific test generation

## Setup
1. **Clone the repository:**
   ```sh
   git clone https://github.com/AhmedRashad15/Azure-TestCases-Generator.git
   cd Azure-TestCases-Generator
   ```
2. **Install dependencies:**
   ```sh
   pip install -r requirements.txt
   ```
3. **Configure Gemini API Key:**
   - Create a `.env` file in the project root:
     ```
     GEMINI_API_KEY=your_gemini_api_key_here
     ```
4. **Run the app:**
   ```sh
   python app.py
   ```

## Usage
- Open the app in your browser (default: http://localhost:5000)
- Enter your Azure DevOps credentials and user story ID
- Generate, review, and upload test cases to your Azure DevOps Test Plan

## Technologies Used
- Python, Flask
- Google Gemini API
- Azure DevOps Python SDK
- HTML/CSS/JS (frontend)

## Contact
For questions or support, open an issue or contact [Ahmed Rashad](mailto:ahmedmohamed255106@gmail.com). 