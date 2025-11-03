"""
Simple script to create a 128x128 icon for Test Genius extension
Requires: pip install Pillow
"""
try:
    from PIL import Image, ImageDraw, ImageFont
    
    # Create 128x128 image with Azure blue background
    img = Image.new('RGB', (128, 128), color='#0078D7')
    draw = ImageDraw.Draw(img)
    
    # Try to use a nice font, fallback to default
    try:
        # Try common Windows fonts
        font_paths = [
            'C:/Windows/Fonts/arial.ttf',
            'C:/Windows/Fonts/arialbd.ttf',
            'C:/Windows/Fonts/calibri.ttf',
        ]
        font = None
        for path in font_paths:
            try:
                font = ImageFont.truetype(path, 70)
                break
            except:
                continue
        if font is None:
            font = ImageFont.load_default()
    except:
        font = ImageFont.load_default()
    
    # Draw "TG" text in white, centered
    text = "TG"
    # Get text bounding box
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Center the text
    x = (128 - text_width) / 2 - bbox[0]
    y = (128 - text_height) / 2 - bbox[1]
    
    # Draw text with shadow for better visibility
    draw.text((x+2, y+2), text, fill='#000000', font=font)  # Shadow
    draw.text((x, y), text, fill='white', font=font)  # Main text
    
    # Save to extension/images folder
    import os
    icon_path = os.path.join('extension', 'images', 'icon.png')
    os.makedirs(os.path.dirname(icon_path), exist_ok=True)
    img.save(icon_path)
    
    print(f"✅ Icon created successfully at: {icon_path}")
    print(f"   Size: 128x128 pixels")
    print(f"   Format: PNG")
    print(f"   Ready to use!")
    
except ImportError:
    print("❌ Pillow library not installed.")
    print("   Install it with: pip install Pillow")
    print("   Then run this script again.")
except Exception as e:
    print(f"❌ Error creating icon: {e}")
    print("\nAlternative: Use Option 1-4 from ICON_GUIDE.md")

