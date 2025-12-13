// VE3 Image Editor - Drawing Tools

class Tool {
    constructor(editor) {
        this.editor = editor;
        this.name = 'tool';
        this.icon = 'fa-mouse-pointer';
        this.cursor = 'default';
        this.isDrawing = false;
        this.startX = 0;
        this.startY = 0;
        this.lastX = 0;
        this.lastY = 0;
    }

    activate() {}
    deactivate() {}

    onMouseDown(x, y, e) {}
    onMouseMove(x, y, e) {}
    onMouseUp(x, y, e) {}

    onKeyDown(e) {}
    onKeyUp(e) {}

    getOptionsHTML() { return ''; }
    updateOptions() {}
}

// Move Tool
class MoveTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'move';
        this.icon = 'fa-arrows-alt';
        this.cursor = 'move';
        this.layerStartX = 0;
        this.layerStartY = 0;
    }

    onMouseDown(x, y, e) {
        this.isDrawing = true;
        this.startX = x;
        this.startY = y;
        const layer = this.editor.layerManager.getActiveLayer();
        this.layerStartX = layer.x;
        this.layerStartY = layer.y;
    }

    onMouseMove(x, y, e) {
        if (!this.isDrawing) return;

        const layer = this.editor.layerManager.getActiveLayer();
        layer.x = this.layerStartX + (x - this.startX);
        layer.y = this.layerStartY + (y - this.startY);
        this.editor.render();
    }

    onMouseUp(x, y, e) {
        if (this.isDrawing) {
            this.editor.saveState('Move Layer', 'transform');
        }
        this.isDrawing = false;
    }
}

// Brush Tool
class BrushTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'brush';
        this.icon = 'fa-paint-brush';
        this.cursor = 'crosshair';
        this.size = 10;
        this.hardness = 100;
        this.opacity = 100;
        this.flow = 100;
        this.spacing = 0.25;
    }

    activate() {
        this.editor.showToolOptions('brushOptions');
    }

    onMouseDown(x, y, e) {
        this.isDrawing = true;
        this.lastX = x;
        this.lastY = y;
        this.drawPoint(x, y);
    }

    onMouseMove(x, y, e) {
        if (!this.isDrawing) return;

        const dist = Utils.distance(this.lastX, this.lastY, x, y);
        const step = Math.max(1, this.size * this.spacing);

        if (dist >= step) {
            const steps = Math.ceil(dist / step);
            for (let i = 1; i <= steps; i++) {
                const t = i / steps;
                const px = Utils.lerp(this.lastX, x, t);
                const py = Utils.lerp(this.lastY, y, t);
                this.drawPoint(px, py);
            }
            this.lastX = x;
            this.lastY = y;
        }

        this.editor.render();
    }

    onMouseUp(x, y, e) {
        if (this.isDrawing) {
            this.editor.saveState('Brush', 'brush');
        }
        this.isDrawing = false;
    }

    drawPoint(x, y) {
        const layer = this.editor.layerManager.getActiveLayer();
        if (layer.locked) return;

        const ctx = layer.ctx;
        const color = this.editor.colorManager.foreground;
        const selection = this.editor.selection;

        // Check if point is within selection
        if (selection.hasSelection() && !selection.containsPoint(x, y)) {
            return;
        }

        ctx.save();

        // Set up brush
        const gradient = ctx.createRadialGradient(x, y, 0, x, y, this.size / 2);
        const alpha = (this.opacity / 100) * (this.flow / 100);
        const innerAlpha = alpha;
        const outerAlpha = alpha * (this.hardness / 100);

        gradient.addColorStop(0, `rgba(${color.r}, ${color.g}, ${color.b}, ${innerAlpha})`);
        gradient.addColorStop(1 - (this.hardness / 100), `rgba(${color.r}, ${color.g}, ${color.b}, ${innerAlpha})`);
        gradient.addColorStop(1, `rgba(${color.r}, ${color.g}, ${color.b}, ${outerAlpha})`);

        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(x, y, this.size / 2, 0, Math.PI * 2);
        ctx.fill();

        ctx.restore();
    }

    updateOptions() {
        this.size = parseInt(document.getElementById('brushSize').value);
        this.hardness = parseInt(document.getElementById('brushHardness').value);
        this.opacity = parseInt(document.getElementById('brushOpacity').value);
        this.flow = parseInt(document.getElementById('brushFlow').value);
    }
}

// Pencil Tool
class PencilTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'pencil';
        this.icon = 'fa-pencil-alt';
        this.cursor = 'crosshair';
        this.size = 1;
    }

    activate() {
        this.editor.showToolOptions('brushOptions');
    }

    onMouseDown(x, y, e) {
        this.isDrawing = true;
        this.lastX = Math.floor(x);
        this.lastY = Math.floor(y);
        this.drawPixel(this.lastX, this.lastY);
    }

    onMouseMove(x, y, e) {
        if (!this.isDrawing) return;

        const px = Math.floor(x);
        const py = Math.floor(y);

        // Draw line using Bresenham's algorithm
        const points = Utils.bresenhamLine(this.lastX, this.lastY, px, py);
        points.forEach(p => this.drawPixel(p.x, p.y));

        this.lastX = px;
        this.lastY = py;
        this.editor.render();
    }

    onMouseUp(x, y, e) {
        if (this.isDrawing) {
            this.editor.saveState('Pencil', 'pencil');
        }
        this.isDrawing = false;
    }

    drawPixel(x, y) {
        const layer = this.editor.layerManager.getActiveLayer();
        if (layer.locked) return;

        const selection = this.editor.selection;
        if (selection.hasSelection() && !selection.containsPoint(x, y)) {
            return;
        }

        const ctx = layer.ctx;
        const color = this.editor.colorManager.foreground;

        ctx.fillStyle = color.toRGBA();
        ctx.fillRect(x, y, this.size, this.size);
    }

    updateOptions() {
        this.size = parseInt(document.getElementById('brushSize').value);
    }
}

// Eraser Tool
class EraserTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'eraser';
        this.icon = 'fa-eraser';
        this.cursor = 'crosshair';
        this.size = 20;
        this.hardness = 100;
        this.opacity = 100;
    }

    activate() {
        this.editor.showToolOptions('eraserOptions');
    }

    onMouseDown(x, y, e) {
        this.isDrawing = true;
        this.lastX = x;
        this.lastY = y;
        this.erasePoint(x, y);
    }

    onMouseMove(x, y, e) {
        if (!this.isDrawing) return;

        const dist = Utils.distance(this.lastX, this.lastY, x, y);
        const step = Math.max(1, this.size * 0.25);

        if (dist >= step) {
            const steps = Math.ceil(dist / step);
            for (let i = 1; i <= steps; i++) {
                const t = i / steps;
                const px = Utils.lerp(this.lastX, x, t);
                const py = Utils.lerp(this.lastY, y, t);
                this.erasePoint(px, py);
            }
            this.lastX = x;
            this.lastY = y;
        }

        this.editor.render();
    }

    onMouseUp(x, y, e) {
        if (this.isDrawing) {
            this.editor.saveState('Eraser', 'eraser');
        }
        this.isDrawing = false;
    }

    erasePoint(x, y) {
        const layer = this.editor.layerManager.getActiveLayer();
        if (layer.locked) return;

        const selection = this.editor.selection;
        if (selection.hasSelection() && !selection.containsPoint(x, y)) {
            return;
        }

        const ctx = layer.ctx;
        ctx.save();
        ctx.globalCompositeOperation = 'destination-out';

        const gradient = ctx.createRadialGradient(x, y, 0, x, y, this.size / 2);
        const alpha = this.opacity / 100;

        gradient.addColorStop(0, `rgba(0, 0, 0, ${alpha})`);
        gradient.addColorStop(1 - (this.hardness / 100), `rgba(0, 0, 0, ${alpha})`);
        gradient.addColorStop(1, `rgba(0, 0, 0, ${alpha * (this.hardness / 100)})`);

        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(x, y, this.size / 2, 0, Math.PI * 2);
        ctx.fill();

        ctx.restore();
    }

    updateOptions() {
        this.size = parseInt(document.getElementById('eraserSize').value);
        this.hardness = parseInt(document.getElementById('eraserHardness').value);
        this.opacity = parseInt(document.getElementById('eraserOpacity').value);
    }
}

// Fill (Paint Bucket) Tool
class FillTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'fill';
        this.icon = 'fa-fill-drip';
        this.cursor = 'crosshair';
        this.tolerance = 32;
    }

    onMouseDown(x, y, e) {
        const layer = this.editor.layerManager.getActiveLayer();
        if (layer.locked) return;

        const imageData = layer.getImageData();
        const color = this.editor.colorManager.foreground;

        Utils.floodFill(imageData, x, y, {
            r: color.r,
            g: color.g,
            b: color.b,
            a: color.a
        }, this.tolerance);

        layer.putImageData(imageData);
        this.editor.saveState('Fill', 'fill');
        this.editor.render();
    }
}

// Gradient Tool
class GradientTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'gradient';
        this.icon = 'fa-palette';
        this.cursor = 'crosshair';
        this.type = 'linear'; // linear, radial
    }

    onMouseDown(x, y, e) {
        this.isDrawing = true;
        this.startX = x;
        this.startY = y;
    }

    onMouseMove(x, y, e) {
        if (!this.isDrawing) return;

        // Show preview on overlay
        this.editor.clearOverlay();
        const ctx = this.editor.overlayCtx;

        ctx.save();
        ctx.setLineDash([5, 5]);
        ctx.strokeStyle = '#000';
        ctx.beginPath();
        ctx.moveTo(this.startX, this.startY);
        ctx.lineTo(x, y);
        ctx.stroke();
        ctx.restore();
    }

    onMouseUp(x, y, e) {
        if (!this.isDrawing) return;
        this.isDrawing = false;

        this.editor.clearOverlay();

        const layer = this.editor.layerManager.getActiveLayer();
        if (layer.locked) return;

        const ctx = layer.ctx;
        const fg = this.editor.colorManager.foreground;
        const bg = this.editor.colorManager.background;

        let gradient;
        if (this.type === 'radial') {
            const dist = Utils.distance(this.startX, this.startY, x, y);
            gradient = ctx.createRadialGradient(this.startX, this.startY, 0, this.startX, this.startY, dist);
        } else {
            gradient = ctx.createLinearGradient(this.startX, this.startY, x, y);
        }

        gradient.addColorStop(0, fg.toRGBA());
        gradient.addColorStop(1, bg.toRGBA());

        ctx.fillStyle = gradient;

        if (this.editor.selection.hasSelection()) {
            // Fill only selection
            const mask = this.editor.selection.mask;
            const imageData = ctx.getImageData(0, 0, layer.width, layer.height);
            const tempCanvas = Utils.createCanvas(layer.width, layer.height);
            const tempCtx = tempCanvas.getContext('2d');
            tempCtx.fillStyle = gradient;
            tempCtx.fillRect(0, 0, layer.width, layer.height);
            const gradientData = tempCtx.getImageData(0, 0, layer.width, layer.height);

            for (let i = 0; i < mask.length; i++) {
                if (mask[i] > 0) {
                    const alpha = mask[i] / 255;
                    const idx = i * 4;
                    imageData.data[idx] = Utils.lerp(imageData.data[idx], gradientData.data[idx], alpha);
                    imageData.data[idx + 1] = Utils.lerp(imageData.data[idx + 1], gradientData.data[idx + 1], alpha);
                    imageData.data[idx + 2] = Utils.lerp(imageData.data[idx + 2], gradientData.data[idx + 2], alpha);
                    imageData.data[idx + 3] = Utils.lerp(imageData.data[idx + 3], gradientData.data[idx + 3], alpha);
                }
            }
            ctx.putImageData(imageData, 0, 0);
        } else {
            ctx.fillRect(0, 0, layer.width, layer.height);
        }

        this.editor.saveState('Gradient', 'gradient');
        this.editor.render();
    }
}

// Rectangle Select Tool
class RectSelectTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'select-rect';
        this.icon = 'fa-vector-square';
        this.cursor = 'crosshair';
    }

    activate() {
        this.editor.showToolOptions('selectionOptions');
    }

    onMouseDown(x, y, e) {
        this.isDrawing = true;
        this.startX = x;
        this.startY = y;
    }

    onMouseMove(x, y, e) {
        if (!this.isDrawing) return;

        this.editor.clearOverlay();
        const ctx = this.editor.overlayCtx;

        const rx = Math.min(this.startX, x);
        const ry = Math.min(this.startY, y);
        const rw = Math.abs(x - this.startX);
        const rh = Math.abs(y - this.startY);

        ctx.save();
        ctx.setLineDash([5, 5]);
        ctx.strokeStyle = '#000';
        ctx.strokeRect(rx, ry, rw, rh);
        ctx.strokeStyle = '#fff';
        ctx.lineDashOffset = 5;
        ctx.strokeRect(rx, ry, rw, rh);
        ctx.restore();
    }

    onMouseUp(x, y, e) {
        if (!this.isDrawing) return;
        this.isDrawing = false;

        this.editor.clearOverlay();

        const width = x - this.startX;
        const height = y - this.startY;

        if (Math.abs(width) > 2 && Math.abs(height) > 2) {
            this.editor.selection.setFeather(this.editor.selectionFeather);
            this.editor.selection.createRect(this.startX, this.startY, width, height);
        } else {
            this.editor.selection.deselect();
        }

        this.editor.render();
    }
}

// Ellipse Select Tool
class EllipseSelectTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'select-ellipse';
        this.icon = 'fa-circle';
        this.cursor = 'crosshair';
    }

    activate() {
        this.editor.showToolOptions('selectionOptions');
    }

    onMouseDown(x, y, e) {
        this.isDrawing = true;
        this.startX = x;
        this.startY = y;
    }

    onMouseMove(x, y, e) {
        if (!this.isDrawing) return;

        this.editor.clearOverlay();
        const ctx = this.editor.overlayCtx;

        const cx = (this.startX + x) / 2;
        const cy = (this.startY + y) / 2;
        const rx = Math.abs(x - this.startX) / 2;
        const ry = Math.abs(y - this.startY) / 2;

        ctx.save();
        ctx.setLineDash([5, 5]);
        ctx.strokeStyle = '#000';
        ctx.beginPath();
        ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
        ctx.stroke();
        ctx.strokeStyle = '#fff';
        ctx.lineDashOffset = 5;
        ctx.beginPath();
        ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
    }

    onMouseUp(x, y, e) {
        if (!this.isDrawing) return;
        this.isDrawing = false;

        this.editor.clearOverlay();

        const cx = (this.startX + x) / 2;
        const cy = (this.startY + y) / 2;
        const rx = Math.abs(x - this.startX) / 2;
        const ry = Math.abs(y - this.startY) / 2;

        if (rx > 2 && ry > 2) {
            this.editor.selection.setFeather(this.editor.selectionFeather);
            this.editor.selection.createEllipse(cx, cy, rx, ry);
        } else {
            this.editor.selection.deselect();
        }

        this.editor.render();
    }
}

// Lasso Tool
class LassoTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'lasso';
        this.icon = 'fa-draw-polygon';
        this.cursor = 'crosshair';
        this.points = [];
    }

    activate() {
        this.editor.showToolOptions('selectionOptions');
    }

    onMouseDown(x, y, e) {
        this.isDrawing = true;
        this.points = [{ x, y }];
    }

    onMouseMove(x, y, e) {
        if (!this.isDrawing) return;

        this.points.push({ x, y });

        this.editor.clearOverlay();
        const ctx = this.editor.overlayCtx;

        ctx.save();
        ctx.setLineDash([5, 5]);
        ctx.strokeStyle = '#000';
        ctx.beginPath();
        this.points.forEach((p, i) => {
            if (i === 0) ctx.moveTo(p.x, p.y);
            else ctx.lineTo(p.x, p.y);
        });
        ctx.stroke();
        ctx.restore();
    }

    onMouseUp(x, y, e) {
        if (!this.isDrawing) return;
        this.isDrawing = false;

        this.editor.clearOverlay();

        if (this.points.length > 3) {
            this.editor.selection.setFeather(this.editor.selectionFeather);
            this.editor.selection.createLasso(this.points);
        } else {
            this.editor.selection.deselect();
        }

        this.points = [];
        this.editor.render();
    }
}

// Magic Wand Tool
class MagicWandTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'magic-wand';
        this.icon = 'fa-magic';
        this.cursor = 'crosshair';
        this.tolerance = 32;
        this.contiguous = true;
    }

    activate() {
        this.editor.showToolOptions('wandOptions');
    }

    onMouseDown(x, y, e) {
        const layer = this.editor.layerManager.getActiveLayer();
        const imageData = layer.getImageData();

        this.editor.selection.setFeather(this.editor.selectionFeather);
        this.editor.selection.createMagicWand(imageData, x, y, this.tolerance, this.contiguous);
        this.editor.render();
    }

    updateOptions() {
        this.tolerance = parseInt(document.getElementById('wandTolerance').value);
        this.contiguous = document.getElementById('wandContiguous').checked;
    }
}

// Crop Tool
class CropTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'crop';
        this.icon = 'fa-crop';
        this.cursor = 'crosshair';
        this.cropRect = null;
    }

    onMouseDown(x, y, e) {
        this.isDrawing = true;
        this.startX = x;
        this.startY = y;
    }

    onMouseMove(x, y, e) {
        if (!this.isDrawing) return;

        this.editor.clearOverlay();
        const ctx = this.editor.overlayCtx;

        const rx = Math.min(this.startX, x);
        const ry = Math.min(this.startY, y);
        const rw = Math.abs(x - this.startX);
        const rh = Math.abs(y - this.startY);

        this.cropRect = { x: rx, y: ry, width: rw, height: rh };

        // Darken outside area
        ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';
        ctx.fillRect(0, 0, this.editor.width, ry);
        ctx.fillRect(0, ry + rh, this.editor.width, this.editor.height - ry - rh);
        ctx.fillRect(0, ry, rx, rh);
        ctx.fillRect(rx + rw, ry, this.editor.width - rx - rw, rh);

        // Draw crop border
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.strokeRect(rx, ry, rw, rh);

        // Draw grid
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.5)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(rx + rw / 3, ry);
        ctx.lineTo(rx + rw / 3, ry + rh);
        ctx.moveTo(rx + 2 * rw / 3, ry);
        ctx.lineTo(rx + 2 * rw / 3, ry + rh);
        ctx.moveTo(rx, ry + rh / 3);
        ctx.lineTo(rx + rw, ry + rh / 3);
        ctx.moveTo(rx, ry + 2 * rh / 3);
        ctx.lineTo(rx + rw, ry + 2 * rh / 3);
        ctx.stroke();
    }

    onMouseUp(x, y, e) {
        if (!this.isDrawing) return;
        this.isDrawing = false;

        if (this.cropRect && this.cropRect.width > 10 && this.cropRect.height > 10) {
            if (confirm('Apply crop?')) {
                this.applyCrop();
            }
        }

        this.editor.clearOverlay();
        this.cropRect = null;
    }

    applyCrop() {
        if (!this.cropRect) return;

        const { x, y, width, height } = this.cropRect;

        // Create new layer manager with cropped size
        const newLayers = [];
        this.editor.layerManager.layers.forEach(layer => {
            const newLayer = new Layer(width, height, layer.name);
            newLayer.visible = layer.visible;
            newLayer.locked = layer.locked;
            newLayer.opacity = layer.opacity;
            newLayer.blendMode = layer.blendMode;
            newLayer.ctx.drawImage(layer.canvas, -x, -y);
            newLayers.push(newLayer);
        });

        this.editor.layerManager.width = width;
        this.editor.layerManager.height = height;
        this.editor.layerManager.layers = newLayers;

        this.editor.resize(width, height);
        this.editor.saveState('Crop', 'crop');
        this.editor.render();
    }
}

// Eyedropper Tool
class EyedropperTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'eyedropper';
        this.icon = 'fa-eye-dropper';
        this.cursor = 'crosshair';
    }

    onMouseDown(x, y, e) {
        this.pickColor(x, y, e);
    }

    onMouseMove(x, y, e) {
        if (e.buttons === 1) {
            this.pickColor(x, y, e);
        }
    }

    pickColor(x, y, e) {
        const layer = this.editor.layerManager.getActiveLayer();
        const imageData = layer.ctx.getImageData(Math.floor(x), Math.floor(y), 1, 1);
        const [r, g, b, a] = imageData.data;

        const color = new Color(r, g, b, a);

        if (e.altKey) {
            this.editor.colorManager.setBackground(color);
        } else {
            this.editor.colorManager.setForeground(color);
        }
    }
}

// Text Tool
class TextTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'text';
        this.icon = 'fa-font';
        this.cursor = 'text';
        this.fontFamily = 'Arial';
        this.fontSize = 24;
        this.bold = false;
        this.italic = false;
        this.underline = false;
        this.textInput = null;
    }

    activate() {
        this.editor.showToolOptions('textOptions');
    }

    deactivate() {
        this.commitText();
    }

    onMouseDown(x, y, e) {
        this.commitText();
        this.createTextInput(x, y);
    }

    createTextInput(x, y) {
        this.textInput = document.createElement('div');
        this.textInput.className = 'text-input-overlay';
        this.textInput.contentEditable = true;
        this.textInput.style.left = x + 'px';
        this.textInput.style.top = y + 'px';
        this.textInput.style.fontFamily = this.fontFamily;
        this.textInput.style.fontSize = this.fontSize + 'px';
        this.textInput.style.fontWeight = this.bold ? 'bold' : 'normal';
        this.textInput.style.fontStyle = this.italic ? 'italic' : 'normal';
        this.textInput.style.textDecoration = this.underline ? 'underline' : 'none';
        this.textInput.style.color = this.editor.colorManager.foreground.toRGBA();

        this.textInput.textX = x;
        this.textInput.textY = y;

        this.editor.canvasWrapper.appendChild(this.textInput);
        this.textInput.focus();
    }

    commitText() {
        if (!this.textInput || !this.textInput.innerText.trim()) {
            if (this.textInput) {
                this.textInput.remove();
                this.textInput = null;
            }
            return;
        }

        const layer = this.editor.layerManager.getActiveLayer();
        const ctx = layer.ctx;
        const color = this.editor.colorManager.foreground;

        let fontStyle = '';
        if (this.italic) fontStyle += 'italic ';
        if (this.bold) fontStyle += 'bold ';

        ctx.font = `${fontStyle}${this.fontSize}px ${this.fontFamily}`;
        ctx.fillStyle = color.toRGBA();
        ctx.textBaseline = 'top';

        const lines = this.textInput.innerText.split('\n');
        let y = this.textInput.textY;

        lines.forEach(line => {
            ctx.fillText(line, this.textInput.textX, y);
            if (this.underline) {
                const metrics = ctx.measureText(line);
                ctx.beginPath();
                ctx.moveTo(this.textInput.textX, y + this.fontSize);
                ctx.lineTo(this.textInput.textX + metrics.width, y + this.fontSize);
                ctx.strokeStyle = color.toRGBA();
                ctx.stroke();
            }
            y += this.fontSize * 1.2;
        });

        this.textInput.remove();
        this.textInput = null;

        this.editor.saveState('Text', 'text');
        this.editor.render();
    }

    updateOptions() {
        this.fontFamily = document.getElementById('fontFamily').value;
        this.fontSize = parseInt(document.getElementById('fontSize').value);

        if (this.textInput) {
            this.textInput.style.fontFamily = this.fontFamily;
            this.textInput.style.fontSize = this.fontSize + 'px';
            this.textInput.style.fontWeight = this.bold ? 'bold' : 'normal';
            this.textInput.style.fontStyle = this.italic ? 'italic' : 'normal';
            this.textInput.style.textDecoration = this.underline ? 'underline' : 'none';
        }
    }
}

// Shape Tools
class ShapeRectTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'shape-rect';
        this.icon = 'fa-square';
        this.cursor = 'crosshair';
        this.fill = true;
        this.stroke = false;
        this.strokeWidth = 2;
    }

    activate() {
        this.editor.showToolOptions('shapeOptions');
    }

    onMouseDown(x, y, e) {
        this.isDrawing = true;
        this.startX = x;
        this.startY = y;
    }

    onMouseMove(x, y, e) {
        if (!this.isDrawing) return;

        this.editor.clearOverlay();
        const ctx = this.editor.overlayCtx;
        this.drawShape(ctx, x, y);
    }

    onMouseUp(x, y, e) {
        if (!this.isDrawing) return;
        this.isDrawing = false;

        this.editor.clearOverlay();

        const layer = this.editor.layerManager.getActiveLayer();
        if (!layer.locked) {
            this.drawShape(layer.ctx, x, y);
            this.editor.saveState('Rectangle', 'shape');
            this.editor.render();
        }
    }

    drawShape(ctx, x, y) {
        const rx = Math.min(this.startX, x);
        const ry = Math.min(this.startY, y);
        const rw = Math.abs(x - this.startX);
        const rh = Math.abs(y - this.startY);

        if (this.fill) {
            ctx.fillStyle = this.editor.colorManager.foreground.toRGBA();
            ctx.fillRect(rx, ry, rw, rh);
        }
        if (this.stroke) {
            ctx.strokeStyle = this.editor.colorManager.foreground.toRGBA();
            ctx.lineWidth = this.strokeWidth;
            ctx.strokeRect(rx, ry, rw, rh);
        }
    }

    updateOptions() {
        this.fill = document.getElementById('shapeFill').checked;
        this.stroke = document.getElementById('shapeStroke').checked;
        this.strokeWidth = parseInt(document.getElementById('shapeStrokeWidth').value);
    }
}

class ShapeEllipseTool extends ShapeRectTool {
    constructor(editor) {
        super(editor);
        this.name = 'shape-ellipse';
        this.icon = 'fa-circle';
    }

    drawShape(ctx, x, y) {
        const cx = (this.startX + x) / 2;
        const cy = (this.startY + y) / 2;
        const rx = Math.abs(x - this.startX) / 2;
        const ry = Math.abs(y - this.startY) / 2;

        ctx.beginPath();
        ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);

        if (this.fill) {
            ctx.fillStyle = this.editor.colorManager.foreground.toRGBA();
            ctx.fill();
        }
        if (this.stroke) {
            ctx.strokeStyle = this.editor.colorManager.foreground.toRGBA();
            ctx.lineWidth = this.strokeWidth;
            ctx.stroke();
        }
    }
}

class ShapeLineTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'shape-line';
        this.icon = 'fa-minus';
        this.cursor = 'crosshair';
        this.strokeWidth = 2;
    }

    activate() {
        this.editor.showToolOptions('shapeOptions');
    }

    onMouseDown(x, y, e) {
        this.isDrawing = true;
        this.startX = x;
        this.startY = y;
    }

    onMouseMove(x, y, e) {
        if (!this.isDrawing) return;

        this.editor.clearOverlay();
        const ctx = this.editor.overlayCtx;
        this.drawLine(ctx, x, y);
    }

    onMouseUp(x, y, e) {
        if (!this.isDrawing) return;
        this.isDrawing = false;

        this.editor.clearOverlay();

        const layer = this.editor.layerManager.getActiveLayer();
        if (!layer.locked) {
            this.drawLine(layer.ctx, x, y);
            this.editor.saveState('Line', 'shape');
            this.editor.render();
        }
    }

    drawLine(ctx, x, y) {
        ctx.strokeStyle = this.editor.colorManager.foreground.toRGBA();
        ctx.lineWidth = this.strokeWidth;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(this.startX, this.startY);
        ctx.lineTo(x, y);
        ctx.stroke();
    }

    updateOptions() {
        this.strokeWidth = parseInt(document.getElementById('shapeStrokeWidth').value);
    }
}

// Hand Tool
class HandTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'hand';
        this.icon = 'fa-hand-paper';
        this.cursor = 'grab';
        this.scrollStartX = 0;
        this.scrollStartY = 0;
    }

    onMouseDown(x, y, e) {
        this.isDrawing = true;
        this.cursor = 'grabbing';
        this.startX = e.clientX;
        this.startY = e.clientY;
        this.scrollStartX = this.editor.canvasContainer.scrollLeft;
        this.scrollStartY = this.editor.canvasContainer.scrollTop;
    }

    onMouseMove(x, y, e) {
        if (!this.isDrawing) return;

        const dx = e.clientX - this.startX;
        const dy = e.clientY - this.startY;

        this.editor.canvasContainer.scrollLeft = this.scrollStartX - dx;
        this.editor.canvasContainer.scrollTop = this.scrollStartY - dy;
    }

    onMouseUp(x, y, e) {
        this.isDrawing = false;
        this.cursor = 'grab';
    }
}

// Zoom Tool
class ZoomTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'zoom';
        this.icon = 'fa-search';
        this.cursor = 'zoom-in';
    }

    onMouseDown(x, y, e) {
        if (e.altKey) {
            this.editor.zoomOut(x, y);
            this.cursor = 'zoom-out';
        } else {
            this.editor.zoomIn(x, y);
            this.cursor = 'zoom-in';
        }
    }

    onKeyDown(e) {
        if (e.altKey) {
            this.cursor = 'zoom-out';
        }
    }

    onKeyUp(e) {
        if (!e.altKey) {
            this.cursor = 'zoom-in';
        }
    }
}

// Clone Stamp Tool
class CloneStampTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'clone';
        this.icon = 'fa-stamp';
        this.cursor = 'crosshair';
        this.size = 20;
        this.sourceX = null;
        this.sourceY = null;
        this.offsetX = 0;
        this.offsetY = 0;
    }

    activate() {
        this.editor.showToolOptions('brushOptions');
    }

    onMouseDown(x, y, e) {
        if (e.altKey) {
            // Set source point
            this.sourceX = x;
            this.sourceY = y;
            this.offsetX = 0;
            this.offsetY = 0;
            return;
        }

        if (this.sourceX === null) {
            alert('Alt+Click to set source point first');
            return;
        }

        this.isDrawing = true;
        this.offsetX = x - this.sourceX;
        this.offsetY = y - this.sourceY;
        this.lastX = x;
        this.lastY = y;
        this.clonePoint(x, y);
    }

    onMouseMove(x, y, e) {
        if (!this.isDrawing) return;

        const dist = Utils.distance(this.lastX, this.lastY, x, y);
        const step = Math.max(1, this.size * 0.25);

        if (dist >= step) {
            const steps = Math.ceil(dist / step);
            for (let i = 1; i <= steps; i++) {
                const t = i / steps;
                const px = Utils.lerp(this.lastX, x, t);
                const py = Utils.lerp(this.lastY, y, t);
                this.clonePoint(px, py);
            }
            this.lastX = x;
            this.lastY = y;
        }

        this.editor.render();
    }

    onMouseUp(x, y, e) {
        if (this.isDrawing) {
            this.editor.saveState('Clone Stamp', 'clone');
        }
        this.isDrawing = false;
    }

    clonePoint(x, y) {
        const layer = this.editor.layerManager.getActiveLayer();
        if (layer.locked) return;

        const sourceX = x - this.offsetX;
        const sourceY = y - this.offsetY;

        const ctx = layer.ctx;
        const size = this.size;
        const halfSize = size / 2;

        // Get source image data
        const sourceData = ctx.getImageData(
            sourceX - halfSize, sourceY - halfSize,
            size, size
        );

        // Draw at destination with circular mask
        const tempCanvas = Utils.createCanvas(size, size);
        const tempCtx = tempCanvas.getContext('2d');
        tempCtx.putImageData(sourceData, 0, 0);

        ctx.save();
        ctx.beginPath();
        ctx.arc(x, y, halfSize, 0, Math.PI * 2);
        ctx.clip();
        ctx.drawImage(tempCanvas, x - halfSize, y - halfSize);
        ctx.restore();
    }

    updateOptions() {
        this.size = parseInt(document.getElementById('brushSize').value);
    }
}

// Blur Tool
class BlurTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'blur-tool';
        this.icon = 'fa-water';
        this.cursor = 'crosshair';
        this.size = 20;
        this.strength = 50;
    }

    activate() {
        this.editor.showToolOptions('brushOptions');
    }

    onMouseDown(x, y, e) {
        this.isDrawing = true;
        this.lastX = x;
        this.lastY = y;
        this.applyBlur(x, y);
    }

    onMouseMove(x, y, e) {
        if (!this.isDrawing) return;

        const dist = Utils.distance(this.lastX, this.lastY, x, y);
        if (dist >= 5) {
            this.applyBlur(x, y);
            this.lastX = x;
            this.lastY = y;
        }

        this.editor.render();
    }

    onMouseUp(x, y, e) {
        if (this.isDrawing) {
            this.editor.saveState('Blur Tool', 'blur');
        }
        this.isDrawing = false;
    }

    applyBlur(x, y) {
        const layer = this.editor.layerManager.getActiveLayer();
        if (layer.locked) return;

        const ctx = layer.ctx;
        const size = this.size;
        const halfSize = size / 2;

        const imageData = ctx.getImageData(x - halfSize, y - halfSize, size, size);
        const radius = Math.ceil(this.strength / 20);
        Utils.gaussianBlur(imageData, radius);

        // Apply with circular mask
        const tempCanvas = Utils.createCanvas(size, size);
        const tempCtx = tempCanvas.getContext('2d');
        tempCtx.putImageData(imageData, 0, 0);

        ctx.save();
        ctx.beginPath();
        ctx.arc(x, y, halfSize, 0, Math.PI * 2);
        ctx.clip();
        ctx.drawImage(tempCanvas, x - halfSize, y - halfSize);
        ctx.restore();
    }

    updateOptions() {
        this.size = parseInt(document.getElementById('brushSize').value);
        this.strength = parseInt(document.getElementById('brushOpacity').value);
    }
}

// Sharpen Tool
class SharpenTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'sharpen-tool';
        this.icon = 'fa-bolt';
        this.cursor = 'crosshair';
        this.size = 20;
        this.strength = 50;
    }

    activate() {
        this.editor.showToolOptions('brushOptions');
    }

    onMouseDown(x, y, e) {
        this.isDrawing = true;
        this.lastX = x;
        this.lastY = y;
        this.applySharpen(x, y);
    }

    onMouseMove(x, y, e) {
        if (!this.isDrawing) return;

        const dist = Utils.distance(this.lastX, this.lastY, x, y);
        if (dist >= 5) {
            this.applySharpen(x, y);
            this.lastX = x;
            this.lastY = y;
        }

        this.editor.render();
    }

    onMouseUp(x, y, e) {
        if (this.isDrawing) {
            this.editor.saveState('Sharpen Tool', 'sharpen');
        }
        this.isDrawing = false;
    }

    applySharpen(x, y) {
        const layer = this.editor.layerManager.getActiveLayer();
        if (layer.locked) return;

        const ctx = layer.ctx;
        const size = this.size;
        const halfSize = size / 2;

        const imageData = ctx.getImageData(x - halfSize, y - halfSize, size, size);
        const strength = this.strength / 100;

        // Sharpen kernel
        const kernel = [
            0, -strength, 0,
            -strength, 1 + 4 * strength, -strength,
            0, -strength, 0
        ];

        Utils.convolve(imageData, kernel);

        // Apply with circular mask
        const tempCanvas = Utils.createCanvas(size, size);
        const tempCtx = tempCanvas.getContext('2d');
        tempCtx.putImageData(imageData, 0, 0);

        ctx.save();
        ctx.beginPath();
        ctx.arc(x, y, halfSize, 0, Math.PI * 2);
        ctx.clip();
        ctx.drawImage(tempCanvas, x - halfSize, y - halfSize);
        ctx.restore();
    }

    updateOptions() {
        this.size = parseInt(document.getElementById('brushSize').value);
        this.strength = parseInt(document.getElementById('brushOpacity').value);
    }
}

// Smudge Tool
class SmudgeTool extends Tool {
    constructor(editor) {
        super(editor);
        this.name = 'smudge';
        this.icon = 'fa-hand-pointer';
        this.cursor = 'crosshair';
        this.size = 20;
        this.strength = 50;
        this.pickedColor = null;
    }

    activate() {
        this.editor.showToolOptions('brushOptions');
    }

    onMouseDown(x, y, e) {
        this.isDrawing = true;
        this.lastX = x;
        this.lastY = y;

        // Pick color at start point
        const layer = this.editor.layerManager.getActiveLayer();
        const imageData = layer.ctx.getImageData(Math.floor(x), Math.floor(y), 1, 1);
        this.pickedColor = new Color(imageData.data[0], imageData.data[1], imageData.data[2], imageData.data[3]);
    }

    onMouseMove(x, y, e) {
        if (!this.isDrawing || !this.pickedColor) return;

        const layer = this.editor.layerManager.getActiveLayer();
        if (layer.locked) return;

        const ctx = layer.ctx;
        const strength = this.strength / 100;

        // Draw smudge stroke
        ctx.save();
        ctx.globalAlpha = strength;
        ctx.fillStyle = this.pickedColor.toRGBA();
        ctx.beginPath();
        ctx.arc(x, y, this.size / 2, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();

        // Pick new color at current point for blending
        const newImageData = ctx.getImageData(Math.floor(x), Math.floor(y), 1, 1);
        this.pickedColor = this.pickedColor.blend(
            new Color(newImageData.data[0], newImageData.data[1], newImageData.data[2], newImageData.data[3]),
            0.5
        );

        this.lastX = x;
        this.lastY = y;
        this.editor.render();
    }

    onMouseUp(x, y, e) {
        if (this.isDrawing) {
            this.editor.saveState('Smudge', 'brush');
        }
        this.isDrawing = false;
        this.pickedColor = null;
    }

    updateOptions() {
        this.size = parseInt(document.getElementById('brushSize').value);
        this.strength = parseInt(document.getElementById('brushOpacity').value);
    }
}

// Export all tools
window.Tool = Tool;
window.MoveTool = MoveTool;
window.BrushTool = BrushTool;
window.PencilTool = PencilTool;
window.EraserTool = EraserTool;
window.FillTool = FillTool;
window.GradientTool = GradientTool;
window.RectSelectTool = RectSelectTool;
window.EllipseSelectTool = EllipseSelectTool;
window.LassoTool = LassoTool;
window.MagicWandTool = MagicWandTool;
window.CropTool = CropTool;
window.EyedropperTool = EyedropperTool;
window.TextTool = TextTool;
window.ShapeRectTool = ShapeRectTool;
window.ShapeEllipseTool = ShapeEllipseTool;
window.ShapeLineTool = ShapeLineTool;
window.HandTool = HandTool;
window.ZoomTool = ZoomTool;
window.CloneStampTool = CloneStampTool;
window.BlurTool = BlurTool;
window.SharpenTool = SharpenTool;
window.SmudgeTool = SmudgeTool;
