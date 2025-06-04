import os
import time
from celery import Celery, Task
import uuid
import cv2
import numpy as np
from PIL import Image
import zipfile
import io
import json
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
import config  # Import the centralized config module

# Set up Celery with Redis as the broker
celery = Celery('dtf_packer', broker=config.REDIS_URL, backend=config.REDIS_URL)

# Celery configuration
celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour timeout for tasks
    worker_prefetch_multiplier=1,  # Prevent worker from prefetching too many tasks
    task_acks_late=True,  # Only acknowledge tasks after they are complete
)

# Function to save task status
def update_task_status(task_id, status, progress=None, message=None, result=None):
    """Update the status of a task in Redis for progress tracking."""
    status_data = {
        'status': status,
        'progress': progress,
        'message': message,
        'result': result,
        'updated_at': time.time()
    }
    celery.backend.set(f'task_status:{task_id}', json.dumps(status_data))

class ProcessingTask(Task):
    """Base class for processing tasks with progress tracking."""
    
    def on_success(self, retval, task_id, args, kwargs):
        """Called when a task succeeds."""
        update_task_status(task_id, 'SUCCESS', 100, 'Task completed successfully', retval)
        return super().on_success(retval, task_id, args, kwargs)
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when a task fails."""
        update_task_status(task_id, 'FAILURE', None, str(exc))
        return super().on_failure(exc, task_id, args, kwargs, einfo)
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Called when a task is retried."""
        update_task_status(task_id, 'RETRY', None, f'Retrying: {str(exc)}')
        return super().on_retry(exc, task_id, args, kwargs, einfo)

@celery.task(bind=True, base=ProcessingTask)
def process_designs(self, upload_id, config, file_info_list):
    """
    Asynchronously process designs: load images, pack them, and generate outputs.
    
    Args:
        upload_id: The ID of the upload session
        config: Configuration dictionary with settings
        file_info_list: List of file info dictionaries with paths and dimensions
        
    Returns:
        Dictionary with result information
    """
    try:
        task_id = self.request.id
        upload_dir = os.path.join('uploads', upload_id)
        output_dir = os.path.join('outputs', upload_id)
        os.makedirs(output_dir, exist_ok=True)
        
        # 1. Update status - Started
        update_task_status(task_id, 'STARTED', 5, 'Processing started')
        
        # 2. Load and process images
        update_task_status(task_id, 'PROCESSING', 10, 'Loading images')
        
        image_data_list = []
        spacing_mm = float(config.get('spacing_mm', 3))
        
        for i, file_info_item in enumerate(file_info_list):
            filepath = file_info_item['filepath']
            custom_width = file_info_item['detected_width']
            
            if custom_width:
                # Process image dimensions and create image_data
                image_data = process_image(filepath, spacing_mm, custom_width)
                if image_data:
                    image_data_list.append(image_data)
            
            # Update progress for image loading phase (10% to 30%)
            progress = 10 + int((i / len(file_info_list)) * 20)
            update_task_status(task_id, 'PROCESSING', progress, f'Loading image {i+1}/{len(file_info_list)}')
        
        if not image_data_list:
            update_task_status(task_id, 'FAILURE', None, 'No valid images to process')
            return {'error': 'No valid images to process'}
        
        # 3. Pack images
        update_task_status(task_id, 'PROCESSING', 30, 'Running packing algorithm')
        
        canvas_width_mm = int(float(config.get('canvas_width_cm', 60)) * 10)
        pack_result = pack_images(image_data_list, canvas_width_mm, spacing_mm)
        
        # 4. Generate outputs
        update_task_status(task_id, 'PROCESSING', 50, 'Generating output files')
        
        output_formats = config.get('output_formats', {
            'generate_png': True,
            'generate_pdf': True,
            'generate_svg': True,
            'generate_report': True
        })
        
        outputs = {}
        
        # 4.1 Generate PNG if selected
        if output_formats.get('generate_png', True):
            update_task_status(task_id, 'PROCESSING', 60, 'Generating PNG file')
            png_path = generate_png_output(pack_result, config, output_dir)
            outputs['png'] = png_path
        
        # 4.2 Generate PDF if selected
        if output_formats.get('generate_pdf', True):
            update_task_status(task_id, 'PROCESSING', 70, 'Generating PDF file')
            pdf_path = generate_pdf_output(pack_result, config, output_dir)
            outputs['pdf'] = pdf_path
        
        # 4.3 Generate SVG if selected
        if output_formats.get('generate_svg', True):
            update_task_status(task_id, 'PROCESSING', 80, 'Generating SVG file')
            svg_path = generate_svg_output(pack_result, config, output_dir)
            outputs['svg'] = svg_path
        
        # 4.4 Generate report if selected
        if output_formats.get('generate_report', True):
            update_task_status(task_id, 'PROCESSING', 90, 'Generating report file')
            report_path = generate_report_output(pack_result, output_dir)
            outputs['report'] = report_path
        
        # 5. Create summary
        update_task_status(task_id, 'PROCESSING', 95, 'Creating summary')
        
        summary = {
            'total_images': len(image_data_list),
            'placed_images': len(pack_result['placements']),
            'unplaced_images': len(pack_result['unplaced_images']),
            'canvas_width_mm': pack_result['canvas_width_mm'],
            'canvas_height_mm': pack_result['final_canvas_height_mm'],
            'efficiency': 0
        }
        
        if pack_result['placements']:
            total_area = sum(p['width_mm'] * p['height_mm'] for p in pack_result['placements'])
            canvas_area = summary['canvas_width_mm'] * summary['canvas_height_mm']
            summary['efficiency'] = (total_area / canvas_area) * 100 if canvas_area > 0 else 0
        
        # Create session-safe version of pack_result (without numpy arrays)
        session_pack_result = {
            'placements': pack_result['placements'],
            'unplaced_images': [{'filename': img['filename'], 'width_mm': img['width_mm'], 'height_mm': img['height_mm']} 
                              for img in pack_result['unplaced_images']],
            'final_canvas_height_mm': pack_result['final_canvas_height_mm'],
            'canvas_width_mm': pack_result['canvas_width_mm']
        }
        
        # 6. Return result
        result = {
            'upload_id': upload_id,
            'pack_result': session_pack_result,
            'outputs': outputs,
            'summary': summary,
            'config': config
        }
        
        update_task_status(task_id, 'SUCCESS', 100, 'Processing completed successfully', result)
        return result
        
    except Exception as e:
        update_task_status(task_id, 'FAILURE', None, f'Processing failed: {str(e)}')
        return {'error': f'Processing failed: {str(e)}'}

# Helper functions for process_designs task
def process_image(filepath, spacing_mm, custom_width_cm):
    """Process an image and return image data for packing."""
    try:
        # Get width from custom input
        width_cm = float(custom_width_cm)
        
        # Load and process image
        img_orig = cv2.imread(filepath, cv2.IMREAD_UNCHANGED)
        if img_orig is None:
            return None
        
        h, w = img_orig.shape[:2]
        
        # Calculate dimensions in mm
        width_mm = width_cm * 10.0
        height_mm = width_mm * (h / w)
        
        # Convert to integers for pixel operations
        width_mm_int = int(round(width_mm))
        height_mm_int = int(round(height_mm))
        
        # Create mask and convert image to BGRA format
        if len(img_orig.shape) == 2:  # Grayscale
            mask = (img_orig > 0).astype(np.uint8) * 255
            img_bgra = cv2.cvtColor(img_orig, cv2.COLOR_GRAY2BGRA)
        elif img_orig.shape[2] == 3:  # BGR
            mask = np.ones((img_orig.shape[0], img_orig.shape[1]), dtype=np.uint8) * 255
            img_bgra = cv2.cvtColor(img_orig, cv2.COLOR_BGR2BGRA)
            img_bgra[:, :, 3] = 255
        elif img_orig.shape[2] == 4:  # BGRA
            mask = (img_orig[:, :, 3] > 0).astype(np.uint8) * 255
            img_bgra = img_orig
        else:
            return None
        
        # Resize mask to match placement dimensions
        mask = cv2.resize(mask, (width_mm_int, height_mm_int), interpolation=cv2.INTER_NEAREST)
        
        return {
            'path': filepath,
            'filename': os.path.basename(filepath),
            'img_bgra': img_bgra,
            'mask': mask,
            'width_mm': width_mm_int,
            'height_mm': height_mm_int,
            'area_mm2': width_mm_int * height_mm_int,
            'id': os.path.basename(filepath),
            'width_cm': width_cm,
            'height_cm': height_mm / 10.0
        }
        
    except Exception:
        return None

def pack_images(image_data_list, canvas_width_mm, spacing_mm):
    """Pack images on the canvas."""
    # You would import your actual packing algorithm here
    # For example: from smart_fast_packer import simple_pack_images
    
    # Basic rectangular packing (placeholder - replace with your actual algorithm)
    placements = []
    x, y = 0, 0
    max_height_in_row = 0
    
    for img in image_data_list:
        w, h = img['width_mm'], img['height_mm']
        
        # Try both orientations if width > height
        rotated = False
        if w > h and w > canvas_width_mm / 2:
            w, h = h, w
            rotated = True
        
        # Check if we need to move to next row
        if x + w > canvas_width_mm:
            x = 0
            y += max_height_in_row + spacing_mm
            max_height_in_row = 0
        
        placements.append({
            'id': img['id'],
            'path': img['path'],
            'x_mm': x,
            'y_mm': y,
            'width_mm': w,
            'height_mm': h,
            'rotated': rotated
        })
        
        # Update position and max height
        x += w + spacing_mm
        max_height_in_row = max(max_height_in_row, h)
    
    # Calculate final canvas height
    final_height = y + max_height_in_row + spacing_mm if placements else spacing_mm
    
    return {
        'placements': placements,
        'unplaced_images': [],
        'final_canvas_height_mm': final_height,
        'canvas_width_mm': canvas_width_mm,
        'image_data_map': {img['id']: img for img in image_data_list}
    }

def generate_png_output(pack_result, config, output_dir):
    """Generate PNG output file."""
    placements = pack_result['placements']
    canvas_width_mm = pack_result['canvas_width_mm']
    final_canvas_height_mm = pack_result['final_canvas_height_mm']
    image_data_map = pack_result['image_data_map']
    
    pixels_per_mm_png = (config['png_dpi'] / 25.4)
    
    canvas_width_px = int(canvas_width_mm * pixels_per_mm_png)
    canvas_height_px = int(final_canvas_height_mm * pixels_per_mm_png)
    
    final_png_canvas = Image.new('RGBA', (canvas_width_px, canvas_height_px), (0, 0, 0, 0))

    for p in placements:
        img_data = image_data_map.get(p['id'])
        if not img_data:
            continue

        try:
            img_bgra_orig = img_data['img_bgra']
            if img_bgra_orig is None:
                continue
                
            img_rgba_pil = Image.fromarray(cv2.cvtColor(img_bgra_orig, cv2.COLOR_BGRA2RGBA))

            if p['rotated']:
                img_rgba_pil = img_rgba_pil.rotate(90, expand=True)

            target_width_px = int(p['width_mm'] * pixels_per_mm_png)
            target_height_px = int(p['height_mm'] * pixels_per_mm_png)

            img_resized = img_rgba_pil.resize((target_width_px, target_height_px), Image.Resampling.LANCZOS)

            pos_x_px = int(p['x_mm'] * pixels_per_mm_png)
            pos_y_px = int(p['y_mm'] * pixels_per_mm_png)

            final_png_canvas.paste(img_resized, (pos_x_px, pos_y_px), img_resized)

        except Exception:
            continue

    png_path = os.path.join(output_dir, 'packed_output.png')
    final_png_canvas.save(png_path)
    return png_path

def generate_pdf_output(pack_result, config, output_dir):
    """Generate PDF output file."""
    placements = pack_result['placements']
    canvas_width_mm = pack_result['canvas_width_mm']
    final_canvas_height_mm = pack_result['final_canvas_height_mm']
    image_data_map = pack_result['image_data_map']
    
    pdf_margin_cm = config.get('pdf_margin_cm', 1.0)
    pdf_width_pt = (canvas_width_mm + 2 * pdf_margin_cm * 10) * mm
    pdf_height_pt = (final_canvas_height_mm + 2 * pdf_margin_cm * 10) * mm
    pdf_margin_pt = pdf_margin_cm * mm

    pdf_path = os.path.join(output_dir, 'packed_output.pdf')
    c = rl_canvas.Canvas(pdf_path, pagesize=(pdf_width_pt, pdf_height_pt))

    for p in placements:
        img_data = image_data_map.get(p['id'])
        if not img_data: 
            continue

        try:
            img_bgra_orig = img_data['img_bgra']
            if img_bgra_orig is None:
                continue
                
            img_rgba_pil = Image.fromarray(cv2.cvtColor(img_bgra_orig, cv2.COLOR_BGRA2RGBA))

            if p['rotated']:
                img_rgba_pil = img_rgba_pil.rotate(90, expand=True)

            width_pt = p['width_mm'] * mm
            height_pt = p['height_mm'] * mm
            x_pt = p['x_mm'] * mm + pdf_margin_pt
            y_pt = pdf_height_pt - (p['y_mm'] * mm + pdf_margin_pt + height_pt) 

            img_buffer = io.BytesIO()
            try:
                img_rgba_pil.save(img_buffer, format='PNG', optimize=False)
                img_buffer.seek(0)
                img_reader = ImageReader(img_buffer)

                c.drawImage(img_reader, x_pt, y_pt, width=width_pt, height=height_pt, mask='auto')
            finally:
                img_buffer.close()

        except Exception:
            continue

    c.save()
    return pdf_path

def generate_svg_output(pack_result, config, output_dir):
    """Generate SVG output file."""
    import base64
    placements = pack_result['placements']
    canvas_width_mm = pack_result['canvas_width_mm']
    final_canvas_height_mm = pack_result['final_canvas_height_mm']
    image_data_map = pack_result['image_data_map']
    
    svg_path = os.path.join(output_dir, 'packed_output.svg')
    
    # Convert mm to SVG units (1mm = 3.779528 SVG units)
    svg_scale = 3.779528
    svg_width = canvas_width_mm * svg_scale
    svg_height = final_canvas_height_mm * svg_scale
    
    svg_content = [
        f'<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"',
        f'     width="{svg_width:.2f}" height="{svg_height:.2f}"',
        f'     viewBox="0 0 {svg_width:.2f} {svg_height:.2f}">',
        f'  <!-- DTF Layout: {canvas_width_mm}mm x {final_canvas_height_mm}mm -->',
        f'  <!-- Generated by DTF Packer - {len(placements)} images placed -->',
        ''
    ]
    
    # Add each image as embedded base64
    for p in placements:
        img_data = image_data_map.get(p['id'])
        if not img_data:
            continue
            
        try:
            img_bgra_orig = img_data['img_bgra']
            if img_bgra_orig is None:
                continue
                
            img_rgba_pil = Image.fromarray(cv2.cvtColor(img_bgra_orig, cv2.COLOR_BGRA2RGBA))
            
            if p['rotated']:
                img_rgba_pil = img_rgba_pil.rotate(90, expand=True)
            
            # Convert to base64 for embedding
            img_buffer = io.BytesIO()
            img_rgba_pil.save(img_buffer, format='PNG', optimize=True)
            img_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
            img_buffer.close()
            
            # Calculate SVG positions and dimensions
            x_svg = p['x_mm'] * svg_scale
            y_svg = p['y_mm'] * svg_scale
            width_svg = p['width_mm'] * svg_scale
            height_svg = p['height_mm'] * svg_scale
            
            # Add image to SVG
            svg_content.extend([
                f'  <!-- {p["id"]} - {p["width_mm"]}x{p["height_mm"]}mm {"(rotated)" if p["rotated"] else ""} -->',
                f'  <image x="{x_svg:.2f}" y="{y_svg:.2f}" width="{width_svg:.2f}" height="{height_svg:.2f}"',
                f'         xlink:href="data:image/png;base64,{img_base64}"/>',
                ''
            ])
            
        except Exception:
            continue
    
    svg_content.append('</svg>')
    
    # Write SVG file
    with open(svg_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(svg_content))
        
    return svg_path

def generate_report_output(pack_result, output_dir):
    """Generate placement report file."""
    placements = pack_result['placements']
    report_path = os.path.join(output_dir, 'placements.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("Filename; X (mm); Y (mm); Width (mm); Height (mm); Rotated\n")
        for p in placements:
            f.write(f"{p['id']}; {p['x_mm']:.2f}; {p['y_mm']:.2f}; {p['width_mm']:.2f}; {p['height_mm']:.2f}; {p['rotated']}\n")
    return report_path

# Function to get task status
def get_task_status(task_id):
    """Get the current status of a task."""
    status_data = celery.backend.get(f'task_status:{task_id}')
    if status_data:
        try:
            return json.loads(status_data)
        except:
            pass
    return None 