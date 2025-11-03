#!/bin/bash
# Package extension script for Unix/Mac

echo "Building extension..."
npm run build

echo "Packaging extension..."
npm run package

echo "Extension packaged successfully!"
echo "Check the extension folder for the .vsix file"

