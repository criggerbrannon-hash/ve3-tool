// VE3 Image Editor - Application Entry Point

let editor;

document.addEventListener('DOMContentLoaded', () => {
    // Initialize editor
    editor = new ImageEditor();

    // Initialize UI components
    initMenus();
    initToolbar();
    initToolOptions();
    initPanels();
    initModals();
    initFileHandling();

    // Set status
    document.getElementById('statusInfo').textContent = 'Ready';
});

// Menu handling
function initMenus() {
    // Menu item click handling
    document.querySelectorAll('.menu-option').forEach(option => {
        option.addEventListener('click', (e) => {
            const id = option.id;
            handleMenuAction(id);
            // Close menu
            document.querySelectorAll('.dropdown-menu').forEach(menu => {
                menu.style.display = 'none';
            });
        });
    });
}

function handleMenuAction(action) {
    switch (action) {
        // File menu
        case 'newFile':
            document.getElementById('newFileModal').classList.add('active');
            break;
        case 'openFile':
            document.getElementById('fileInput').click();
            break;
        case 'saveFile':
            editor.quickSave();
            break;
        case 'saveAs':
        case 'exportFile':
            showExportModal();
            break;

        // Edit menu
        case 'undo':
            editor.undo();
            break;
        case 'redo':
            editor.redo();
            break;
        case 'cut':
            // Copy then delete
            copySelection();
            editor.deleteSelection();
            break;
        case 'copy':
            copySelection();
            break;
        case 'paste':
            pasteClipboard();
            break;
        case 'selectAll':
            editor.selection.selectAll();
            editor.render();
            break;
        case 'deselect':
            editor.selection.deselect();
            editor.render();
            break;

        // Image menu
        case 'imageSize':
            showImageSizeModal();
            break;
        case 'canvasSize':
            showCanvasSizeModal();
            break;
        case 'rotateLeft':
            editor.rotateImage(-90);
            break;
        case 'rotateRight':
            editor.rotateImage(90);
            break;
        case 'flipH':
            editor.flipHorizontal();
            break;
        case 'flipV':
            editor.flipVertical();
            break;

        // Filter menu
        case 'filterBlur':
            showFilterModal('blur', 'Blur', [
                { name: 'radius', label: 'Radius', type: 'range', min: 1, max: 50, value: 5 }
            ]);
            break;
        case 'filterSharpen':
            applyFilter('sharpen');
            break;
        case 'filterNoise':
            showFilterModal('noise', 'Add Noise', [
                { name: 'amount', label: 'Amount', type: 'range', min: 1, max: 100, value: 25 }
            ]);
            break;
        case 'filterGrayscale':
            applyFilter('grayscale');
            break;
        case 'filterSepia':
            applyFilter('sepia');
            break;
        case 'filterInvert':
            applyFilter('invert');
            break;
        case 'filterVignette':
            showFilterModal('vignette', 'Vignette', [
                { name: 'amount', label: 'Amount', type: 'range', min: 0, max: 100, value: 50 },
                { name: 'radius', label: 'Radius', type: 'range', min: 10, max: 100, value: 50 }
            ]);
            break;
        case 'filterPixelate':
            showFilterModal('pixelate', 'Pixelate', [
                { name: 'size', label: 'Size', type: 'range', min: 2, max: 50, value: 10 }
            ]);
            break;

        // View menu
        case 'zoomIn':
            editor.zoomIn();
            break;
        case 'zoomOut':
            editor.zoomOut();
            break;
        case 'zoomFit':
            editor.fitToScreen();
            break;
        case 'zoom100':
            editor.setZoom(1);
            break;
        case 'toggleGrid':
            toggleGrid();
            break;
        case 'toggleRulers':
            toggleRulers();
            break;

        // Help menu
        case 'shortcuts':
            document.getElementById('shortcutsModal').classList.add('active');
            break;
        case 'about':
            document.getElementById('aboutModal').classList.add('active');
            break;
    }
}

// Toolbar handling
function initToolbar() {
    document.querySelectorAll('.tool-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tool = btn.dataset.tool;
            if (tool) {
                editor.setTool(tool);
            }
        });
    });

    // Color boxes
    document.getElementById('foregroundColor').addEventListener('click', () => {
        showColorPicker('foreground');
    });

    document.getElementById('backgroundColor').addEventListener('click', () => {
        showColorPicker('background');
    });

    document.getElementById('swapColors').addEventListener('click', () => {
        editor.colorManager.swap();
    });

    document.getElementById('resetColors').addEventListener('click', () => {
        editor.colorManager.reset();
    });
}

// Tool options handling
function initToolOptions() {
    // Brush options
    const brushSize = document.getElementById('brushSize');
    const brushHardness = document.getElementById('brushHardness');
    const brushOpacity = document.getElementById('brushOpacity');
    const brushFlow = document.getElementById('brushFlow');

    brushSize.addEventListener('input', () => {
        document.getElementById('brushSizeValue').textContent = brushSize.value + 'px';
        if (editor.currentTool && editor.currentTool.updateOptions) {
            editor.currentTool.updateOptions();
        }
    });

    brushHardness.addEventListener('input', () => {
        document.getElementById('brushHardnessValue').textContent = brushHardness.value + '%';
        if (editor.currentTool && editor.currentTool.updateOptions) {
            editor.currentTool.updateOptions();
        }
    });

    brushOpacity.addEventListener('input', () => {
        document.getElementById('brushOpacityValue').textContent = brushOpacity.value + '%';
        if (editor.currentTool && editor.currentTool.updateOptions) {
            editor.currentTool.updateOptions();
        }
    });

    brushFlow.addEventListener('input', () => {
        document.getElementById('brushFlowValue').textContent = brushFlow.value + '%';
        if (editor.currentTool && editor.currentTool.updateOptions) {
            editor.currentTool.updateOptions();
        }
    });

    // Eraser options
    const eraserSize = document.getElementById('eraserSize');
    const eraserHardness = document.getElementById('eraserHardness');
    const eraserOpacity = document.getElementById('eraserOpacity');

    eraserSize.addEventListener('input', () => {
        document.getElementById('eraserSizeValue').textContent = eraserSize.value + 'px';
        if (editor.currentTool && editor.currentTool.updateOptions) {
            editor.currentTool.updateOptions();
        }
    });

    eraserHardness.addEventListener('input', () => {
        document.getElementById('eraserHardnessValue').textContent = eraserHardness.value + '%';
        if (editor.currentTool && editor.currentTool.updateOptions) {
            editor.currentTool.updateOptions();
        }
    });

    eraserOpacity.addEventListener('input', () => {
        document.getElementById('eraserOpacityValue').textContent = eraserOpacity.value + '%';
        if (editor.currentTool && editor.currentTool.updateOptions) {
            editor.currentTool.updateOptions();
        }
    });

    // Text options
    document.getElementById('fontFamily').addEventListener('change', () => {
        if (editor.currentTool && editor.currentTool.updateOptions) {
            editor.currentTool.updateOptions();
        }
    });

    document.getElementById('fontSize').addEventListener('change', () => {
        if (editor.currentTool && editor.currentTool.updateOptions) {
            editor.currentTool.updateOptions();
        }
    });

    document.getElementById('boldBtn').addEventListener('click', (e) => {
        e.target.closest('button').classList.toggle('active');
        if (editor.tools.text) {
            editor.tools.text.bold = e.target.closest('button').classList.contains('active');
            editor.tools.text.updateOptions();
        }
    });

    document.getElementById('italicBtn').addEventListener('click', (e) => {
        e.target.closest('button').classList.toggle('active');
        if (editor.tools.text) {
            editor.tools.text.italic = e.target.closest('button').classList.contains('active');
            editor.tools.text.updateOptions();
        }
    });

    document.getElementById('underlineBtn').addEventListener('click', (e) => {
        e.target.closest('button').classList.toggle('active');
        if (editor.tools.text) {
            editor.tools.text.underline = e.target.closest('button').classList.contains('active');
            editor.tools.text.updateOptions();
        }
    });

    // Shape options
    document.getElementById('shapeFill').addEventListener('change', () => {
        if (editor.currentTool && editor.currentTool.updateOptions) {
            editor.currentTool.updateOptions();
        }
    });

    document.getElementById('shapeStroke').addEventListener('change', () => {
        if (editor.currentTool && editor.currentTool.updateOptions) {
            editor.currentTool.updateOptions();
        }
    });

    document.getElementById('shapeStrokeWidth').addEventListener('change', () => {
        if (editor.currentTool && editor.currentTool.updateOptions) {
            editor.currentTool.updateOptions();
        }
    });

    // Selection options
    const selectionFeather = document.getElementById('selectionFeather');
    selectionFeather.addEventListener('input', () => {
        document.getElementById('selectionFeatherValue').textContent = selectionFeather.value + 'px';
        editor.selectionFeather = parseInt(selectionFeather.value);
    });

    document.getElementById('selectInverse').addEventListener('click', () => {
        editor.selection.inverse();
        editor.render();
    });

    // Magic wand options
    const wandTolerance = document.getElementById('wandTolerance');
    wandTolerance.addEventListener('input', () => {
        document.getElementById('wandToleranceValue').textContent = wandTolerance.value;
        if (editor.currentTool && editor.currentTool.updateOptions) {
            editor.currentTool.updateOptions();
        }
    });

    document.getElementById('wandContiguous').addEventListener('change', () => {
        if (editor.currentTool && editor.currentTool.updateOptions) {
            editor.currentTool.updateOptions();
        }
    });
}

// Panels handling
function initPanels() {
    // Panel toggle
    document.querySelectorAll('.panel-header').forEach(header => {
        header.addEventListener('click', () => {
            header.parentElement.classList.toggle('collapsed');
        });
    });

    // Layer actions
    document.getElementById('addLayer').addEventListener('click', () => {
        editor.layerManager.addLayer();
        editor.saveState('New Layer', 'layer');
        editor.updateUI();
    });

    document.getElementById('duplicateLayer').addEventListener('click', () => {
        editor.layerManager.duplicateLayer(editor.layerManager.activeLayerIndex);
        editor.saveState('Duplicate Layer', 'layer');
        editor.updateUI();
    });

    document.getElementById('deleteLayer').addEventListener('click', () => {
        if (editor.layerManager.removeLayer(editor.layerManager.activeLayerIndex)) {
            editor.saveState('Delete Layer', 'layer');
            editor.render();
            editor.updateUI();
        }
    });

    document.getElementById('mergeLayer').addEventListener('click', () => {
        if (editor.layerManager.mergeDown(editor.layerManager.activeLayerIndex)) {
            editor.saveState('Merge Layer', 'layer');
            editor.render();
            editor.updateUI();
        }
    });

    // Blend mode
    document.getElementById('blendMode').addEventListener('change', (e) => {
        const layer = editor.layerManager.getActiveLayer();
        if (layer) {
            layer.blendMode = e.target.value;
            editor.render();
        }
    });

    // Layer opacity
    document.getElementById('layerOpacity').addEventListener('input', (e) => {
        const layer = editor.layerManager.getActiveLayer();
        if (layer) {
            layer.opacity = parseInt(e.target.value);
            document.getElementById('layerOpacityValue').textContent = layer.opacity + '%';
            editor.render();
        }
    });

    // Navigator zoom
    document.getElementById('navZoomSlider').addEventListener('input', (e) => {
        editor.setZoom(parseInt(e.target.value) / 100);
    });

    document.getElementById('navZoomIn').addEventListener('click', () => {
        editor.zoomIn();
    });

    document.getElementById('navZoomOut').addEventListener('click', () => {
        editor.zoomOut();
    });

    // Color inputs
    ['colorH', 'colorS', 'colorB'].forEach(id => {
        document.getElementById(id).addEventListener('change', updateColorFromHSV);
    });

    ['colorR', 'colorG', 'colorBl'].forEach(id => {
        document.getElementById(id).addEventListener('change', updateColorFromRGB);
    });

    document.getElementById('colorHex').addEventListener('change', (e) => {
        const color = Color.fromHex(e.target.value);
        editor.colorManager.setForeground(color);
    });

    // Adjustment buttons
    document.querySelectorAll('.adj-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const adj = btn.dataset.adj;
            showAdjustmentModal(adj);
        });
    });
}

function updateColorFromHSV() {
    const h = parseInt(document.getElementById('colorH').value);
    const s = parseInt(document.getElementById('colorS').value);
    const v = parseInt(document.getElementById('colorB').value);
    const color = Color.fromHSV(h, s, v);
    editor.colorManager.setForeground(color);
}

function updateColorFromRGB() {
    const r = parseInt(document.getElementById('colorR').value);
    const g = parseInt(document.getElementById('colorG').value);
    const b = parseInt(document.getElementById('colorBl').value);
    const color = new Color(r, g, b);
    editor.colorManager.setForeground(color);
}

// Modal handling
function initModals() {
    // Close buttons
    document.querySelectorAll('.modal-close, .modal-cancel').forEach(btn => {
        btn.addEventListener('click', () => {
            btn.closest('.modal').classList.remove('active');
        });
    });

    // Click outside to close
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.remove('active');
            }
        });
    });

    // New file modal
    document.getElementById('createNewFile').addEventListener('click', () => {
        const width = parseInt(document.getElementById('newWidth').value);
        const height = parseInt(document.getElementById('newHeight').value);
        const background = document.getElementById('newBackground').value;

        editor.newDocument(width, height, background);
        document.getElementById('newFileModal').classList.remove('active');
    });

    // Presets
    document.querySelectorAll('.preset-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.getElementById('newWidth').value = btn.dataset.w;
            document.getElementById('newHeight').value = btn.dataset.h;
        });
    });

    // Export modal
    document.getElementById('exportFormat').addEventListener('change', (e) => {
        const qualityRow = document.getElementById('qualityRow');
        qualityRow.style.display = e.target.value === 'png' ? 'none' : 'flex';
    });

    document.getElementById('exportQuality').addEventListener('input', (e) => {
        document.getElementById('exportQualityValue').textContent = e.target.value + '%';
    });

    document.getElementById('exportImage').addEventListener('click', () => {
        const format = document.getElementById('exportFormat').value;
        const quality = parseInt(document.getElementById('exportQuality').value);
        const scale = parseFloat(document.getElementById('exportScale').value);

        editor.export(format, quality, scale);
        document.getElementById('exportModal').classList.remove('active');
    });

    // Image size modal
    document.getElementById('applyResize').addEventListener('click', () => {
        const width = parseInt(document.getElementById('resizeWidth').value);
        const height = parseInt(document.getElementById('resizeHeight').value);
        const method = document.getElementById('resampleMethod').value;

        editor.layerManager.resize(width, height, method);
        editor.resize(width, height);
        editor.saveState('Resize', 'resize');

        document.getElementById('imageSizeModal').classList.remove('active');
    });

    // Constrain proportions
    const constrainCheckbox = document.getElementById('constrainProportions');
    const resizeWidth = document.getElementById('resizeWidth');
    const resizeHeight = document.getElementById('resizeHeight');
    let aspectRatio = 1;

    resizeWidth.addEventListener('focus', () => {
        aspectRatio = editor.width / editor.height;
    });

    resizeWidth.addEventListener('input', () => {
        if (constrainCheckbox.checked) {
            resizeHeight.value = Math.round(parseInt(resizeWidth.value) / aspectRatio);
        }
    });

    resizeHeight.addEventListener('input', () => {
        if (constrainCheckbox.checked) {
            resizeWidth.value = Math.round(parseInt(resizeHeight.value) * aspectRatio);
        }
    });

    // Apply adjustment
    document.getElementById('applyAdjustment').addEventListener('click', () => {
        applyCurrentAdjustment();
        document.getElementById('adjustmentsModal').classList.remove('active');
    });

    // Apply filter
    document.getElementById('applyFilter').addEventListener('click', () => {
        applyCurrentFilter();
        document.getElementById('filterModal').classList.remove('active');
    });
}

// File handling
function initFileHandling() {
    const fileInput = document.getElementById('fileInput');

    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            editor.openImage(file);
        }
        fileInput.value = '';
    });
}

// Helper functions
function showExportModal() {
    const modal = document.getElementById('exportModal');

    // Update preview
    const preview = document.getElementById('exportPreview');
    const scale = Math.min(300 / editor.width, 200 / editor.height);
    preview.width = editor.width * scale;
    preview.height = editor.height * scale;

    const ctx = preview.getContext('2d');
    ctx.drawImage(editor.mainCanvas, 0, 0, preview.width, preview.height);

    modal.classList.add('active');
}

function showImageSizeModal() {
    document.getElementById('resizeWidth').value = editor.width;
    document.getElementById('resizeHeight').value = editor.height;
    document.getElementById('imageSizeModal').classList.add('active');
}

function showCanvasSizeModal() {
    // Similar to image size but for canvas
    showImageSizeModal();
}

function showColorPicker(target) {
    const modal = document.getElementById('colorPickerModal');
    modal.dataset.target = target;

    const currentColor = target === 'foreground'
        ? editor.colorManager.foreground
        : editor.colorManager.background;

    // Initialize color picker
    initColorPickerUI(currentColor);

    document.getElementById('colorPreviewOld').style.backgroundColor = currentColor.toRGBA();
    document.getElementById('colorPreviewNew').style.backgroundColor = currentColor.toRGBA();

    modal.classList.add('active');
}

function initColorPickerUI(initialColor) {
    const gradient = document.getElementById('colorPickerGradient');
    const gradientCtx = gradient.getContext('2d');
    const hue = document.getElementById('colorPickerHue');
    const hueCtx = hue.getContext('2d');

    const hsv = initialColor.toHSV();
    let currentHue = hsv.h;

    // Draw hue bar
    for (let y = 0; y < hue.height; y++) {
        const h = (y / hue.height) * 360;
        hueCtx.fillStyle = `hsl(${h}, 100%, 50%)`;
        hueCtx.fillRect(0, y, hue.width, 1);
    }

    // Draw gradient
    function drawGradient(h) {
        const color = Color.fromHSV(h, 100, 100);

        // Horizontal gradient (saturation)
        const gradientH = gradientCtx.createLinearGradient(0, 0, gradient.width, 0);
        gradientH.addColorStop(0, 'white');
        gradientH.addColorStop(1, color.toRGBA());
        gradientCtx.fillStyle = gradientH;
        gradientCtx.fillRect(0, 0, gradient.width, gradient.height);

        // Vertical gradient (brightness)
        const gradientV = gradientCtx.createLinearGradient(0, 0, 0, gradient.height);
        gradientV.addColorStop(0, 'rgba(0, 0, 0, 0)');
        gradientV.addColorStop(1, 'black');
        gradientCtx.fillStyle = gradientV;
        gradientCtx.fillRect(0, 0, gradient.width, gradient.height);
    }

    drawGradient(currentHue);

    // Position cursors
    const cursor = document.getElementById('colorPickerCursor');
    const hueCursor = document.getElementById('colorPickerHueCursor');

    cursor.style.left = (hsv.s / 100 * gradient.width) + 'px';
    cursor.style.top = ((100 - hsv.v) / 100 * gradient.height) + 'px';
    hueCursor.style.top = (hsv.h / 360 * hue.height) + 'px';

    // Hue click
    hue.onclick = (e) => {
        const rect = hue.getBoundingClientRect();
        const y = e.clientY - rect.top;
        currentHue = (y / hue.height) * 360;
        hueCursor.style.top = y + 'px';
        drawGradient(currentHue);
        updateColorPreview();
    };

    // Gradient click
    gradient.onclick = (e) => {
        const rect = gradient.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        cursor.style.left = x + 'px';
        cursor.style.top = y + 'px';
        updateColorPreview();
    };

    function updateColorPreview() {
        const s = parseFloat(cursor.style.left) / gradient.width * 100;
        const v = (1 - parseFloat(cursor.style.top) / gradient.height) * 100;
        const newColor = Color.fromHSV(currentHue, s, v);
        document.getElementById('colorPreviewNew').style.backgroundColor = newColor.toRGBA();
    }

    // Select color
    document.getElementById('selectColor').onclick = () => {
        const s = parseFloat(cursor.style.left) / gradient.width * 100;
        const v = (1 - parseFloat(cursor.style.top) / gradient.height) * 100;
        const newColor = Color.fromHSV(currentHue, s, v);

        const modal = document.getElementById('colorPickerModal');
        if (modal.dataset.target === 'foreground') {
            editor.colorManager.setForeground(newColor);
        } else {
            editor.colorManager.setBackground(newColor);
        }
        modal.classList.remove('active');
    };
}

// Adjustment modal
let currentAdjustment = null;
let adjustmentPreviewData = null;

function showAdjustmentModal(type) {
    const modal = document.getElementById('adjustmentsModal');
    const title = document.getElementById('adjustmentTitle');
    const controls = document.getElementById('adjustmentControls');

    currentAdjustment = type;
    controls.innerHTML = '';

    const configs = {
        'brightness-contrast': {
            title: 'Brightness/Contrast',
            controls: [
                { name: 'brightness', label: 'Brightness', min: -100, max: 100, value: 0 },
                { name: 'contrast', label: 'Contrast', min: -100, max: 100, value: 0 }
            ]
        },
        'hue-saturation': {
            title: 'Hue/Saturation',
            controls: [
                { name: 'hue', label: 'Hue', min: -180, max: 180, value: 0 },
                { name: 'saturation', label: 'Saturation', min: -100, max: 100, value: 0 },
                { name: 'lightness', label: 'Lightness', min: -100, max: 100, value: 0 }
            ]
        },
        'levels': {
            title: 'Levels',
            controls: [
                { name: 'inputMin', label: 'Input Min', min: 0, max: 255, value: 0 },
                { name: 'inputMax', label: 'Input Max', min: 0, max: 255, value: 255 },
                { name: 'gamma', label: 'Gamma', min: 0.1, max: 3, value: 1, step: 0.1 },
                { name: 'outputMin', label: 'Output Min', min: 0, max: 255, value: 0 },
                { name: 'outputMax', label: 'Output Max', min: 0, max: 255, value: 255 }
            ]
        },
        'exposure': {
            title: 'Exposure',
            controls: [
                { name: 'exposure', label: 'Exposure', min: -3, max: 3, value: 0, step: 0.1 }
            ]
        },
        'vibrance': {
            title: 'Vibrance',
            controls: [
                { name: 'vibrance', label: 'Vibrance', min: -100, max: 100, value: 0 }
            ]
        },
        'color-balance': {
            title: 'Color Balance',
            controls: [
                { name: 'cyan-red', label: 'Cyan/Red', min: -100, max: 100, value: 0 },
                { name: 'magenta-green', label: 'Magenta/Green', min: -100, max: 100, value: 0 },
                { name: 'yellow-blue', label: 'Yellow/Blue', min: -100, max: 100, value: 0 }
            ]
        },
        'shadows-highlights': {
            title: 'Shadows/Highlights',
            controls: [
                { name: 'shadows', label: 'Shadows', min: -100, max: 100, value: 0 },
                { name: 'highlights', label: 'Highlights', min: -100, max: 100, value: 0 }
            ]
        }
    };

    const config = configs[type];
    if (!config) return;

    title.textContent = config.title;

    config.controls.forEach(ctrl => {
        const div = document.createElement('div');
        div.className = 'adjustment-control';
        div.innerHTML = `
            <label>${ctrl.label}:</label>
            <input type="range" id="adj_${ctrl.name}"
                min="${ctrl.min}" max="${ctrl.max}"
                value="${ctrl.value}" step="${ctrl.step || 1}">
            <span id="adj_${ctrl.name}_value">${ctrl.value}</span>
        `;
        controls.appendChild(div);

        const input = div.querySelector('input');
        const valueSpan = div.querySelector('span');

        input.addEventListener('input', () => {
            valueSpan.textContent = input.value;
            if (document.getElementById('previewAdjustment').checked) {
                previewAdjustment();
            }
        });
    });

    // Store original image data
    const layer = editor.layerManager.getActiveLayer();
    adjustmentPreviewData = layer.getImageData();

    // Update preview
    updateAdjustmentPreview();

    modal.classList.add('active');
}

function updateAdjustmentPreview() {
    const preview = document.getElementById('adjustmentPreview');
    const layer = editor.layerManager.getActiveLayer();

    const scale = Math.min(500 / layer.width, 250 / layer.height, 1);
    preview.width = layer.width * scale;
    preview.height = layer.height * scale;

    const ctx = preview.getContext('2d');
    ctx.drawImage(layer.canvas, 0, 0, preview.width, preview.height);
}

function previewAdjustment() {
    if (!adjustmentPreviewData) return;

    const layer = editor.layerManager.getActiveLayer();
    const tempData = Utils.deepClone(adjustmentPreviewData);

    applyAdjustmentToData(currentAdjustment, tempData);
    layer.putImageData(tempData);
    editor.render();
    updateAdjustmentPreview();
}

function applyAdjustmentToData(type, imageData) {
    switch (type) {
        case 'brightness-contrast':
            const brightness = parseInt(document.getElementById('adj_brightness').value);
            const contrast = parseInt(document.getElementById('adj_contrast').value);
            Adjustments.brightnessContrast(imageData, brightness, contrast);
            break;

        case 'hue-saturation':
            const hue = parseInt(document.getElementById('adj_hue').value);
            const saturation = parseInt(document.getElementById('adj_saturation').value);
            const lightness = parseInt(document.getElementById('adj_lightness').value);
            Adjustments.hueSaturationLightness(imageData, hue, saturation, lightness);
            break;

        case 'levels':
            const inputMin = parseInt(document.getElementById('adj_inputMin').value);
            const inputMax = parseInt(document.getElementById('adj_inputMax').value);
            const gamma = parseFloat(document.getElementById('adj_gamma').value);
            const outputMin = parseInt(document.getElementById('adj_outputMin').value);
            const outputMax = parseInt(document.getElementById('adj_outputMax').value);
            Adjustments.levels(imageData, inputMin, inputMax, outputMin, outputMax, gamma);
            break;

        case 'exposure':
            const exposure = parseFloat(document.getElementById('adj_exposure').value);
            Adjustments.exposure(imageData, exposure);
            break;

        case 'vibrance':
            const vibrance = parseInt(document.getElementById('adj_vibrance').value);
            Adjustments.vibrance(imageData, vibrance);
            break;

        case 'color-balance':
            const cr = parseInt(document.getElementById('adj_cyan-red').value);
            const mg = parseInt(document.getElementById('adj_magenta-green').value);
            const yb = parseInt(document.getElementById('adj_yellow-blue').value);
            Adjustments.colorBalance(imageData,
                { r: 0, g: 0, b: 0 },
                { r: cr, g: mg, b: yb },
                { r: 0, g: 0, b: 0 }
            );
            break;

        case 'shadows-highlights':
            const shadows = parseInt(document.getElementById('adj_shadows').value);
            const highlights = parseInt(document.getElementById('adj_highlights').value);
            Adjustments.shadowsHighlights(imageData, shadows, highlights);
            break;
    }
}

function applyCurrentAdjustment() {
    if (!adjustmentPreviewData) return;

    const layer = editor.layerManager.getActiveLayer();
    layer.putImageData(adjustmentPreviewData);

    const imageData = layer.getImageData();
    applyAdjustmentToData(currentAdjustment, imageData);
    layer.putImageData(imageData);

    editor.saveState('Adjustment', 'adjustment');
    editor.render();

    adjustmentPreviewData = null;
}

// Filter modal
let currentFilter = null;
let filterPreviewData = null;

function showFilterModal(type, title, controls) {
    const modal = document.getElementById('filterModal');
    const titleEl = document.getElementById('filterTitle');
    const controlsEl = document.getElementById('filterControls');

    currentFilter = type;
    titleEl.textContent = title;
    controlsEl.innerHTML = '';

    controls.forEach(ctrl => {
        const div = document.createElement('div');
        div.className = 'adjustment-control';
        div.innerHTML = `
            <label>${ctrl.label}:</label>
            <input type="range" id="filter_${ctrl.name}"
                min="${ctrl.min}" max="${ctrl.max}" value="${ctrl.value}">
            <span id="filter_${ctrl.name}_value">${ctrl.value}</span>
        `;
        controlsEl.appendChild(div);

        const input = div.querySelector('input');
        const valueSpan = div.querySelector('span');

        input.addEventListener('input', () => {
            valueSpan.textContent = input.value;
            previewFilter();
        });
    });

    // Store original data
    const layer = editor.layerManager.getActiveLayer();
    filterPreviewData = layer.getImageData();

    updateFilterPreview();
    modal.classList.add('active');
}

function updateFilterPreview() {
    const preview = document.getElementById('filterPreview');
    const layer = editor.layerManager.getActiveLayer();

    const scale = Math.min(500 / layer.width, 250 / layer.height, 1);
    preview.width = layer.width * scale;
    preview.height = layer.height * scale;

    const ctx = preview.getContext('2d');
    ctx.drawImage(layer.canvas, 0, 0, preview.width, preview.height);
}

function previewFilter() {
    if (!filterPreviewData) return;

    const layer = editor.layerManager.getActiveLayer();
    const tempData = Utils.deepClone(filterPreviewData);

    applyFilterToData(currentFilter, tempData);
    layer.putImageData(tempData);
    editor.render();
    updateFilterPreview();
}

function applyFilterToData(type, imageData) {
    switch (type) {
        case 'blur':
            const blurRadius = parseInt(document.getElementById('filter_radius').value);
            Filters.blur(imageData, blurRadius);
            break;
        case 'noise':
            const noiseAmount = parseInt(document.getElementById('filter_amount').value);
            Filters.noise(imageData, noiseAmount);
            break;
        case 'pixelate':
            const pixelSize = parseInt(document.getElementById('filter_size').value);
            Filters.pixelate(imageData, pixelSize);
            break;
        case 'vignette':
            const vigAmount = parseInt(document.getElementById('filter_amount').value) / 100;
            const vigRadius = parseInt(document.getElementById('filter_radius').value) / 100;
            Filters.vignette(imageData, vigAmount, vigRadius);
            break;
    }
}

function applyCurrentFilter() {
    if (!filterPreviewData) return;

    const layer = editor.layerManager.getActiveLayer();
    layer.putImageData(filterPreviewData);

    const imageData = layer.getImageData();
    applyFilterToData(currentFilter, imageData);
    layer.putImageData(imageData);

    editor.saveState('Filter', 'filter');
    editor.render();

    filterPreviewData = null;
}

function applyFilter(type) {
    const layer = editor.layerManager.getActiveLayer();
    if (layer.locked) return;

    const imageData = layer.getImageData();

    switch (type) {
        case 'grayscale':
            Filters.grayscale(imageData);
            break;
        case 'sepia':
            Filters.sepia(imageData);
            break;
        case 'invert':
            Filters.invert(imageData);
            break;
        case 'sharpen':
            Filters.sharpen(imageData);
            break;
    }

    layer.putImageData(imageData);
    editor.saveState('Filter', 'filter');
    editor.render();
}

// Copy/Paste
let clipboard = null;

function copySelection() {
    const layer = editor.layerManager.getActiveLayer();
    const imageData = layer.getImageData();

    if (editor.selection.hasSelection()) {
        clipboard = editor.selection.getSelectedImageData(imageData);
        clipboard.bounds = { ...editor.selection.bounds };
    } else {
        clipboard = imageData;
        clipboard.bounds = { x: 0, y: 0, width: editor.width, height: editor.height };
    }

    document.getElementById('statusInfo').textContent = 'Copied to clipboard';
}

function pasteClipboard() {
    if (!clipboard) return;

    // Create new layer with pasted content
    const newLayer = editor.layerManager.addLayer('Pasted');
    newLayer.ctx.putImageData(clipboard, clipboard.bounds.x, clipboard.bounds.y);

    editor.saveState('Paste', 'paste');
    editor.render();
    editor.updateUI();
}

// Grid and rulers
let showGrid = false;
let showRulers = true;

function toggleGrid() {
    showGrid = !showGrid;
    // Implementation would draw grid on overlay
    document.getElementById('statusInfo').textContent = showGrid ? 'Grid: On' : 'Grid: Off';
}

function toggleRulers() {
    showRulers = !showRulers;
    document.getElementById('rulerH').style.display = showRulers ? 'block' : 'none';
    document.getElementById('rulerV').style.display = showRulers ? 'block' : 'none';
}

// Export global editor reference
window.editor = editor;
