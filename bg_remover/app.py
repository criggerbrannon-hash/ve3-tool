#!/usr/bin/env python3
"""
Background Remover Pro - Server
================================
AI-powered background removal with 4K upscaling
"""

import os
import io
import uuid
import base64
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from PIL import Image
import numpy as np

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# App config
app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = 'bg-remover-pro-secret-2024'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max

CORS(app, origins="*")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Directories
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
TEMP_DIR = BASE_DIR / "temp"

for d in [UPLOAD_DIR, OUTPUT_DIR, TEMP_DIR]:
    d.mkdir(exist_ok=True)

# Global state
processing_status = {}


class ImageProcessor:
    """AI-powered image processing engine."""

    def __init__(self):
        self.rembg_session = None
        self.upscaler = None
        self._init_models()

    def _init_models(self):
        """Initialize AI models (lazy loading)."""
        pass

    def _get_rembg_session(self):
        """Get or create rembg session."""
        if self.rembg_session is None:
            try:
                from rembg import new_session
                self.rembg_session = new_session("u2net")
                logger.info("Loaded rembg model: u2net")
            except Exception as e:
                logger.error(f"Failed to load rembg: {e}")
                raise
        return self.rembg_session

    def remove_background(self, image: Image.Image,
                          alpha_matting: bool = False,
                          alpha_matting_foreground_threshold: int = 240,
                          alpha_matting_background_threshold: int = 10) -> Image.Image:
        """
        Remove background from image using AI.

        Args:
            image: PIL Image
            alpha_matting: Enable alpha matting for better edges

        Returns:
            Image with transparent background
        """
        try:
            from rembg import remove

            # Convert to bytes
            img_bytes = io.BytesIO()
            image.save(img_bytes, format='PNG')
            img_bytes.seek(0)

            # Remove background
            result_bytes = remove(
                img_bytes.read(),
                session=self._get_rembg_session(),
                alpha_matting=alpha_matting,
                alpha_matting_foreground_threshold=alpha_matting_foreground_threshold,
                alpha_matting_background_threshold=alpha_matting_background_threshold
            )

            # Convert back to PIL
            result = Image.open(io.BytesIO(result_bytes))
            return result

        except ImportError:
            logger.warning("rembg not installed, using fallback")
            return self._fallback_remove_bg(image)
        except Exception as e:
            logger.error(f"Background removal error: {e}")
            raise

    def _fallback_remove_bg(self, image: Image.Image) -> Image.Image:
        """Fallback background removal using simple thresholding."""
        # Convert to RGBA
        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        # Simple approach: make white/near-white pixels transparent
        data = np.array(image)

        # Calculate brightness
        r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]

        # Detect near-white pixels (simple background detection)
        threshold = 240
        is_white = (r > threshold) & (g > threshold) & (b > threshold)

        # Make those pixels transparent
        data[:,:,3] = np.where(is_white, 0, 255)

        return Image.fromarray(data, 'RGBA')

    def upscale_image(self, image: Image.Image, scale: int = 4) -> Image.Image:
        """
        Upscale image to higher resolution using AI.

        Args:
            image: PIL Image
            scale: Upscale factor (2x or 4x)

        Returns:
            Upscaled image
        """
        try:
            # Try Real-ESRGAN first
            return self._upscale_realesrgan(image, scale)
        except ImportError:
            logger.warning("Real-ESRGAN not available, using Lanczos")
            return self._upscale_lanczos(image, scale)
        except Exception as e:
            logger.warning(f"AI upscale failed: {e}, using Lanczos")
            return self._upscale_lanczos(image, scale)

    def _upscale_realesrgan(self, image: Image.Image, scale: int) -> Image.Image:
        """Upscale using Real-ESRGAN AI model."""
        from basicsr.archs.rrdbnet_arch import RRDBNet
        from realesrgan import RealESRGANer
        import cv2
        import torch

        # Convert PIL to numpy
        img_np = np.array(image)

        # Handle RGBA
        has_alpha = image.mode == 'RGBA'
        if has_alpha:
            alpha = img_np[:, :, 3]
            img_np = img_np[:, :, :3]

        # Convert RGB to BGR for OpenCV
        img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

        # Setup model
        model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64,
                       num_block=23, num_grow_ch=32, scale=scale)

        # Initialize upscaler
        upsampler = RealESRGANer(
            scale=scale,
            model_path=None,  # Will use default
            model=model,
            tile=400,
            tile_pad=10,
            pre_pad=0,
            half=torch.cuda.is_available()
        )

        # Upscale
        output, _ = upsampler.enhance(img_bgr, outscale=scale)

        # Convert back to RGB
        output_rgb = cv2.cvtColor(output, cv2.COLOR_BGR2RGB)

        # Handle alpha channel
        if has_alpha:
            # Upscale alpha separately using Lanczos
            alpha_pil = Image.fromarray(alpha)
            new_size = (output_rgb.shape[1], output_rgb.shape[0])
            alpha_upscaled = np.array(alpha_pil.resize(new_size, Image.Resampling.LANCZOS))

            # Combine
            output_rgba = np.dstack((output_rgb, alpha_upscaled))
            return Image.fromarray(output_rgba, 'RGBA')

        return Image.fromarray(output_rgb, 'RGB')

    def _upscale_lanczos(self, image: Image.Image, scale: int) -> Image.Image:
        """High-quality Lanczos upscaling (fallback)."""
        new_width = image.width * scale
        new_height = image.height * scale

        # Cap at 4K resolution
        max_dim = 3840
        if new_width > max_dim or new_height > max_dim:
            ratio = min(max_dim / new_width, max_dim / new_height)
            new_width = int(new_width * ratio)
            new_height = int(new_height * ratio)

        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    def apply_background(self, image: Image.Image,
                         bg_color: Optional[str] = None,
                         bg_image: Optional[Image.Image] = None) -> Image.Image:
        """
        Apply new background to transparent image.

        Args:
            image: Image with transparency
            bg_color: Hex color code (e.g., '#ffffff')
            bg_image: Background image

        Returns:
            Image with new background
        """
        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        if bg_image:
            # Resize background to match image
            bg_image = bg_image.resize(image.size, Image.Resampling.LANCZOS)
            if bg_image.mode != 'RGBA':
                bg_image = bg_image.convert('RGBA')

            # Composite
            result = Image.alpha_composite(bg_image, image)

        elif bg_color:
            # Create solid color background
            bg_color = bg_color.lstrip('#')
            rgb = tuple(int(bg_color[i:i+2], 16) for i in (0, 2, 4))
            bg = Image.new('RGBA', image.size, (*rgb, 255))

            # Composite
            result = Image.alpha_composite(bg, image)
        else:
            result = image

        return result

    def auto_crop(self, image: Image.Image, padding: int = 10) -> Image.Image:
        """Auto crop to content with padding."""
        if image.mode != 'RGBA':
            return image

        # Get alpha channel
        alpha = np.array(image)[:, :, 3]

        # Find bounding box
        rows = np.any(alpha > 0, axis=1)
        cols = np.any(alpha > 0, axis=0)

        if not rows.any() or not cols.any():
            return image

        ymin, ymax = np.where(rows)[0][[0, -1]]
        xmin, xmax = np.where(cols)[0][[0, -1]]

        # Add padding
        ymin = max(0, ymin - padding)
        ymax = min(image.height, ymax + padding)
        xmin = max(0, xmin - padding)
        xmax = min(image.width, xmax + padding)

        return image.crop((xmin, ymin, xmax, ymax))


# Global processor
processor = ImageProcessor()


def emit_progress(task_id: str, progress: int, status: str, message: str = ""):
    """Emit progress update via WebSocket."""
    processing_status[task_id] = {
        'progress': progress,
        'status': status,
        'message': message
    }
    socketio.emit('progress', {
        'task_id': task_id,
        'progress': progress,
        'status': status,
        'message': message
    })


@app.route('/')
def index():
    """Serve main page."""
    return send_from_directory(BASE_DIR / 'static', 'index.html')


@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files."""
    return send_from_directory(BASE_DIR / 'static', filename)


@app.route('/api/process', methods=['POST'])
def process_image():
    """
    Process image: remove background and optionally upscale.

    Form data:
        - image: Image file
        - remove_bg: bool (default: true)
        - upscale: int (1, 2, 4)
        - bg_color: hex color (optional)
        - alpha_matting: bool (better edges)
        - auto_crop: bool
    """
    task_id = str(uuid.uuid4())[:8]

    try:
        # Get file
        if 'image' not in request.files:
            return jsonify({'error': 'No image provided'}), 400

        file = request.files['image']
        if not file.filename:
            return jsonify({'error': 'Empty filename'}), 400

        # Get options
        remove_bg = request.form.get('remove_bg', 'true').lower() == 'true'
        upscale = int(request.form.get('upscale', 1))
        bg_color = request.form.get('bg_color', None)
        alpha_matting = request.form.get('alpha_matting', 'false').lower() == 'true'
        auto_crop = request.form.get('auto_crop', 'false').lower() == 'true'

        emit_progress(task_id, 10, 'loading', 'Loading image...')

        # Load image
        image = Image.open(file.stream)
        original_mode = image.mode

        # Convert to RGB/RGBA
        if image.mode not in ('RGB', 'RGBA'):
            image = image.convert('RGB')

        emit_progress(task_id, 20, 'processing', 'Processing...')

        result = image

        # Step 1: Remove background
        if remove_bg:
            emit_progress(task_id, 30, 'removing_bg', 'Removing background with AI...')
            result = processor.remove_background(
                result,
                alpha_matting=alpha_matting
            )
            emit_progress(task_id, 50, 'bg_removed', 'Background removed!')

        # Step 2: Auto crop
        if auto_crop and result.mode == 'RGBA':
            emit_progress(task_id, 55, 'cropping', 'Auto cropping...')
            result = processor.auto_crop(result)

        # Step 3: Apply new background
        if bg_color and result.mode == 'RGBA':
            emit_progress(task_id, 60, 'applying_bg', 'Applying background...')
            result = processor.apply_background(result, bg_color=bg_color)

        # Step 4: Upscale
        if upscale > 1:
            emit_progress(task_id, 70, 'upscaling', f'Upscaling {upscale}x to 4K...')
            result = processor.upscale_image(result, scale=upscale)
            emit_progress(task_id, 90, 'upscaled', 'Upscaling complete!')

        emit_progress(task_id, 95, 'encoding', 'Encoding result...')

        # Save result
        output_buffer = io.BytesIO()

        # Determine format
        if result.mode == 'RGBA':
            result.save(output_buffer, format='PNG', optimize=True)
            mime_type = 'image/png'
        else:
            result.save(output_buffer, format='JPEG', quality=95)
            mime_type = 'image/jpeg'

        output_buffer.seek(0)

        # Encode to base64
        img_base64 = base64.b64encode(output_buffer.read()).decode('utf-8')

        emit_progress(task_id, 100, 'complete', 'Done!')

        return jsonify({
            'success': True,
            'task_id': task_id,
            'image': f'data:{mime_type};base64,{img_base64}',
            'width': result.width,
            'height': result.height,
            'has_transparency': result.mode == 'RGBA'
        })

    except Exception as e:
        logger.exception("Processing error")
        emit_progress(task_id, 0, 'error', str(e))
        return jsonify({'error': str(e)}), 500


@app.route('/api/batch', methods=['POST'])
def batch_process():
    """Process multiple images."""
    task_id = str(uuid.uuid4())[:8]
    results = []

    try:
        files = request.files.getlist('images')
        if not files:
            return jsonify({'error': 'No images provided'}), 400

        total = len(files)
        remove_bg = request.form.get('remove_bg', 'true').lower() == 'true'
        upscale = int(request.form.get('upscale', 1))

        for i, file in enumerate(files):
            try:
                progress = int((i / total) * 100)
                emit_progress(task_id, progress, 'processing', f'Processing {i+1}/{total}...')

                image = Image.open(file.stream)
                if image.mode not in ('RGB', 'RGBA'):
                    image = image.convert('RGB')

                result = image

                if remove_bg:
                    result = processor.remove_background(result)

                if upscale > 1:
                    result = processor.upscale_image(result, scale=upscale)

                # Encode
                output_buffer = io.BytesIO()
                if result.mode == 'RGBA':
                    result.save(output_buffer, format='PNG')
                    mime = 'image/png'
                else:
                    result.save(output_buffer, format='JPEG', quality=95)
                    mime = 'image/jpeg'

                output_buffer.seek(0)
                img_base64 = base64.b64encode(output_buffer.read()).decode('utf-8')

                results.append({
                    'filename': file.filename,
                    'success': True,
                    'image': f'data:{mime};base64,{img_base64}',
                    'width': result.width,
                    'height': result.height
                })

            except Exception as e:
                results.append({
                    'filename': file.filename,
                    'success': False,
                    'error': str(e)
                })

        emit_progress(task_id, 100, 'complete', f'Processed {total} images')

        return jsonify({
            'success': True,
            'task_id': task_id,
            'results': results,
            'total': total,
            'succeeded': sum(1 for r in results if r['success']),
            'failed': sum(1 for r in results if not r['success'])
        })

    except Exception as e:
        logger.exception("Batch processing error")
        return jsonify({'error': str(e)}), 500


@app.route('/api/download/<task_id>')
def download_result(task_id):
    """Download processed image."""
    output_path = OUTPUT_DIR / f"{task_id}.png"
    if output_path.exists():
        return send_file(output_path, mimetype='image/png', as_attachment=True,
                        download_name=f'bg_removed_{task_id}.png')
    return jsonify({'error': 'File not found'}), 404


@app.route('/api/status/<task_id>')
def get_status(task_id):
    """Get processing status."""
    status = processing_status.get(task_id, {
        'progress': 0,
        'status': 'unknown',
        'message': 'Task not found'
    })
    return jsonify(status)


@app.route('/api/health')
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'version': '1.0.0',
        'features': {
            'background_removal': True,
            'upscaling': True,
            'batch_processing': True
        }
    })


@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection."""
    logger.info(f"Client connected: {request.sid}")
    emit('connected', {'status': 'ok'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection."""
    logger.info(f"Client disconnected: {request.sid}")


def run_server(host='0.0.0.0', port=5000, debug=True):
    """Run the server."""
    logger.info(f"Starting Background Remover Pro on http://{host}:{port}")
    socketio.run(app, host=host, port=port, debug=debug, use_reloader=debug)


if __name__ == '__main__':
    run_server()
