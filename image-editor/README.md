# VE3 Image Editor

A powerful web-based image editor with Photoshop-like features.

## Features

### Drawing Tools
- **Brush Tool** - Customizable brush with size, hardness, opacity, and flow
- **Pencil Tool** - Pixel-perfect drawing
- **Eraser Tool** - Remove pixels with adjustable settings
- **Paint Bucket** - Flood fill with tolerance control
- **Gradient Tool** - Linear and radial gradients
- **Clone Stamp** - Clone parts of the image
- **Blur/Sharpen Tools** - Local blur and sharpen
- **Smudge Tool** - Smudge and blend colors

### Selection Tools
- **Rectangle Select** - Rectangular selections
- **Ellipse Select** - Elliptical selections
- **Lasso Tool** - Freeform selections
- **Magic Wand** - Select by color with tolerance
- **Feathering** - Soft selection edges

### Shape Tools
- Rectangle, Ellipse, and Line shapes
- Fill and stroke options

### Text Tool
- Multiple fonts
- Size, bold, italic, underline options

### Layer System
- Multiple layers
- Layer visibility and locking
- Blend modes (Normal, Multiply, Screen, Overlay, etc.)
- Layer opacity
- Merge, duplicate, and delete layers

### Image Adjustments
- Brightness/Contrast
- Hue/Saturation/Lightness
- Levels
- Curves
- Exposure
- Vibrance
- Color Balance
- Shadows/Highlights
- Auto Levels/Contrast/Color

### Filters
- Blur (Gaussian, Box, Motion, Radial)
- Sharpen
- Noise
- Grayscale
- Sepia
- Invert
- Pixelate
- Vignette
- Oil Paint effect
- Edge Detection
- Emboss

### Other Features
- Undo/Redo with history panel
- Crop tool
- Image rotation and flip
- Zoom and pan
- Navigator panel
- Color picker with HSV/RGB input
- Color swatches
- Keyboard shortcuts
- Export to PNG, JPEG, WebP

## Keyboard Shortcuts

### File
- `Ctrl+N` - New document
- `Ctrl+O` - Open image
- `Ctrl+S` - Save/Export
- `Ctrl+E` - Export

### Edit
- `Ctrl+Z` - Undo
- `Ctrl+Y` - Redo
- `Ctrl+A` - Select all
- `Ctrl+D` - Deselect
- `Delete` - Delete selection

### Tools
- `V` - Move tool
- `M` - Selection tool
- `L` - Lasso tool
- `W` - Magic wand
- `C` - Crop tool
- `I` - Eyedropper
- `B` - Brush
- `N` - Pencil
- `E` - Eraser
- `G` - Paint bucket
- `T` - Text tool
- `H` - Hand tool
- `Z` - Zoom tool

### View
- `Ctrl++` - Zoom in
- `Ctrl+-` - Zoom out
- `Ctrl+0` - Fit to screen
- `Ctrl+1` - 100% zoom

### Colors
- `X` - Swap foreground/background colors
- `D` - Reset colors to black/white

### Brush
- `[` / `]` - Decrease/Increase brush size

## How to Run

### Option 1: Python Server
```bash
cd image-editor
python server.py
```

### Option 2: Any HTTP Server
```bash
# Using Python 3
python -m http.server 8080

# Using Node.js
npx serve

# Using PHP
php -S localhost:8080
```

Then open `http://localhost:8080` in your browser.

## Browser Support

- Chrome (recommended)
- Firefox
- Safari
- Edge

## License

MIT License
