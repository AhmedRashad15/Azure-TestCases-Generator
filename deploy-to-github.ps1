# PowerShell script to deploy stable version to GitHub
# Excludes .md files (except README.md) and other unnecessary files

Write-Host "🚀 Deploying stable version to GitHub..." -ForegroundColor Green
Write-Host ""

# Check if git is initialized
if (-not (Test-Path ".git")) {
    Write-Host "⚠️  Git not initialized. Initializing..." -ForegroundColor Yellow
    git init
}

# Check current git status
Write-Host "📋 Checking git status..." -ForegroundColor Cyan
git status

Write-Host ""
Write-Host "📦 Files to be committed (excluding .md files, node_modules, dist, etc.):" -ForegroundColor Cyan

# Add all files (gitignore will exclude .md files and other unnecessary files)
git add .

# Show what will be committed
Write-Host ""
Write-Host "📝 Files staged for commit:" -ForegroundColor Cyan
git status --short

Write-Host ""
$commitMessage = Read-Host "Enter commit message (or press Enter for default)"

if ([string]::IsNullOrWhiteSpace($commitMessage)) {
    $commitMessage = "Deploy stable version - Test Genius Extension"
}

Write-Host ""
Write-Host "💾 Committing changes..." -ForegroundColor Cyan
git commit -m $commitMessage

Write-Host ""
$remoteUrl = Read-Host "Enter GitHub repository URL (or press Enter if already set): https://github.com/AhmedRashad15/Azure-TestCases-Generator"

# Check if remote exists
$remoteExists = git remote | Select-String -Pattern "origin"

if (-not $remoteExists) {
    if ([string]::IsNullOrWhiteSpace($remoteUrl)) {
        $remoteUrl = "https://github.com/AhmedRashad15/Azure-TestCases-Generator.git"
    }
    Write-Host "🔗 Adding remote origin..." -ForegroundColor Cyan
    git remote add origin $remoteUrl
} else {
    Write-Host "✅ Remote origin already exists" -ForegroundColor Green
}

Write-Host ""
$branch = Read-Host "Enter branch name (or press Enter for 'main'):"

if ([string]::IsNullOrWhiteSpace($branch)) {
    $branch = "main"
}

# Check if branch exists, create if not
$branchExists = git branch --list $branch
if (-not $branchExists) {
    Write-Host "🌿 Creating branch: $branch" -ForegroundColor Cyan
    git checkout -b $branch
} else {
    Write-Host "✅ Branch $branch already exists" -ForegroundColor Green
    git checkout $branch
}

Write-Host ""
Write-Host "🚀 Pushing to GitHub..." -ForegroundColor Cyan
Write-Host "⚠️  This will push to: origin/$branch" -ForegroundColor Yellow

$confirm = Read-Host "Continue? (Y/N)"

if ($confirm -eq "Y" -or $confirm -eq "y") {
    git push -u origin $branch
    
    Write-Host ""
    Write-Host "✅ Deployment complete!" -ForegroundColor Green
    Write-Host "📦 Repository: https://github.com/AhmedRashad15/Azure-TestCases-Generator" -ForegroundColor Cyan
} else {
    Write-Host "❌ Deployment cancelled" -ForegroundColor Red
}

