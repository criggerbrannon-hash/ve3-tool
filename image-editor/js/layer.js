// VE3 Image Editor - Layer System

class Layer {
    constructor(width, height, name = 'Layer') {
        this.id = Utils.generateId();
        this.name = name;
        this.width = width;
        this.height = height;
        this.visible = true;
        this.locked = false;
        this.opacity = 100;
        this.blendMode = 'normal';
        this.x = 0;
        this.y = 0;

        // Create canvas for this layer
        this.canvas = Utils.createCanvas(width, height);
        this.ctx = this.canvas.getContext('2d');
    }

    // Clear layer
    clear() {
        this.ctx.clearRect(0, 0, this.width, this.height);
    }

    // Fill with color
    fill(color) {
        this.ctx.fillStyle = color instanceof Color ? color.toRGBA() : color;
        this.ctx.fillRect(0, 0, this.width, this.height);
    }

    // Get image data
    getImageData() {
        return this.ctx.getImageData(0, 0, this.width, this.height);
    }

    // Put image data
    putImageData(imageData) {
        this.ctx.putImageData(imageData, 0, 0);
    }

    // Draw image onto layer
    drawImage(image, x = 0, y = 0) {
        this.ctx.drawImage(image, x, y);
    }

    // Clone layer
    clone() {
        const cloned = new Layer(this.width, this.height, this.name + ' copy');
        cloned.visible = this.visible;
        cloned.locked = this.locked;
        cloned.opacity = this.opacity;
        cloned.blendMode = this.blendMode;
        cloned.ctx.drawImage(this.canvas, 0, 0);
        return cloned;
    }

    // Resize layer
    resize(newWidth, newHeight, resample = 'bilinear') {
        const tempCanvas = Utils.copyCanvas(this.canvas);
        this.canvas.width = newWidth;
        this.canvas.height = newHeight;
        this.width = newWidth;
        this.height = newHeight;

        if (resample === 'nearest') {
            this.ctx.imageSmoothingEnabled = false;
        } else {
            this.ctx.imageSmoothingEnabled = true;
            this.ctx.imageSmoothingQuality = resample === 'bicubic' ? 'high' : 'medium';
        }

        this.ctx.drawImage(tempCanvas, 0, 0, newWidth, newHeight);
    }

    // Get thumbnail
    getThumbnail(maxSize = 32) {
        const ratio = Math.min(maxSize / this.width, maxSize / this.height);
        const thumbWidth = Math.floor(this.width * ratio);
        const thumbHeight = Math.floor(this.height * ratio);

        const thumbnail = Utils.createCanvas(thumbWidth, thumbHeight);
        const thumbCtx = thumbnail.getContext('2d');
        thumbCtx.drawImage(this.canvas, 0, 0, thumbWidth, thumbHeight);

        return thumbnail;
    }

    // Merge with another layer
    mergeWith(otherLayer) {
        const tempCtx = this.ctx;
        tempCtx.globalAlpha = otherLayer.opacity / 100;
        tempCtx.globalCompositeOperation = this.getCompositeOperation(otherLayer.blendMode);
        tempCtx.drawImage(otherLayer.canvas, otherLayer.x, otherLayer.y);
        tempCtx.globalAlpha = 1;
        tempCtx.globalCompositeOperation = 'source-over';
    }

    // Get composite operation from blend mode
    getCompositeOperation(blendMode) {
        const blendModes = {
            'normal': 'source-over',
            'multiply': 'multiply',
            'screen': 'screen',
            'overlay': 'overlay',
            'darken': 'darken',
            'lighten': 'lighten',
            'color-dodge': 'color-dodge',
            'color-burn': 'color-burn',
            'hard-light': 'hard-light',
            'soft-light': 'soft-light',
            'difference': 'difference',
            'exclusion': 'exclusion',
            'hue': 'hue',
            'saturation': 'saturation',
            'color': 'color',
            'luminosity': 'luminosity'
        };
        return blendModes[blendMode] || 'source-over';
    }

    // Rotate layer
    rotate(degrees) {
        const radians = Utils.degToRad(degrees);
        const cos = Math.abs(Math.cos(radians));
        const sin = Math.abs(Math.sin(radians));

        const newWidth = Math.ceil(this.width * cos + this.height * sin);
        const newHeight = Math.ceil(this.width * sin + this.height * cos);

        const tempCanvas = Utils.copyCanvas(this.canvas);
        this.canvas.width = newWidth;
        this.canvas.height = newHeight;
        this.width = newWidth;
        this.height = newHeight;

        this.ctx.translate(newWidth / 2, newHeight / 2);
        this.ctx.rotate(radians);
        this.ctx.drawImage(tempCanvas, -tempCanvas.width / 2, -tempCanvas.height / 2);
        this.ctx.setTransform(1, 0, 0, 1, 0, 0);
    }

    // Flip horizontal
    flipHorizontal() {
        const tempCanvas = Utils.copyCanvas(this.canvas);
        this.ctx.clearRect(0, 0, this.width, this.height);
        this.ctx.scale(-1, 1);
        this.ctx.drawImage(tempCanvas, -this.width, 0);
        this.ctx.setTransform(1, 0, 0, 1, 0, 0);
    }

    // Flip vertical
    flipVertical() {
        const tempCanvas = Utils.copyCanvas(this.canvas);
        this.ctx.clearRect(0, 0, this.width, this.height);
        this.ctx.scale(1, -1);
        this.ctx.drawImage(tempCanvas, 0, -this.height);
        this.ctx.setTransform(1, 0, 0, 1, 0, 0);
    }

    // Serialize layer data
    serialize() {
        return {
            id: this.id,
            name: this.name,
            width: this.width,
            height: this.height,
            visible: this.visible,
            locked: this.locked,
            opacity: this.opacity,
            blendMode: this.blendMode,
            x: this.x,
            y: this.y,
            data: this.canvas.toDataURL()
        };
    }

    // Deserialize layer data
    static deserialize(data) {
        return new Promise((resolve) => {
            const layer = new Layer(data.width, data.height, data.name);
            layer.id = data.id;
            layer.visible = data.visible;
            layer.locked = data.locked;
            layer.opacity = data.opacity;
            layer.blendMode = data.blendMode;
            layer.x = data.x;
            layer.y = data.y;

            const img = new Image();
            img.onload = () => {
                layer.ctx.drawImage(img, 0, 0);
                resolve(layer);
            };
            img.src = data.data;
        });
    }
}

// Layer Manager
class LayerManager {
    constructor(width, height) {
        this.width = width;
        this.height = height;
        this.layers = [];
        this.activeLayerIndex = 0;
        this.listeners = [];

        // Create initial background layer
        this.addLayer('Background', true);
    }

    // Get active layer
    getActiveLayer() {
        return this.layers[this.activeLayerIndex];
    }

    // Set active layer by index
    setActiveLayer(index) {
        if (index >= 0 && index < this.layers.length) {
            this.activeLayerIndex = index;
            this.notifyListeners('activeChange');
        }
    }

    // Set active layer by id
    setActiveLayerById(id) {
        const index = this.layers.findIndex(l => l.id === id);
        if (index !== -1) {
            this.setActiveLayer(index);
        }
    }

    // Add new layer
    addLayer(name = 'Layer', isBackground = false) {
        const layer = new Layer(this.width, this.height, name || `Layer ${this.layers.length + 1}`);

        if (isBackground) {
            layer.fill('#ffffff');
        }

        this.layers.unshift(layer);
        this.activeLayerIndex = 0;
        this.notifyListeners('add');
        return layer;
    }

    // Remove layer
    removeLayer(index) {
        if (this.layers.length <= 1) return false;

        this.layers.splice(index, 1);

        if (this.activeLayerIndex >= this.layers.length) {
            this.activeLayerIndex = this.layers.length - 1;
        }

        this.notifyListeners('remove');
        return true;
    }

    // Duplicate layer
    duplicateLayer(index) {
        const original = this.layers[index];
        const duplicate = original.clone();
        this.layers.splice(index, 0, duplicate);
        this.activeLayerIndex = index;
        this.notifyListeners('duplicate');
        return duplicate;
    }

    // Move layer
    moveLayer(fromIndex, toIndex) {
        if (fromIndex < 0 || fromIndex >= this.layers.length) return;
        if (toIndex < 0 || toIndex >= this.layers.length) return;

        const [layer] = this.layers.splice(fromIndex, 1);
        this.layers.splice(toIndex, 0, layer);

        if (this.activeLayerIndex === fromIndex) {
            this.activeLayerIndex = toIndex;
        }

        this.notifyListeners('move');
    }

    // Merge layer down
    mergeDown(index) {
        if (index >= this.layers.length - 1) return false;

        const upperLayer = this.layers[index];
        const lowerLayer = this.layers[index + 1];

        lowerLayer.mergeWith(upperLayer);
        this.layers.splice(index, 1);

        if (this.activeLayerIndex >= index) {
            this.activeLayerIndex = Math.max(0, this.activeLayerIndex - 1);
        }

        this.notifyListeners('merge');
        return true;
    }

    // Merge all visible layers
    mergeVisible() {
        const merged = new Layer(this.width, this.height, 'Merged');
        const visibleLayers = this.layers.filter(l => l.visible).reverse();

        visibleLayers.forEach(layer => {
            merged.mergeWith(layer);
        });

        // Remove visible layers and add merged
        this.layers = this.layers.filter(l => !l.visible);
        this.layers.unshift(merged);
        this.activeLayerIndex = 0;

        this.notifyListeners('mergeVisible');
        return merged;
    }

    // Flatten image
    flatten() {
        const flattened = new Layer(this.width, this.height, 'Background');
        flattened.fill('#ffffff');

        [...this.layers].reverse().forEach(layer => {
            if (layer.visible) {
                flattened.mergeWith(layer);
            }
        });

        this.layers = [flattened];
        this.activeLayerIndex = 0;

        this.notifyListeners('flatten');
        return flattened;
    }

    // Render all layers to canvas
    render(targetCanvas) {
        const ctx = targetCanvas.getContext('2d');
        ctx.clearRect(0, 0, this.width, this.height);

        // Draw checkerboard pattern for transparency
        const pattern = this.createCheckerboardPattern(ctx);
        ctx.fillStyle = pattern;
        ctx.fillRect(0, 0, this.width, this.height);

        // Render layers from bottom to top
        for (let i = this.layers.length - 1; i >= 0; i--) {
            const layer = this.layers[i];
            if (!layer.visible) continue;

            ctx.globalAlpha = layer.opacity / 100;
            ctx.globalCompositeOperation = layer.getCompositeOperation(layer.blendMode);
            ctx.drawImage(layer.canvas, layer.x, layer.y);
        }

        ctx.globalAlpha = 1;
        ctx.globalCompositeOperation = 'source-over';
    }

    // Create checkerboard pattern for transparency
    createCheckerboardPattern(ctx) {
        const size = 10;
        const patternCanvas = Utils.createCanvas(size * 2, size * 2);
        const pCtx = patternCanvas.getContext('2d');

        pCtx.fillStyle = '#ffffff';
        pCtx.fillRect(0, 0, size * 2, size * 2);
        pCtx.fillStyle = '#cccccc';
        pCtx.fillRect(0, 0, size, size);
        pCtx.fillRect(size, size, size, size);

        return ctx.createPattern(patternCanvas, 'repeat');
    }

    // Resize all layers
    resize(newWidth, newHeight, resample = 'bilinear') {
        this.layers.forEach(layer => {
            layer.resize(newWidth, newHeight, resample);
        });
        this.width = newWidth;
        this.height = newHeight;
        this.notifyListeners('resize');
    }

    // Get flattened canvas
    getFlattenedCanvas() {
        const canvas = Utils.createCanvas(this.width, this.height);
        this.render(canvas);
        return canvas;
    }

    // Add listener
    addListener(callback) {
        this.listeners.push(callback);
    }

    // Remove listener
    removeListener(callback) {
        const index = this.listeners.indexOf(callback);
        if (index > -1) {
            this.listeners.splice(index, 1);
        }
    }

    // Notify listeners
    notifyListeners(type) {
        this.listeners.forEach(cb => cb(type, this));
    }

    // Serialize all layers
    serialize() {
        return {
            width: this.width,
            height: this.height,
            activeLayerIndex: this.activeLayerIndex,
            layers: this.layers.map(l => l.serialize())
        };
    }

    // Deserialize layers
    static async deserialize(data) {
        const manager = new LayerManager(data.width, data.height);
        manager.layers = [];

        for (const layerData of data.layers) {
            const layer = await Layer.deserialize(layerData);
            manager.layers.push(layer);
        }

        manager.activeLayerIndex = data.activeLayerIndex;
        return manager;
    }
}

// Export
window.Layer = Layer;
window.LayerManager = LayerManager;
