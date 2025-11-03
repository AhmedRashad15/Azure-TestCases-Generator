# Test Genius - Azure DevOps Extension

An Azure DevOps extension that generates comprehensive test cases from user stories using Google Gemini AI.

## Features

- 🔍 **Fetch User Stories** - Automatically fetch user stories from Azure DevOps work items
- 🤖 **AI-Powered Analysis** - Get detailed analysis of user stories with recommendations
- 📝 **Generate Test Cases** - Generate Positive, Negative, Edge Case, and Data Flow test cases
- 📤 **Upload to Test Plans** - Directly upload generated test cases to Azure Test Plans
- 🎨 **Beautiful UI** - Color-coded analysis reports for easy readability

## Prerequisites

- Node.js 18+ and npm
- Azure DevOps account
- Backend API deployed (see backend setup below)
- Google Gemini API key (configured in backend)

## Installation

### For Development

1. **Install dependencies:**
   ```bash
   cd extension
   npm install
   ```

2. **Configure API URL:**
   Edit `src/services/apiService.ts` and update the `API_BASE_URL`:
   ```typescript
   const API_BASE_URL = "https://your-api.azurewebsites.net";
   ```

3. **Build the extension:**
   ```bash
   npm run build
   ```

4. **Package the extension:**
   ```bash
   npm install -g tfx-cli
   npm run package
   ```

### Backend API Setup

The extension requires a backend API to be deployed. You have two options:

#### Option 1: Use the provided Flask API (`app_api.py`)

1. Deploy `app_api.py` to Azure App Service or similar hosting
2. Configure environment variables:
   - `GEMINI_API_KEY` - Your Google Gemini API key
   - `PORT` - Port number (default: 5000)

3. Enable CORS for Azure DevOps origins

#### Option 2: Modify existing Flask app

Add CORS support to your existing `app.py`:
```python
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins=[
    "https://dev.azure.com",
    "https://*.visualstudio.com"
])
```

## Publishing to Marketplace

1. **Create a publisher:**
   - Go to https://aka.ms/vsmarketplace-manage
   - Create a new publisher account

2. **Update manifest:**
   - Edit `vss-extension.json`
   - Update `publisher` field with your publisher ID

3. **Package extension:**
   ```bash
   npm run package
   ```

4. **Upload to Marketplace:**
   - Go to https://marketplace.visualstudio.com/manage
   - Create new extension
   - Upload the generated `.vsix` file

5. **Share/Install:**
   - Share the extension link with your organization
   - Install from the Azure DevOps Marketplace

## Development Workflow

1. **Make changes to source files:**
   - Edit files in `src/` directory
   - Components are in `src/components/`
   - Services are in `src/services/`

2. **Build:**
   ```bash
   npm run build
   ```

3. **Test locally:**
   - Use Azure DevOps extension development tools
   - Or package and install in a test organization

4. **Watch mode (for development):**
   ```bash
   npm run watch
   ```

## Project Structure

```
extension/
├── src/
│   ├── components/        # React components
│   │   ├── App.tsx
│   │   ├── StoryFetcher.tsx
│   │   ├── StoryAnalysis.tsx
│   │   └── TestCaseGenerator.tsx
│   ├── services/          # API and Azure DevOps services
│   │   ├── apiService.ts
│   │   └── azureDevOpsService.ts
│   ├── styles/            # CSS styles
│   │   └── index.css
│   ├── index.html
│   └── index.tsx          # Entry point
├── images/                # Extension icons
├── dist/                  # Built files (generated)
├── vss-extension.json      # Extension manifest
├── package.json
├── tsconfig.json
└── webpack.config.js
```

## Permissions Required

The extension requires these Azure DevOps scopes:
- `vso.work` - Read work items
- `vso.work_write` - Modify work items
- `vso.test_write` - Create test cases
- `vso.test_manage` - Manage test plans

## Troubleshooting

### Extension not loading
- Check browser console for errors
- Verify SDK initialization
- Ensure extension is properly packaged

### API calls failing
- Verify `API_BASE_URL` is correct
- Check CORS settings on backend
- Ensure backend is accessible from Azure DevOps

### Test cases not uploading
- Verify you have `vso.test_write` permission
- Check Test Plan and Suite IDs are correct
- Review browser console for API errors

## Support

For issues or questions:
- Open an issue on GitHub
- Contact: ahmedmohamed255106@gmail.com

## License

MIT

