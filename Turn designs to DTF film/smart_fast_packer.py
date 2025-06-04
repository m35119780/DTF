# -*- coding: utf-8 -*-
"""
Optimized Image Packer: Combines smart placement (mask-based, scoring) 
with speed (parallel processing) and features (rotation, transparency handling).
Replaces rectpack with a custom packing algorithm inspired by fast_image_packer.py.
"""
import os
import re
import time
import math
import io
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import cProfile
import pstats

import cv2
import numpy as np
from PIL import Image, ImageOps
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.units import cm, mm
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import A4

# --- Configuration --- 
INPUT_DIR = r"C:\Users\Ali\Downloads\ORDERS TOD\New folder"  # Put your design images here
OUTPUT_DIR = r"C:\Users\Ali\Downloads\ORDERS TOD\New folder"  # Output files will be saved here
# New output filenames for the smart/fast packer
OUTPUT_PDF_FILENAME = "packed_smart_fast.pdf"
OUTPUT_PNG_FILENAME = "packed_smart_fast_visual.png"
OUTPUT_PLACEMENTS_FILENAME = "placements_smart_fast.txt"
OUTPUT_UNPLACED_FILENAME = "unplaced_smart_fast.txt"

CANVAS_WIDTH_CM = 60.0 # Target width for packing
SPACING_MM = 3 # Spacing between images in millimeters
PNG_OUTPUT_DPI = 150 # DPI for the rasterized PNG output
ALLOW_ROTATION = True # Allow 90-degree rotation
PDF_MARGIN_CM = 0.5 # Margin for PDF output
NUM_PROCESSES = multiprocessing.cpu_count() # Use all available CPU cores
INITIAL_HEIGHT_FACTOR = 1.5 # Initial estimate factor for canvas height
HEIGHT_INCREASE_STEP_MM = 50 # How much to increase height if needed (in mm)
MAX_PLACEMENT_ATTEMPTS = 10 # Max attempts to find a spot before increasing height

# Placement Algorithm Tuning
PLACEMENT_STEP_MM = 5 # Search step size in mm (smaller = slower but potentially denser)
SORT_IMAGES = True # Sort images before packing (e.g., by area descending)

# Files to exclude from processing
EXCLUDED_PATTERNS = [
    OUTPUT_PDF_FILENAME,
    OUTPUT_PNG_FILENAME,
    OUTPUT_PLACEMENTS_FILENAME,
    OUTPUT_UNPLACED_FILENAME,
    "packed_final_rotated", # Exclude previous run's output
    "packed_final_norotate",
]

# --- Helper Functions --- 

def extract_dimensions_cm(filename):
    """Extracts width and height in CM from filename."""
    pattern = r'([\d.]+)cm[_xX]+([\d.]+)cm'
    match = re.search(pattern, filename)
    if match:
        try:
            return float(match.group(1)), float(match.group(2))
        except ValueError:
            return None
    if "main 9cm" in filename:
        return 9.0, 9.0
    # Add handling for the new image.png if needed, or remove if temporary
    # if "image.png" in filename: 
    #     return 29.25, 29.25 # Example dimension
    return None

def should_exclude_file(filename):
    """Checks if a file should be excluded based on patterns or type."""
    base_filename = os.path.basename(filename)
    for pattern in EXCLUDED_PATTERNS:
        if pattern in base_filename:
            return True
    if not base_filename.lower().endswith(('.png', '.jpg', '.jpeg')):
        return True
    if extract_dimensions_cm(base_filename) is None:
        return True
    return False

def get_image_data(filepath, spacing_mm):
    """Loads image, extracts info, creates initial mask."""
    filename = os.path.basename(filepath)
    if should_exclude_file(filename):
        return None
    
    dimensions_cm = extract_dimensions_cm(filename)
    if not dimensions_cm:
        return None

    width_cm, height_cm = dimensions_cm
    if width_cm <= 0 or height_cm <= 0:
        return None

    try:
        img_orig = cv2.imread(filepath, cv2.IMREAD_UNCHANGED)
        if img_orig is None: raise ValueError("Cannot read image")

        # Create alpha mask (thresholded > 0)
        if len(img_orig.shape) == 2: # Grayscale
            mask = (img_orig > 0).astype(np.uint8) * 255
            img_bgra = cv2.cvtColor(img_orig, cv2.COLOR_GRAY2BGRA)
        elif img_orig.shape[2] == 3: # BGR
            mask = np.ones((img_orig.shape[0], img_orig.shape[1]), dtype=np.uint8) * 255
            img_bgra = cv2.cvtColor(img_orig, cv2.COLOR_BGR2BGRA)
            img_bgra[:, :, 3] = 255
        elif img_orig.shape[2] == 4: # BGRA
            mask = (img_orig[:, :, 3] > 0).astype(np.uint8) * 255
            img_bgra = img_orig
        else:
            raise ValueError(f"Unsupported image shape: {img_orig.shape}")

        # Calculate dimensions in mm (for placement logic)
        width_mm = int(width_cm * 10)
        height_mm = int(height_cm * 10)

        # Resize mask to match the dimensions used for placement (mm converted to int pixels)
        # Use INTER_NEAREST to preserve binary nature as much as possible
        target_mask_shape = (height_mm, width_mm) # Note: OpenCV uses (height, width)
        if mask.shape != target_mask_shape:
            print(f"Resizing mask for {filename} from {mask.shape} to {target_mask_shape}")
            mask = cv2.resize(mask, (width_mm, height_mm), interpolation=cv2.INTER_NEAREST)
        
        return {
            'path': filepath,
            'filename': filename,
            'img_bgra': img_bgra, # Original image (BGRA)
            'mask': mask,       # Original mask (binary, RESIZED to mm dimensions)
            'width_mm': width_mm, # Content width in mm
            'height_mm': height_mm, # Content height in mm
            'area_mm2': width_mm * height_mm,
            'id': filename # Unique ID
        }
    except Exception as e:
        print(f"Error processing image {filename}: {e}")
        return None

# --- Custom Packing Algorithm Functions --- 

def check_distance(canvas_mask, x_mm, y_mm, width_mm, height_mm, spacing_mm):
    """Checks if placing a rect at (x,y) maintains spacing using the canvas mask."""
    if spacing_mm <= 0:
        return True # No spacing check needed

    canvas_h, canvas_w = canvas_mask.shape
    
    # Define the check region including spacing
    y_start = max(0, y_mm - spacing_mm)
    y_end = min(canvas_h, y_mm + height_mm + spacing_mm)
    x_start = max(0, x_mm - spacing_mm)
    x_end = min(canvas_w, x_mm + width_mm + spacing_mm)

    # Extract the region from the canvas mask
    check_region = canvas_mask[y_start:y_end, x_start:x_end]

    # Create a mask for the *inner* area (the image itself) within the check region
    inner_mask = np.zeros_like(check_region, dtype=bool)
    inner_y_start_rel = y_mm - y_start
    inner_y_end_rel = inner_y_start_rel + height_mm
    inner_x_start_rel = x_mm - x_start
    inner_x_end_rel = inner_x_start_rel + width_mm
    inner_mask[inner_y_start_rel:inner_y_end_rel, inner_x_start_rel:inner_x_end_rel] = True

    # Check if any occupied pixel in the check_region falls *outside* the inner mask area
    # If yes, it means another image is too close (within the spacing)
    overlap = check_region[~inner_mask].any()
    
    return not overlap

def calculate_placement_score(x_mm, y_mm, width_mm, height_mm, canvas_mask, spacing_mm):
    """Calculates a score for a potential placement (lower is better)."""
    canvas_h, canvas_w = canvas_mask.shape
    
    # 1. Positional Score: Prefer top-left
    # Heavier penalty for increasing height (y)
    score = y_mm * 1.5 + x_mm * 1.0

    # 2. Contact Score: Reward contact with canvas edges or other images
    contact_pixels = 0
    perimeter = 2 * (width_mm + height_mm) + 1 # Avoid division by zero

    # Check adjacent areas (within spacing) for occupied pixels
    s = spacing_mm # shorthand
    # Top
    if y_mm > 0:
        top_region = canvas_mask[max(0, y_mm - s):y_mm, x_mm:min(canvas_w, x_mm + width_mm)]
        contact_pixels += np.sum(top_region)
    else: # Contact with top edge
        contact_pixels += width_mm 
    # Bottom (less critical as canvas grows, but check anyway)
    if y_mm + height_mm < canvas_h:
        bottom_region = canvas_mask[y_mm + height_mm:min(canvas_h, y_mm + height_mm + s), x_mm:min(canvas_w, x_mm + width_mm)]
        contact_pixels += np.sum(bottom_region)
    # Left
    if x_mm > 0:
        left_region = canvas_mask[y_mm:min(canvas_h, y_mm + height_mm), max(0, x_mm - s):x_mm]
        contact_pixels += np.sum(left_region)
    else: # Contact with left edge
        contact_pixels += height_mm
    # Right
    if x_mm + width_mm < canvas_w:
        right_region = canvas_mask[y_mm:min(canvas_h, y_mm + height_mm), x_mm + width_mm:min(canvas_w, x_mm + width_mm + s)]
        contact_pixels += np.sum(right_region)
    else: # Contact with right edge
        contact_pixels += height_mm
        
    # Normalize contact score and subtract from main score (higher contact = lower score)
    contact_bonus = (contact_pixels / perimeter) * 50 # Adjust weight as needed
    score -= contact_bonus

    # 3. Gap Filling Score (Simplified): Check density of surrounding area
    # Check a slightly larger bounding box
    margin = s + 1
    gap_y_start = max(0, y_mm - margin)
    gap_y_end = min(canvas_h, y_mm + height_mm + margin)
    gap_x_start = max(0, x_mm - margin)
    gap_x_end = min(canvas_w, x_mm + width_mm + margin)
    gap_region = canvas_mask[gap_y_start:gap_y_end, gap_x_start:gap_x_end]
    if gap_region.size > 0:
        occupied_ratio = np.sum(gap_region) / gap_region.size
        # Reward placing in denser areas (higher ratio = lower score)
        gap_bonus = occupied_ratio * 25 # Adjust weight
        score -= gap_bonus

    return score

def try_placement_for_image(args):
    """Worker function to find the best placement for a single image on the current canvas."""
    img_data, canvas_mask, canvas_h, canvas_w, spacing_mm, step_mm, allow_rotation = args # Renamed for direct use with threads
    
    best_placement = None
    best_score = float('inf')

    # Access the shared canvas mask (direct access with threads)
    # canvas_mask = np.frombuffer(canvas_mask_shared.get_obj(), dtype=np.uint8).reshape((canvas_h, canvas_w)) # Removed for threading

    options = [(img_data['width_mm'], img_data['height_mm'], img_data['mask'], False)] # Original orientation
    if allow_rotation and img_data['width_mm'] != img_data['height_mm']:
        # Add 90-degree rotated option
        rotated_mask = cv2.rotate(img_data['mask'], cv2.ROTATE_90_CLOCKWISE)
        options.append((img_data['height_mm'], img_data['width_mm'], rotated_mask, True))

    for width_mm, height_mm, mask_to_place, rotated in options:
        if width_mm > canvas_w or height_mm > canvas_h:
            continue # Skip if image is larger than canvas
            
        # Iterate through possible top-left positions (x, y) with step size
        for y in range(0, canvas_h - height_mm + 1, step_mm):
            for x in range(0, canvas_w - width_mm + 1, step_mm):
                
                # 1. Quick Overlap Check (using bounding box on canvas mask)
                roi = canvas_mask[y:y+height_mm, x:x+width_mm]
                if np.any(roi): # If any pixel in the target ROI is already occupied
                    # More precise check needed only if mask_to_place has transparency
                    # Check if the intersection of the mask and occupied ROI is non-zero
                    if np.any(np.logical_and(roi, mask_to_place)):
                         continue # Definite overlap, skip this position

                # 2. Spacing Check
                if not check_distance(canvas_mask, x, y, width_mm, height_mm, spacing_mm):
                    continue # Too close to another image

                # 3. Calculate Score
                score = calculate_placement_score(x, y, width_mm, height_mm, canvas_mask, spacing_mm)
                
                # Add slight penalty for rotation to prefer original orientation if scores are close
                if rotated:
                    score += 0.1 

                # 4. Update Best Placement if score is better
                if score < best_score:
                    best_score = score
                    best_placement = {
                        'id': img_data['id'],
                        'path': img_data['path'],
                        'x_mm': x,
                        'y_mm': y,
                        'width_mm': width_mm, # Placed width (content only)
                        'height_mm': height_mm, # Placed height (content only)
                        'rotated': rotated,
                        'score': score
                    }
                    
    # Return the best placement found for this image (or None)
    return best_placement

# --- Main Execution --- 

def main():
    script_start_time = time.time()
    print(f"Starting Smart/Fast Packing (Rotation: {ALLOW_ROTATION}, Parallel: {NUM_PROCESSES} cores)...")
    print(f"Input directory: {INPUT_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # --- Step 1: Load and Prepare Image Data --- 
    print("\nStep 1: Loading and preparing image data...")
    load_start_time = time.time()
    all_files = [os.path.join(INPUT_DIR, f) for f in os.listdir(INPUT_DIR) if os.path.isfile(os.path.join(INPUT_DIR, f))]
    
    # Load image data sequentially first (parallel loading can be complex with cv2/PIL)
    image_data_list = []
    for f in all_files:
        data = get_image_data(f, SPACING_MM)
        if data:
            image_data_list.append(data)
            
    load_end_time = time.time()
    print(f"Found {len(image_data_list)} valid images to pack in {load_end_time - load_start_time:.2f} seconds.")

    if not image_data_list:
        print("Error: No valid images found for packing.")
        return

    # Sort images (optional, e.g., by area descending for potentially better packing)
    if SORT_IMAGES:
        image_data_list.sort(key=lambda x: x['area_mm2'], reverse=True)
        print("Images sorted by area (descending).")

    # --- Step 2: Iterative Packing using Custom Algorithm --- 
    print(f"\nStep 2: Packing images using custom algorithm...")
    pack_start_time = time.time()
    
    canvas_width_mm = int(CANVAS_WIDTH_CM * 10)
    pixels_per_mm_pdf = (72 / 25.4) # Standard PDF points per mm
    pixels_per_mm_png = (PNG_OUTPUT_DPI / 25.4) # Pixels per mm for PNG
    spacing_px_png = int(SPACING_MM * pixels_per_mm_png)

    # Estimate initial canvas height (use mm for consistency)
    total_area_mm2 = sum(img['area_mm2'] for img in image_data_list)
    estimated_height_mm = int((total_area_mm2 / canvas_width_mm) * INITIAL_HEIGHT_FACTOR) 
    max_dim_mm = 0
    if image_data_list:
        max_w = max(img['width_mm'] for img in image_data_list)
        max_h = max(img['height_mm'] for img in image_data_list)
        max_dim_mm = max(max_w, max_h) # Accommodate rotation
    current_canvas_height_mm = max(estimated_height_mm, max_dim_mm + 2 * SPACING_MM) # Ensure tallest fits
    print(f"Initial canvas estimate: {canvas_width_mm}mm x {current_canvas_height_mm}mm")

    placements = []
    unplaced_images = list(image_data_list) # Start with all images as unplaced
    
    # Create the initial canvas mask (using mm as units)
    # Use a shared memory array for the mask for parallel access
    canvas_mask_shape = (current_canvas_height_mm, canvas_width_mm)
    shared_mask_arr = multiprocessing.Array('B', current_canvas_height_mm * canvas_width_mm, lock=False)
    canvas_mask = np.frombuffer(shared_mask_arr, dtype=np.uint8).reshape(canvas_mask_shape)
    canvas_mask.fill(0) # Initialize to empty

    placement_attempts = 0
    last_successful_placement_index = -1

    with ProcessPoolExecutor(max_workers=NUM_PROCESSES) as executor:
        while unplaced_images:
            print(f"Packing iteration: {len(unplaced_images)} images remaining. Canvas height: {current_canvas_height_mm}mm")
            made_placement_in_iteration = False
            
            # Prepare arguments for parallel processing for all remaining images
            args_list = [(img_data, canvas_mask, current_canvas_height_mm, canvas_width_mm, SPACING_MM, PLACEMENT_STEP_MM, ALLOW_ROTATION)
                         for img_data in unplaced_images]
            
            results = list(executor.map(try_placement_for_image, args_list))
            
            # Process results - find the best valid placement among all images
            best_result_for_iteration = None
            best_result_index = -1

            for i, result in enumerate(results):
                if result: # If a valid placement was found for this image
                    if best_result_for_iteration is None or result['score'] < best_result_for_iteration['score']:
                        best_result_for_iteration = result
                        best_result_index = i


            # --- Decision Point: Place the best image or handle failure ---
            if best_result_for_iteration:
                # Get the actual image data corresponding to the best result index
                placed_img_data = unplaced_images.pop(best_result_index) # Remove from unplaced
                placement = best_result_for_iteration
                placements.append(placement) # Add to successful placements

                print(f"  Placed: {placement['id']} at ({placement['x_mm']}, {placement['y_mm']}) Score: {placement['score']:.2f} Rotated: {placement['rotated']}")

                # Update the master canvas mask
                x, y = placement['x_mm'], placement['y_mm']
                w, h = placement['width_mm'], placement['height_mm']
                mask_to_apply = placed_img_data['mask']
                if placement['rotated']:
                    # Ensure mask is rotated *before* applying
                    mask_to_apply = cv2.rotate(placed_img_data['mask'], cv2.ROTATE_90_CLOCKWISE)
                
                # Verify mask dimensions match placement dimensions
                mask_h, mask_w = mask_to_apply.shape
                if mask_h != h or mask_w != w:
                     print(f"Warning: Mask dimension mismatch for {placement['id']}. Expected ({h},{w}), got ({mask_h},{mask_w}). Resizing mask.")
                     # Resize using nearest neighbor to preserve binary nature if possible
                     mask_to_apply = cv2.resize(mask_to_apply, (w, h), interpolation=cv2.INTER_NEAREST) 

                # Apply the mask to the shared canvas_mask using logical OR
                try:
                    canvas_mask_roi = canvas_mask[y:y+h, x:x+w]
                    # Ensure shapes match exactly before logical_or
                    if canvas_mask_roi.shape == mask_to_apply.shape:
                        canvas_mask[y:y+h, x:x+w] = np.logical_or(canvas_mask_roi, mask_to_apply)
                    else:
                        print(f"Error: ROI shape {canvas_mask_roi.shape} does not match mask shape {mask_to_apply.shape} for {placement['id']}. Skipping mask update.")
                except ValueError as ve:
                     print(f"Error applying mask for {placement['id']} at ({x},{y}) size ({w},{h}) on canvas {canvas_mask.shape}: {ve}")
                     # This might indicate placement outside bounds, though try_placement should prevent this

                made_placement_in_iteration = True
                placement_attempts = 0 # Reset attempts after successful placement
                last_successful_placement_index = len(placements) - 1 

            else: # No valid placement found for *any* remaining image in this iteration
                placement_attempts += 1
                print(f"  No suitable placement found in this iteration. Attempt {placement_attempts}/{MAX_PLACEMENT_ATTEMPTS}.")
                if placement_attempts >= MAX_PLACEMENT_ATTEMPTS:
                    print(f"Warning: Could not place remaining {len(unplaced_images)} images after {MAX_PLACEMENT_ATTEMPTS} attempts with current canvas size. Stopping packing loop.")
                    break # Exit the while loop
        # --- End of while unplaced_images loop ---

    # --- Step 3: Generate Output Files ---
    print("\nStep 3: Generating output files...")
    output_gen_start_time = time.time()
    
    # Determine final canvas height based on placements
    final_canvas_height_mm = 0
    if placements:
        final_canvas_height_mm = max(p['y_mm'] + p['height_mm'] for p in placements)
        # Add some bottom margin/spacing
        final_canvas_height_mm += SPACING_MM
    else:
        final_canvas_height_mm = 10 # Minimal height if nothing placed
    
    print(f"Final packed dimensions: {canvas_width_mm}mm x {final_canvas_height_mm}mm")
    
    # --- PNG Output ---
    png_output_path = os.path.join(OUTPUT_DIR, OUTPUT_PNG_FILENAME)
    try:
        canvas_width_px = int(canvas_width_mm * pixels_per_mm_png)
        canvas_height_px = int(final_canvas_height_mm * pixels_per_mm_png)
        
        # Create RGBA canvas using PIL for easier alpha blending
        final_png_canvas = Image.new('RGBA', (canvas_width_px, canvas_height_px), (0, 0, 0, 0)) # Transparent background
    
        # Load original image data map for quick access
        image_data_map = {img['id']: img for img in image_data_list}
    
        print(f"Generating PNG ({canvas_width_px}x{canvas_height_px}px) at {PNG_OUTPUT_DPI} DPI...")
        for p in placements:
            img_data = image_data_map.get(p['id'])
            if not img_data:
                print(f"Warning: Image data not found for placed item {p['id']}")
                continue
    
            try:
                # Load image using PIL from BGRA numpy array (handle potential errors)
                img_bgra_orig = img_data['img_bgra']
                if img_bgra_orig is None:
                     print(f"Warning: BGRA data missing for {p['id']}")
                     continue
                     
                # Convert BGRA (OpenCV) to RGBA (PIL)
                img_rgba_pil = Image.fromarray(cv2.cvtColor(img_bgra_orig, cv2.COLOR_BGRA2RGBA))
    
                # Rotate if needed
                if p['rotated']:
                    img_rgba_pil = img_rgba_pil.rotate(90, expand=True)
    
                # Calculate target size in pixels for PNG
                target_width_px = int(p['width_mm'] * pixels_per_mm_png)
                target_height_px = int(p['height_mm'] * pixels_per_mm_png)
    
                # Resize (use LANCZOS for better quality)
                img_resized = img_rgba_pil.resize((target_width_px, target_height_px), Image.Resampling.LANCZOS)
    
                # Calculate position in pixels
                pos_x_px = int(p['x_mm'] * pixels_per_mm_png)
                pos_y_px = int(p['y_mm'] * pixels_per_mm_png)
    
                # Paste onto canvas using alpha mask
                final_png_canvas.paste(img_resized, (pos_x_px, pos_y_px), img_resized) # Use img_resized as mask for RGBA
    
            except Exception as e_inner:
                print(f"Error processing image {p['id']} for PNG: {e_inner}")
                # Optionally continue or break depending on desired robustness
    
        final_png_canvas.save(png_output_path)
        print(f"Saved PNG visual: {png_output_path}")
    
    except Exception as e_png:
        print(f"Error generating PNG output: {e_png}")
    
    
    # --- PDF Output ---
    pdf_output_path = os.path.join(OUTPUT_DIR, OUTPUT_PDF_FILENAME)
    try:
        # Calculate PDF page size including margins
        pdf_width_pt = (canvas_width_mm + 2 * PDF_MARGIN_CM * 10) * mm
        pdf_height_pt = (final_canvas_height_mm + 2 * PDF_MARGIN_CM * 10) * mm
        pdf_margin_pt = PDF_MARGIN_CM * cm

        c = rl_canvas.Canvas(pdf_output_path, pagesize=(pdf_width_pt, pdf_height_pt))
        print(f"Generating PDF ({pdf_width_pt/cm:.2f}cm x {pdf_height_pt/cm:.2f}cm)...")

        for p in placements:
            img_data = image_data_map.get(p['id'])
            if not img_data: continue # Already warned during PNG generation

            try:
                # Load image as PIL for consistent handling with PNG
                img_bgra_orig = img_data['img_bgra']
                if img_bgra_orig is None:
                    print(f"Warning: BGRA data missing for {p['id']}")
                    continue
                    
                # Convert BGRA (OpenCV) to RGBA (PIL) - same as PNG processing
                img_rgba_pil = Image.fromarray(cv2.cvtColor(img_bgra_orig, cv2.COLOR_BGRA2RGBA))

                # Apply rotation if needed - same as PNG processing
                if p['rotated']:
                    img_rgba_pil = img_rgba_pil.rotate(90, expand=True)

                # Calculate dimensions and position in points for PDF
                width_pt = p['width_mm'] * mm
                height_pt = p['height_mm'] * mm
                x_pt = p['x_mm'] * mm + pdf_margin_pt
                # PDF Y-coordinate is from bottom-left, adjust from top-left placement
                y_pt = pdf_height_pt - (p['y_mm'] * mm + pdf_margin_pt + height_pt) 

                # Convert PIL image to ImageReader for ReportLab
                img_buffer = io.BytesIO()
                img_rgba_pil.save(img_buffer, format='PNG')
                img_buffer.seek(0)
                img_reader = ImageReader(img_buffer)

                # Draw image on PDF canvas with proper dimensions
                c.drawImage(img_reader, x_pt, y_pt, width=width_pt, height=height_pt, mask='auto')

            except Exception as e_inner_pdf:
                print(f"Error processing image {p['id']} for PDF: {e_inner_pdf}")

        c.save()
        print(f"Saved PDF: {pdf_output_path}")

    except Exception as e_pdf:
        print(f"Error generating PDF output: {e_pdf}")
    
    
    # --- Placements File ---
    placements_output_path = os.path.join(OUTPUT_DIR, OUTPUT_PLACEMENTS_FILENAME)
    try:
        with open(placements_output_path, 'w', encoding='utf-8') as f:
            f.write("Filename; X (mm); Y (mm); Width (mm); Height (mm); Rotated\\n")
            for p in placements:
                f.write(f"{p['id']}; {p['x_mm']:.2f}; {p['y_mm']:.2f}; {p['width_mm']:.2f}; {p['height_mm']:.2f}; {p['rotated']}\\n")
        print(f"Saved placements: {placements_output_path}")
    except Exception as e_place:
        print(f"Error writing placements file: {e_place}")
    
    # --- Unplaced Files ---
    unplaced_output_path = os.path.join(OUTPUT_DIR, OUTPUT_UNPLACED_FILENAME)
    if unplaced_images:
        try:
            with open(unplaced_output_path, 'w', encoding='utf-8') as f:
                f.write("Unplaced Filenames:\\n")
                for img_data in unplaced_images:
                    f.write(f"{img_data['id']}\\n")
            print(f"Saved unplaced images list: {unplaced_output_path}")
        except Exception as e_unplace:
            print(f"Error writing unplaced images file: {e_unplace}")
    else:
        print("No unplaced images.")
    
    
    # --- Final Summary ---
    output_gen_end_time = time.time()
    script_end_time = time.time()
    print("\n--- Packing Summary ---")
    print(f"Total execution time: {script_end_time - script_start_time:.2f} seconds")
    print(f"  - Image loading: {load_end_time - load_start_time:.2f} seconds")
    print(f"  - Packing loop: {output_gen_start_time - pack_start_time:.2f} seconds") # Use output gen start as pack end
    print(f"  - Output generation: {output_gen_end_time - output_gen_start_time:.2f} seconds")
    print(f"Placed images: {len(placements)}")
    print(f"Unplaced images: {len(unplaced_images)}")
    print(f"Final canvas dimensions (mm): {canvas_width_mm} x {final_canvas_height_mm:.2f}")
    print(f"Output files generated in: {OUTPUT_DIR}")
    print(f"  - PDF: {OUTPUT_PDF_FILENAME}")
    print(f"  - PNG Visual: {OUTPUT_PNG_FILENAME}")
    print(f"  - Placements: {OUTPUT_PLACEMENTS_FILENAME}")
    if unplaced_images:
        print(f"  - Unplaced: {OUTPUT_UNPLACED_FILENAME}")
    
    # Add profiling output if enabled
    # profile.disable()
    # ps = pstats.Stats(profile).sort_stats('cumulative')
    # ps.print_stats(20) # Print top 20 cumulative time functions
    
if __name__ == "__main__":
    # Enable profiling if needed
    # profile = cProfile.Profile()
    # profile.enable()
    
    main()
    
    # Print profiling stats if enabled
    # profile.disable()
    # ps = pstats.Stats(profile).sort_stats('cumulative')
    # ps.print_stats(20) # Print top 20 cumulative time functions

