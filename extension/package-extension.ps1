# Package extension script for Windows PowerShell

Write-Host "Building extension..." -ForegroundColor Green
npm run build

Write-Host "Packaging extension..." -ForegroundColor Green
npm run package

Write-Host "Extension packaged successfully!" -ForegroundColor Green
Write-Host "Check the extension folder for the .vsix file" -ForegroundColor Yellow

