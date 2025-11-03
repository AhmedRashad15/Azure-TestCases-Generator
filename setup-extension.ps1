# Setup Extension Script
# This script will install dependencies and build the extension

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Test Genius Extension Setup" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Check if we're in the right directory
if (-not (Test-Path "package.json")) {
    Write-Host "ERROR: package.json not found!" -ForegroundColor Red
    Write-Host "Please run this script from the extension directory" -ForegroundColor Yellow
    exit 1
}

Write-Host "Step 1: Installing Node.js dependencies..." -ForegroundColor Green
npm install

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: npm install failed!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Step 2: Building extension..." -ForegroundColor Green
npm run build

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Build failed!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Extension setup complete!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Deploy backend to Azure (see STEP_BY_STEP_GUIDE.md)" -ForegroundColor White
Write-Host "2. Update API URL in src/services/apiService.ts with Azure URL" -ForegroundColor White
Write-Host "3. Run 'npm run build' again" -ForegroundColor White
Write-Host "4. Run 'npm run package' to create .vsix file" -ForegroundColor White
Write-Host ""

