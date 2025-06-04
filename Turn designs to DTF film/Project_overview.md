# DTF Film Smart Packer - Project Overview

## Purpose
This is an optimized image packing system designed for DTF (Direct-to-Film) printing workflows. It automatically arranges multiple design images onto a single canvas to maximize material utilization and minimize waste during printing.

## Core Functionality

### What It Does
- **Automatic Layout**: Takes multiple design images and intelligently arranges them on a canvas
- **Dimension Extraction**: Reads target print dimensions directly from filenames (e.g., "design_9cm_x_5cm.png")
- **Smart Placement**: Uses a scoring algorithm to find optimal positions considering:
  - Minimal gaps and waste
  - Proper spacing between designs
  - Edge contact optimization
  - Density-based gap filling

### Key Features

#### 🔄 **Rotation Support**
- Automatically tries 90-degree rotations to improve packing efficiency
- Compares placement scores for original vs rotated orientations

#### ⚡ **Performance Optimized**
- **Parallel Processing**: Uses all CPU cores for placement calculations
- **Mask-based Collision**: Fast overlap detection using binary masks
- **Iterative Canvas Sizing**: Starts with estimated height, grows as needed

#### 🎯 **Intelligent Placement Algorithm**
- **Scoring System**: Lower scores = better placements based on:
  - Position preference (top-left priority)
  - Contact with edges/other images
  - Gap-filling in dense areas
- **Spacing Control**: Configurable minimum distance between images
- **Step-based Search**: Configurable precision vs speed trade-off

#### 📤 **Multiple Output Formats**
1. **PDF**: Print-ready file with proper dimensions and margins
2. **PNG**: Visual preview at specified DPI
3. **Placements.txt**: Detailed coordinate data for each placed image
4. **Unplaced.txt**: List of images that couldn't fit

## Technical Architecture

### Input Processing
```
Input Directory → Image Loading → Dimension Extraction → Mask Creation
```
- Supports PNG, JPG, JPEG formats
- Creates binary masks for precise collision detection
- Filters out invalid/excluded files

### Packing Engine
```
Canvas Initialization → Parallel Placement Search → Score Evaluation → Best Position Selection
```
- Uses ProcessPoolExecutor for parallel processing
- Custom algorithm replaces traditional bin-packing approaches
- Iterative approach with fallback canvas resizing

### Output Generation
```
Placement Data → PDF Generation → PNG Rendering → Text Reports
```
- ReportLab for PDF creation
- PIL for high-quality PNG output
- Detailed logging and error handling

## Configuration Options

### Canvas & Sizing
- `CANVAS_WIDTH_CM`: Target canvas width (default: 60cm)
- `SPACING_MM`: Minimum spacing between images (default: 3mm)
- `PDF_MARGIN_CM`: PDF page margins (default: 0.5cm)

### Performance Tuning
- `NUM_PROCESSES`: CPU cores to use (default: all available)
- `PLACEMENT_STEP_MM`: Search precision (default: 5mm)
- `MAX_PLACEMENT_ATTEMPTS`: Retry limit before canvas resize

### Output Quality
- `PNG_OUTPUT_DPI`: PNG resolution (default: 150 DPI)
- `ALLOW_ROTATION`: Enable 90-degree rotation (default: True)

## File Naming Convention
Images must include dimensions in filename:
- `design_9cm_x_5cm.png`
- `logo_12.5cm_x_8.2cm.jpg`
- `pattern_main_9cm.png` (special case for square 9x9cm)

## Workflow Integration
1. **Preparation**: Place design files in input directory with proper naming
2. **Processing**: Run script - automatically handles loading, packing, output
3. **Review**: Check PNG preview and unplaced.txt for any issues
4. **Printing**: Use generated PDF for DTF printer

## Performance Characteristics
- **Parallel Processing**: Scales with CPU cores
- **Memory Efficient**: Uses shared memory for canvas masks
- **Fallback Handling**: Gracefully handles placement failures
- **Progress Tracking**: Real-time console feedback

## Error Handling
- Invalid image formats → Skipped with warnings
- Missing dimensions → Excluded from packing
- Placement failures → Logged in unplaced.txt
- Processing errors → Detailed error messages

This system is specifically optimized for DTF printing workflows where maximizing material usage while maintaining proper spacing is critical for cost-effective production.
