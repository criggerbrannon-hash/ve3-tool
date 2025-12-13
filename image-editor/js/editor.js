// VE3 Image Editor - Main Editor Class

class ImageEditor {
    constructor() {
        this.width = 1920;
        this.height = 1080;
        this.zoom = 1;
        this.panX = 0;
        this.panY = 0;

        // Core components
        this.layerManager = null;
        this.historyManager = null;
        this.colorManager = null;
        this.selection = null;

        // Canvas elements
        this.mainCanvas = null;
        this.mainCtx = null;
        this.overlayCanvas = null;
        this.overlayCtx = null;
        this.canvasContainer = null;
        this.canvasWrapper = null;

        // Tools
        this.tools = {};
        this.currentTool = null;
        this.selectionFeather = 0;

        // State
        this.isDirty = false;
        this.fileName = 'Untitled';
        this.marchingAntsOffset = 0;
        this.marchingAntsInterval = null;

        // Initialize
        this.init();
    }

    init() {
        this.initCanvas();
        this.initComponents();
        this.initTools();
        this.initEventListeners();
        this.initUI();

        // Create new document
        this.newDocument(this.width, this.height, 'white');
    }

    initCanvas() {
        this.mainCanvas = document.getElementById('mainCanvas');
        this.mainCtx = this.mainCanvas.getContext('2d');
        this.overlayCanvas = document.getElementById('overlayCanvas');
        this.overlayCtx = this.overlayCanvas.getContext('2d');
        this.canvasContainer = document.getElementById('canvasContainer');
        this.canvasWrapper = document.getElementById('canvasWrapper');

        // Set initial size
        this.mainCanvas.width = this.width;
        this.mainCanvas.height = this.height;
        this.overlayCanvas.width = this.width;
        this.overlayCanvas.height = this.height;
    }

    initComponents() {
        this.layerManager = new LayerManager(this.width, this.height);
        this.historyManager = new HistoryManager(50);
        this.colorManager = new ColorManager();
        this.selection = new Selection(this.width, this.height);

        // Add listeners
        this.layerManager.addListener((type) => this.onLayerChange(type));
        this.colorManager.addListener((type, fg, bg) => this.onColorChange(type, fg, bg));
        this.historyManager.addListener((type) => this.onHistoryChange(type));
    }

    initTools() {
        this.tools = {
            'move': new MoveTool(this),
            'select-rect': new RectSelectTool(this),
            'select-ellipse': new EllipseSelectTool(this),
            'lasso': new LassoTool(this),
            'magic-wand': new MagicWandTool(this),
            'crop': new CropTool(this),
            'eyedropper': new EyedropperTool(this),
            'brush': new BrushTool(this),
            'pencil': new PencilTool(this),
            'eraser': new EraserTool(this),
            'fill': new FillTool(this),
            'gradient': new GradientTool(this),
            'clone': new CloneStampTool(this),
            'blur-tool': new BlurTool(this),
            'sharpen-tool': new SharpenTool(this),
            'smudge': new SmudgeTool(this),
            'text': new TextTool(this),
            'shape-rect': new ShapeRectTool(this),
            'shape-ellipse': new ShapeEllipseTool(this),
            'shape-line': new ShapeLineTool(this),
            'hand': new HandTool(this),
            'zoom': new ZoomTool(this)
        };

        this.setTool('move');
    }

    initEventListeners() {
        // Canvas mouse events
        this.canvasWrapper.addEventListener('mousedown', (e) => this.onMouseDown(e));
        this.canvasWrapper.addEventListener('mousemove', (e) => this.onMouseMove(e));
        this.canvasWrapper.addEventListener('mouseup', (e) => this.onMouseUp(e));
        this.canvasWrapper.addEventListener('mouseleave', (e) => this.onMouseUp(e));
        this.canvasWrapper.addEventListener('wheel', (e) => this.onWheel(e));

        // Touch events
        this.canvasWrapper.addEventListener('touchstart', (e) => this.onTouchStart(e));
        this.canvasWrapper.addEventListener('touchmove', (e) => this.onTouchMove(e));
        this.canvasWrapper.addEventListener('touchend', (e) => this.onTouchEnd(e));

        // Keyboard events
        document.addEventListener('keydown', (e) => this.onKeyDown(e));
        document.addEventListener('keyup', (e) => this.onKeyUp(e));

        // Window resize
        window.addEventListener('resize', () => this.onResize());

        // Prevent context menu on canvas
        this.canvasWrapper.addEventListener('contextmenu', (e) => e.preventDefault());

        // File drag and drop
        this.canvasWrapper.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'copy';
        });

        this.canvasWrapper.addEventListener('drop', (e) => {
            e.preventDefault();
            const file = e.dataTransfer.files[0];
            if (file && file.type.startsWith('image/')) {
                this.openImage(file);
            }
        });
    }

    initUI() {
        this.updateUI();
        this.initSwatches();
        this.initColorWheel();
        this.startMarchingAnts();
    }

    // Document operations
    newDocument(width, height, background = 'white') {
        this.width = width;
        this.height = height;

        this.mainCanvas.width = width;
        this.mainCanvas.height = height;
        this.overlayCanvas.width = width;
        this.overlayCanvas.height = height;

        this.layerManager = new LayerManager(width, height);
        this.selection = new Selection(width, height);

        // Fill background
        const bgLayer = this.layerManager.getActiveLayer();
        switch (background) {
            case 'white':
                bgLayer.fill('#ffffff');
                break;
            case 'black':
                bgLayer.fill('#000000');
                break;
            case 'transparent':
                bgLayer.clear();
                break;
            default:
                bgLayer.fill(background);
        }

        this.historyManager.clear();
        this.saveState('New Document', 'new');
        this.fileName = 'Untitled';
        this.isDirty = false;

        this.fitToScreen();
        this.render();
        this.updateUI();
    }

    async openImage(source) {
        try {
            const img = await Utils.loadImage(source);

            this.width = img.width;
            this.height = img.height;

            this.mainCanvas.width = img.width;
            this.mainCanvas.height = img.height;
            this.overlayCanvas.width = img.width;
            this.overlayCanvas.height = img.height;

            this.layerManager = new LayerManager(img.width, img.height);
            this.selection = new Selection(img.width, img.height);

            const layer = this.layerManager.getActiveLayer();
            layer.drawImage(img);

            this.historyManager.clear();
            this.saveState('Open Image', 'open');

            if (source instanceof File) {
                this.fileName = source.name.replace(/\.[^/.]+$/, '');
            }
            this.isDirty = false;

            this.fitToScreen();
            this.render();
            this.updateUI();
        } catch (error) {
            console.error('Error opening image:', error);
            alert('Error opening image');
        }
    }

    // Tool operations
    setTool(toolName) {
        if (this.currentTool) {
            this.currentTool.deactivate();
        }

        this.currentTool = this.tools[toolName];

        if (this.currentTool) {
            this.currentTool.activate();
            this.canvasWrapper.style.cursor = this.currentTool.cursor;

            // Update toolbar UI
            document.querySelectorAll('.tool-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.tool === toolName);
            });
        }
    }

    showToolOptions(optionsId) {
        document.querySelectorAll('.tool-options').forEach(el => {
            el.style.display = 'none';
        });

        const options = document.getElementById(optionsId);
        if (options) {
            options.style.display = 'flex';
        }
    }

    // Mouse event handlers
    onMouseDown(e) {
        const pos = this.getCanvasPosition(e);

        if (this.currentTool) {
            this.currentTool.onMouseDown(pos.x, pos.y, e);
        }
    }

    onMouseMove(e) {
        const pos = this.getCanvasPosition(e);

        // Update cursor position display
        document.getElementById('cursorPos').textContent = `X: ${Math.round(pos.x)} Y: ${Math.round(pos.y)}`;

        if (this.currentTool) {
            this.currentTool.onMouseMove(pos.x, pos.y, e);
        }
    }

    onMouseUp(e) {
        const pos = this.getCanvasPosition(e);

        if (this.currentTool) {
            this.currentTool.onMouseUp(pos.x, pos.y, e);
        }
    }

    onWheel(e) {
        e.preventDefault();

        if (e.ctrlKey) {
            // Zoom
            const delta = e.deltaY > 0 ? -0.1 : 0.1;
            this.setZoom(this.zoom + delta);
        } else {
            // Pan
            this.canvasContainer.scrollLeft += e.deltaX;
            this.canvasContainer.scrollTop += e.deltaY;
        }
    }

    onTouchStart(e) {
        if (e.touches.length === 1) {
            const touch = e.touches[0];
            const mouseEvent = new MouseEvent('mousedown', {
                clientX: touch.clientX,
                clientY: touch.clientY
            });
            this.onMouseDown(mouseEvent);
        }
    }

    onTouchMove(e) {
        if (e.touches.length === 1) {
            e.preventDefault();
            const touch = e.touches[0];
            const mouseEvent = new MouseEvent('mousemove', {
                clientX: touch.clientX,
                clientY: touch.clientY
            });
            this.onMouseMove(mouseEvent);
        }
    }

    onTouchEnd(e) {
        const mouseEvent = new MouseEvent('mouseup', {});
        this.onMouseUp(mouseEvent);
    }

    // Keyboard event handlers
    onKeyDown(e) {
        // Don't handle if typing in input
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.contentEditable === 'true') {
            return;
        }

        // Tool shortcuts
        const toolShortcuts = {
            'v': 'move',
            'm': 'select-rect',
            'l': 'lasso',
            'w': 'magic-wand',
            'c': 'crop',
            'i': 'eyedropper',
            'b': 'brush',
            'n': 'pencil',
            'e': 'eraser',
            'g': 'fill',
            't': 'text',
            's': 'clone',
            'h': 'hand',
            'z': 'zoom'
        };

        if (!e.ctrlKey && !e.metaKey && !e.altKey) {
            const tool = toolShortcuts[e.key.toLowerCase()];
            if (tool) {
                this.setTool(tool);
                e.preventDefault();
                return;
            }
        }

        // Color shortcuts
        if (e.key === 'x') {
            this.colorManager.swap();
            e.preventDefault();
        } else if (e.key === 'd') {
            this.colorManager.reset();
            e.preventDefault();
        }

        // Brush size shortcuts
        if (e.key === '[') {
            this.changeBrushSize(-5);
            e.preventDefault();
        } else if (e.key === ']') {
            this.changeBrushSize(5);
            e.preventDefault();
        }

        // Ctrl/Cmd shortcuts
        if (e.ctrlKey || e.metaKey) {
            switch (e.key.toLowerCase()) {
                case 'n':
                    e.preventDefault();
                    document.getElementById('newFileModal').classList.add('active');
                    break;
                case 'o':
                    e.preventDefault();
                    document.getElementById('fileInput').click();
                    break;
                case 's':
                    e.preventDefault();
                    if (e.shiftKey) {
                        document.getElementById('exportModal').classList.add('active');
                    } else {
                        this.quickSave();
                    }
                    break;
                case 'e':
                    e.preventDefault();
                    document.getElementById('exportModal').classList.add('active');
                    break;
                case 'z':
                    e.preventDefault();
                    this.undo();
                    break;
                case 'y':
                    e.preventDefault();
                    this.redo();
                    break;
                case 'a':
                    e.preventDefault();
                    this.selection.selectAll();
                    this.render();
                    break;
                case 'd':
                    e.preventDefault();
                    this.selection.deselect();
                    this.render();
                    break;
                case '=':
                case '+':
                    e.preventDefault();
                    this.zoomIn();
                    break;
                case '-':
                    e.preventDefault();
                    this.zoomOut();
                    break;
                case '0':
                    e.preventDefault();
                    this.fitToScreen();
                    break;
                case '1':
                    e.preventDefault();
                    this.setZoom(1);
                    break;
            }
        }

        // Delete key
        if (e.key === 'Delete' || e.key === 'Backspace') {
            if (this.selection.hasSelection()) {
                this.deleteSelection();
                e.preventDefault();
            }
        }

        // Pass to current tool
        if (this.currentTool) {
            this.currentTool.onKeyDown(e);
        }
    }

    onKeyUp(e) {
        if (this.currentTool) {
            this.currentTool.onKeyUp(e);
        }
    }

    onResize() {
        // Handled by CSS, but we could do something here
    }

    // Canvas position calculation
    getCanvasPosition(e) {
        const rect = this.mainCanvas.getBoundingClientRect();
        return {
            x: (e.clientX - rect.left) / this.zoom,
            y: (e.clientY - rect.top) / this.zoom
        };
    }

    // Rendering
    render() {
        this.layerManager.render(this.mainCanvas);
        this.renderSelection();
        this.updateNavigator();
    }

    renderSelection() {
        this.clearOverlay();

        if (this.selection.hasSelection()) {
            this.selection.drawMarchingAnts(this.overlayCtx, this.marchingAntsOffset);
        }
    }

    clearOverlay() {
        this.overlayCtx.clearRect(0, 0, this.width, this.height);
    }

    startMarchingAnts() {
        this.marchingAntsInterval = setInterval(() => {
            this.marchingAntsOffset = (this.marchingAntsOffset + 1) % 16;
            if (this.selection.hasSelection()) {
                this.renderSelection();
            }
        }, 100);
    }

    // Zoom operations
    setZoom(zoom) {
        this.zoom = Utils.clamp(zoom, 0.1, 5);

        const transform = `scale(${this.zoom})`;
        this.mainCanvas.style.transform = transform;
        this.overlayCanvas.style.transform = transform;

        document.getElementById('zoomLevel').textContent = Math.round(this.zoom * 100) + '%';
        document.getElementById('navZoomSlider').value = this.zoom * 100;
    }

    zoomIn(centerX, centerY) {
        this.setZoom(this.zoom + 0.1);
    }

    zoomOut(centerX, centerY) {
        this.setZoom(this.zoom - 0.1);
    }

    fitToScreen() {
        const container = this.canvasContainer;
        const padding = 40;
        const availWidth = container.clientWidth - padding;
        const availHeight = container.clientHeight - padding;

        const scaleX = availWidth / this.width;
        const scaleY = availHeight / this.height;
        const scale = Math.min(scaleX, scaleY, 1);

        this.setZoom(scale);
    }

    // History operations
    saveState(name, icon) {
        this.historyManager.pushState(name, HistoryIcons[icon] || icon, this.layerManager);
        this.isDirty = true;
    }

    undo() {
        if (this.historyManager.undo(this.layerManager)) {
            this.render();
            this.updateUI();
        }
    }

    redo() {
        if (this.historyManager.redo(this.layerManager)) {
            this.render();
            this.updateUI();
        }
    }

    // Selection operations
    deleteSelection() {
        const layer = this.layerManager.getActiveLayer();
        if (layer.locked) return;

        const ctx = layer.ctx;

        if (this.selection.hasSelection()) {
            const mask = this.selection.mask;

            ctx.save();
            ctx.globalCompositeOperation = 'destination-out';

            for (let y = 0; y < this.height; y++) {
                for (let x = 0; x < this.width; x++) {
                    const alpha = mask[y * this.width + x];
                    if (alpha > 0) {
                        ctx.fillStyle = `rgba(0, 0, 0, ${alpha / 255})`;
                        ctx.fillRect(x, y, 1, 1);
                    }
                }
            }

            ctx.restore();
        }

        this.saveState('Delete', 'eraser');
        this.render();
    }

    // Resize operations
    resize(width, height) {
        this.width = width;
        this.height = height;

        this.mainCanvas.width = width;
        this.mainCanvas.height = height;
        this.overlayCanvas.width = width;
        this.overlayCanvas.height = height;

        this.selection.resize(width, height);

        document.getElementById('imageSize').textContent = `${width} x ${height}`;

        this.render();
    }

    // Image transformations
    rotateImage(degrees) {
        this.layerManager.layers.forEach(layer => {
            layer.rotate(degrees);
        });

        if (degrees === 90 || degrees === -90) {
            [this.width, this.height] = [this.height, this.width];
            this.resize(this.width, this.height);
        }

        this.saveState('Rotate', 'rotate');
        this.render();
    }

    flipHorizontal() {
        this.layerManager.layers.forEach(layer => {
            layer.flipHorizontal();
        });
        this.saveState('Flip Horizontal', 'flip');
        this.render();
    }

    flipVertical() {
        this.layerManager.layers.forEach(layer => {
            layer.flipVertical();
        });
        this.saveState('Flip Vertical', 'flip');
        this.render();
    }

    // Export operations
    export(format, quality, scale) {
        const exportCanvas = Utils.createCanvas(this.width * scale, this.height * scale);
        const ctx = exportCanvas.getContext('2d');

        ctx.scale(scale, scale);
        this.layerManager.render(exportCanvas);

        Utils.downloadCanvas(exportCanvas, `${this.fileName}.${format}`, format, quality / 100);
    }

    quickSave() {
        this.export('png', 100, 1);
    }

    // UI updates
    updateUI() {
        this.updateLayersPanel();
        this.updateHistoryPanel();
        this.updateColorUI();
        this.updateStatusBar();
    }

    updateLayersPanel() {
        const list = document.getElementById('layersList');
        list.innerHTML = '';

        this.layerManager.layers.forEach((layer, index) => {
            const item = document.createElement('div');
            item.className = 'layer-item' + (index === this.layerManager.activeLayerIndex ? ' active' : '');
            item.dataset.index = index;

            const thumbnail = layer.getThumbnail();

            item.innerHTML = `
                <i class="layer-visibility fas ${layer.visible ? 'fa-eye' : 'fa-eye-slash'}"></i>
                <canvas class="layer-thumbnail"></canvas>
                <span class="layer-name">${layer.name}</span>
                <i class="layer-lock fas ${layer.locked ? 'fa-lock' : 'fa-lock-open'}"></i>
            `;

            const thumbCanvas = item.querySelector('.layer-thumbnail');
            thumbCanvas.width = 32;
            thumbCanvas.height = 32;
            thumbCanvas.getContext('2d').drawImage(thumbnail, 0, 0, 32, 32);

            // Event listeners
            item.addEventListener('click', () => {
                this.layerManager.setActiveLayer(index);
                this.updateLayersPanel();
            });

            item.querySelector('.layer-visibility').addEventListener('click', (e) => {
                e.stopPropagation();
                layer.visible = !layer.visible;
                this.render();
                this.updateLayersPanel();
            });

            item.querySelector('.layer-lock').addEventListener('click', (e) => {
                e.stopPropagation();
                layer.locked = !layer.locked;
                this.updateLayersPanel();
            });

            list.appendChild(item);
        });

        // Update blend mode and opacity
        const activeLayer = this.layerManager.getActiveLayer();
        if (activeLayer) {
            document.getElementById('blendMode').value = activeLayer.blendMode;
            document.getElementById('layerOpacity').value = activeLayer.opacity;
            document.getElementById('layerOpacityValue').textContent = activeLayer.opacity + '%';
        }
    }

    updateHistoryPanel() {
        const list = document.getElementById('historyList');
        list.innerHTML = '';

        const states = this.historyManager.getStates();
        const currentIndex = this.historyManager.currentIndex;

        states.forEach((state, index) => {
            const item = document.createElement('div');
            item.className = 'history-item';
            if (index === currentIndex) item.classList.add('active');
            if (index > currentIndex) item.classList.add('inactive');

            item.innerHTML = `
                <i class="fas ${state.icon}"></i>
                <span>${state.name}</span>
            `;

            item.addEventListener('click', () => {
                this.historyManager.goToState(index, this.layerManager);
                this.render();
                this.updateUI();
            });

            list.appendChild(item);
        });

        // Scroll to current state
        const activeItem = list.querySelector('.active');
        if (activeItem) {
            activeItem.scrollIntoView({ block: 'nearest' });
        }
    }

    updateColorUI() {
        const fg = this.colorManager.foreground;
        const bg = this.colorManager.background;

        document.getElementById('foregroundColor').style.backgroundColor = fg.toRGBA();
        document.getElementById('backgroundColor').style.backgroundColor = bg.toRGBA();

        // Update color inputs
        const hsv = fg.toHSV();
        document.getElementById('colorH').value = hsv.h;
        document.getElementById('colorS').value = hsv.s;
        document.getElementById('colorB').value = hsv.v;
        document.getElementById('colorR').value = fg.r;
        document.getElementById('colorG').value = fg.g;
        document.getElementById('colorBl').value = fg.b;
        document.getElementById('colorHex').value = fg.toHex();
    }

    updateStatusBar() {
        document.getElementById('imageSize').textContent = `${this.width} x ${this.height}`;

        // Estimate file size
        const estimatedSize = this.width * this.height * 4;
        document.getElementById('fileSize').textContent = Utils.formatFileSize(estimatedSize);
    }

    // Swatches
    initSwatches() {
        const grid = document.getElementById('swatchesGrid');
        grid.innerHTML = '';

        DEFAULT_SWATCHES.forEach(color => {
            const swatch = document.createElement('div');
            swatch.className = 'swatch';
            swatch.style.backgroundColor = color;
            swatch.addEventListener('click', (e) => {
                if (e.altKey) {
                    this.colorManager.setBackground(Color.fromHex(color));
                } else {
                    this.colorManager.setForeground(Color.fromHex(color));
                }
            });
            grid.appendChild(swatch);
        });
    }

    // Color wheel
    initColorWheel() {
        const wheel = document.getElementById('colorWheel');
        const wheelCtx = wheel.getContext('2d');
        const brightness = document.getElementById('colorBrightness');
        const brightnessCtx = brightness.getContext('2d');

        // Draw color wheel
        const centerX = wheel.width / 2;
        const centerY = wheel.height / 2;
        const radius = Math.min(centerX, centerY);

        for (let angle = 0; angle < 360; angle++) {
            const startAngle = Utils.degToRad(angle - 1);
            const endAngle = Utils.degToRad(angle + 1);

            wheelCtx.beginPath();
            wheelCtx.moveTo(centerX, centerY);
            wheelCtx.arc(centerX, centerY, radius, startAngle, endAngle);
            wheelCtx.closePath();

            const gradient = wheelCtx.createRadialGradient(centerX, centerY, 0, centerX, centerY, radius);
            gradient.addColorStop(0, 'white');
            gradient.addColorStop(1, `hsl(${angle}, 100%, 50%)`);
            wheelCtx.fillStyle = gradient;
            wheelCtx.fill();
        }

        // Draw brightness bar
        const brightGradient = brightnessCtx.createLinearGradient(0, 0, 0, brightness.height);
        brightGradient.addColorStop(0, 'white');
        brightGradient.addColorStop(1, 'black');
        brightnessCtx.fillStyle = brightGradient;
        brightnessCtx.fillRect(0, 0, brightness.width, brightness.height);

        // Color wheel click
        wheel.addEventListener('click', (e) => {
            const rect = wheel.getBoundingClientRect();
            const x = e.clientX - rect.left - centerX;
            const y = e.clientY - rect.top - centerY;

            const angle = (Utils.radToDeg(Math.atan2(y, x)) + 360) % 360;
            const distance = Math.min(Utils.distance(0, 0, x, y), radius);
            const saturation = (distance / radius) * 100;

            const currentHSV = this.colorManager.foreground.toHSV();
            const newColor = Color.fromHSV(angle, saturation, currentHSV.v);
            this.colorManager.setForeground(newColor);
        });

        // Brightness click
        brightness.addEventListener('click', (e) => {
            const rect = brightness.getBoundingClientRect();
            const y = e.clientY - rect.top;
            const value = 100 - (y / brightness.height) * 100;

            const currentHSV = this.colorManager.foreground.toHSV();
            const newColor = Color.fromHSV(currentHSV.h, currentHSV.s, value);
            this.colorManager.setForeground(newColor);
        });
    }

    // Navigator
    updateNavigator() {
        const navCanvas = document.getElementById('navigatorCanvas');
        const navCtx = navCanvas.getContext('2d');

        const scale = Math.min(navCanvas.width / this.width, navCanvas.height / this.height);

        navCtx.clearRect(0, 0, navCanvas.width, navCanvas.height);
        navCtx.drawImage(this.mainCanvas, 0, 0, this.width * scale, this.height * scale);

        // Draw viewport rectangle
        const viewRect = {
            x: 0,
            y: 0,
            width: this.canvasContainer.clientWidth / this.zoom * scale,
            height: this.canvasContainer.clientHeight / this.zoom * scale
        };

        navCtx.strokeStyle = 'red';
        navCtx.lineWidth = 2;
        navCtx.strokeRect(viewRect.x, viewRect.y, viewRect.width, viewRect.height);
    }

    // Change brush size
    changeBrushSize(delta) {
        const sizeInput = document.getElementById('brushSize');
        if (sizeInput) {
            const newSize = Utils.clamp(parseInt(sizeInput.value) + delta, 1, 200);
            sizeInput.value = newSize;
            document.getElementById('brushSizeValue').textContent = newSize + 'px';
            if (this.currentTool && this.currentTool.updateOptions) {
                this.currentTool.updateOptions();
            }
        }
    }

    // Callbacks
    onLayerChange(type) {
        this.render();
        this.updateLayersPanel();
    }

    onColorChange(type, fg, bg) {
        this.updateColorUI();
    }

    onHistoryChange(type) {
        this.updateHistoryPanel();
    }
}

// Export
window.ImageEditor = ImageEditor;
