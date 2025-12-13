// VE3 Image Editor - History (Undo/Redo) System

class HistoryState {
    constructor(name, icon, layerData) {
        this.id = Utils.generateId();
        this.name = name;
        this.icon = icon;
        this.timestamp = Date.now();
        this.layerData = layerData;
    }
}

class HistoryManager {
    constructor(maxStates = 50) {
        this.states = [];
        this.currentIndex = -1;
        this.maxStates = maxStates;
        this.listeners = [];
        this.isUndoRedo = false;
    }

    // Push new state
    pushState(name, icon, layerManager) {
        if (this.isUndoRedo) return;

        // Remove any states after current index (clear redo history)
        if (this.currentIndex < this.states.length - 1) {
            this.states = this.states.slice(0, this.currentIndex + 1);
        }

        // Create snapshot of current layer state
        const layerData = this.createSnapshot(layerManager);
        const state = new HistoryState(name, icon, layerData);

        this.states.push(state);
        this.currentIndex = this.states.length - 1;

        // Remove oldest states if exceeding max
        while (this.states.length > this.maxStates) {
            this.states.shift();
            this.currentIndex--;
        }

        this.notifyListeners('push');
    }

    // Create snapshot of layer manager
    createSnapshot(layerManager) {
        return {
            width: layerManager.width,
            height: layerManager.height,
            activeLayerIndex: layerManager.activeLayerIndex,
            layers: layerManager.layers.map(layer => ({
                id: layer.id,
                name: layer.name,
                visible: layer.visible,
                locked: layer.locked,
                opacity: layer.opacity,
                blendMode: layer.blendMode,
                x: layer.x,
                y: layer.y,
                imageData: layer.getImageData()
            }))
        };
    }

    // Restore snapshot to layer manager
    restoreSnapshot(layerManager, snapshot) {
        layerManager.width = snapshot.width;
        layerManager.height = snapshot.height;
        layerManager.activeLayerIndex = snapshot.activeLayerIndex;

        layerManager.layers = snapshot.layers.map(layerSnapshot => {
            const layer = new Layer(snapshot.width, snapshot.height, layerSnapshot.name);
            layer.id = layerSnapshot.id;
            layer.visible = layerSnapshot.visible;
            layer.locked = layerSnapshot.locked;
            layer.opacity = layerSnapshot.opacity;
            layer.blendMode = layerSnapshot.blendMode;
            layer.x = layerSnapshot.x;
            layer.y = layerSnapshot.y;
            layer.putImageData(Utils.deepClone(layerSnapshot.imageData));
            return layer;
        });
    }

    // Check if can undo
    canUndo() {
        return this.currentIndex > 0;
    }

    // Check if can redo
    canRedo() {
        return this.currentIndex < this.states.length - 1;
    }

    // Undo
    undo(layerManager) {
        if (!this.canUndo()) return false;

        this.isUndoRedo = true;
        this.currentIndex--;
        this.restoreSnapshot(layerManager, this.states[this.currentIndex].layerData);
        this.isUndoRedo = false;

        this.notifyListeners('undo');
        return true;
    }

    // Redo
    redo(layerManager) {
        if (!this.canRedo()) return false;

        this.isUndoRedo = true;
        this.currentIndex++;
        this.restoreSnapshot(layerManager, this.states[this.currentIndex].layerData);
        this.isUndoRedo = false;

        this.notifyListeners('redo');
        return true;
    }

    // Go to specific state
    goToState(index, layerManager) {
        if (index < 0 || index >= this.states.length) return false;

        this.isUndoRedo = true;
        this.currentIndex = index;
        this.restoreSnapshot(layerManager, this.states[index].layerData);
        this.isUndoRedo = false;

        this.notifyListeners('goto');
        return true;
    }

    // Get current state
    getCurrentState() {
        return this.states[this.currentIndex];
    }

    // Get all states
    getStates() {
        return this.states;
    }

    // Clear history
    clear() {
        this.states = [];
        this.currentIndex = -1;
        this.notifyListeners('clear');
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
}

// History icons for different actions
const HistoryIcons = {
    'new': 'fa-file',
    'open': 'fa-folder-open',
    'brush': 'fa-paint-brush',
    'pencil': 'fa-pencil-alt',
    'eraser': 'fa-eraser',
    'fill': 'fa-fill-drip',
    'gradient': 'fa-palette',
    'text': 'fa-font',
    'shape': 'fa-shapes',
    'selection': 'fa-vector-square',
    'transform': 'fa-expand-arrows-alt',
    'filter': 'fa-magic',
    'adjustment': 'fa-sliders-h',
    'layer': 'fa-layer-group',
    'crop': 'fa-crop',
    'resize': 'fa-expand',
    'rotate': 'fa-redo',
    'flip': 'fa-arrows-alt-h',
    'paste': 'fa-paste',
    'cut': 'fa-cut',
    'clone': 'fa-stamp',
    'blur': 'fa-water',
    'sharpen': 'fa-bolt'
};

// Export
window.HistoryState = HistoryState;
window.HistoryManager = HistoryManager;
window.HistoryIcons = HistoryIcons;
