// VE3 Image Editor - Selection System

class Selection {
    constructor(width, height) {
        this.width = width;
        this.height = height;
        this.mask = null;
        this.bounds = null;
        this.feather = 0;
        this.active = false;
        this.type = null; // 'rect', 'ellipse', 'lasso', 'wand'
    }

    // Check if selection exists
    hasSelection() {
        return this.active && this.mask !== null;
    }

    // Create rectangular selection
    createRect(x, y, width, height) {
        this.mask = new Uint8Array(this.width * this.height);
        this.type = 'rect';

        const x1 = Math.max(0, Math.floor(Math.min(x, x + width)));
        const y1 = Math.max(0, Math.floor(Math.min(y, y + height)));
        const x2 = Math.min(this.width, Math.ceil(Math.max(x, x + width)));
        const y2 = Math.min(this.height, Math.ceil(Math.max(y, y + height)));

        for (let py = y1; py < y2; py++) {
            for (let px = x1; px < x2; px++) {
                this.mask[py * this.width + px] = 255;
            }
        }

        this.bounds = { x: x1, y: y1, width: x2 - x1, height: y2 - y1 };
        this.active = true;

        if (this.feather > 0) {
            this.applyFeather();
        }
    }

    // Create elliptical selection
    createEllipse(cx, cy, rx, ry) {
        this.mask = new Uint8Array(this.width * this.height);
        this.type = 'ellipse';

        const x1 = Math.max(0, Math.floor(cx - rx));
        const y1 = Math.max(0, Math.floor(cy - ry));
        const x2 = Math.min(this.width, Math.ceil(cx + rx));
        const y2 = Math.min(this.height, Math.ceil(cy + ry));

        for (let py = y1; py < y2; py++) {
            for (let px = x1; px < x2; px++) {
                if (Utils.pointInEllipse(px, py, cx, cy, rx, ry)) {
                    this.mask[py * this.width + px] = 255;
                }
            }
        }

        this.bounds = { x: x1, y: y1, width: x2 - x1, height: y2 - y1 };
        this.active = true;

        if (this.feather > 0) {
            this.applyFeather();
        }
    }

    // Create lasso (freeform) selection
    createLasso(points) {
        if (points.length < 3) return;

        this.mask = new Uint8Array(this.width * this.height);
        this.type = 'lasso';

        // Find bounds
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        points.forEach(p => {
            minX = Math.min(minX, p.x);
            minY = Math.min(minY, p.y);
            maxX = Math.max(maxX, p.x);
            maxY = Math.max(maxY, p.y);
        });

        minX = Math.max(0, Math.floor(minX));
        minY = Math.max(0, Math.floor(minY));
        maxX = Math.min(this.width, Math.ceil(maxX));
        maxY = Math.min(this.height, Math.ceil(maxY));

        // Fill polygon
        for (let py = minY; py < maxY; py++) {
            for (let px = minX; px < maxX; px++) {
                if (Utils.pointInPolygon(px, py, points)) {
                    this.mask[py * this.width + px] = 255;
                }
            }
        }

        this.bounds = { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
        this.active = true;

        if (this.feather > 0) {
            this.applyFeather();
        }
    }

    // Create magic wand selection
    createMagicWand(imageData, startX, startY, tolerance, contiguous) {
        this.mask = Utils.magicWandSelect(imageData, startX, startY, tolerance, contiguous);
        this.type = 'wand';

        // Calculate bounds
        let minX = this.width, minY = this.height, maxX = 0, maxY = 0;
        for (let y = 0; y < this.height; y++) {
            for (let x = 0; x < this.width; x++) {
                if (this.mask[y * this.width + x] > 0) {
                    minX = Math.min(minX, x);
                    minY = Math.min(minY, y);
                    maxX = Math.max(maxX, x);
                    maxY = Math.max(maxY, y);
                }
            }
        }

        if (maxX >= minX && maxY >= minY) {
            this.bounds = { x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1 };
            this.active = true;
        }

        if (this.feather > 0) {
            this.applyFeather();
        }
    }

    // Select all
    selectAll() {
        this.mask = new Uint8Array(this.width * this.height).fill(255);
        this.bounds = { x: 0, y: 0, width: this.width, height: this.height };
        this.type = 'all';
        this.active = true;
    }

    // Deselect
    deselect() {
        this.mask = null;
        this.bounds = null;
        this.type = null;
        this.active = false;
    }

    // Inverse selection
    inverse() {
        if (!this.mask) return;

        for (let i = 0; i < this.mask.length; i++) {
            this.mask[i] = 255 - this.mask[i];
        }

        this.bounds = { x: 0, y: 0, width: this.width, height: this.height };
    }

    // Apply feather (blur) to selection mask
    applyFeather() {
        if (!this.mask || this.feather <= 0) return;

        // Convert mask to float for better precision
        const floatMask = new Float32Array(this.mask);

        // Apply gaussian blur
        const kernel = Utils.createGaussianKernel(this.feather);

        // Horizontal pass
        const temp = new Float32Array(this.width * this.height);
        for (let y = 0; y < this.height; y++) {
            for (let x = 0; x < this.width; x++) {
                let sum = 0, weight = 0;
                for (let i = -this.feather; i <= this.feather; i++) {
                    const px = Utils.clamp(x + i, 0, this.width - 1);
                    const w = kernel[i + this.feather];
                    sum += floatMask[y * this.width + px] * w;
                    weight += w;
                }
                temp[y * this.width + x] = sum / weight;
            }
        }

        // Vertical pass
        for (let y = 0; y < this.height; y++) {
            for (let x = 0; x < this.width; x++) {
                let sum = 0, weight = 0;
                for (let i = -this.feather; i <= this.feather; i++) {
                    const py = Utils.clamp(y + i, 0, this.height - 1);
                    const w = kernel[i + this.feather];
                    sum += temp[py * this.width + x] * w;
                    weight += w;
                }
                this.mask[y * this.width + x] = Utils.clamp(Math.round(sum / weight), 0, 255);
            }
        }
    }

    // Set feather amount
    setFeather(amount) {
        this.feather = amount;
    }

    // Add to selection
    add(otherSelection) {
        if (!otherSelection.mask) return;

        if (!this.mask) {
            this.mask = new Uint8Array(otherSelection.mask);
            this.bounds = { ...otherSelection.bounds };
            this.active = true;
            return;
        }

        for (let i = 0; i < this.mask.length; i++) {
            this.mask[i] = Math.max(this.mask[i], otherSelection.mask[i]);
        }

        this.updateBounds();
    }

    // Subtract from selection
    subtract(otherSelection) {
        if (!this.mask || !otherSelection.mask) return;

        for (let i = 0; i < this.mask.length; i++) {
            this.mask[i] = Math.max(0, this.mask[i] - otherSelection.mask[i]);
        }

        this.updateBounds();
    }

    // Intersect with selection
    intersect(otherSelection) {
        if (!this.mask || !otherSelection.mask) return;

        for (let i = 0; i < this.mask.length; i++) {
            this.mask[i] = Math.min(this.mask[i], otherSelection.mask[i]);
        }

        this.updateBounds();
    }

    // Update bounds based on mask
    updateBounds() {
        if (!this.mask) {
            this.bounds = null;
            return;
        }

        let minX = this.width, minY = this.height, maxX = 0, maxY = 0;
        let hasSelection = false;

        for (let y = 0; y < this.height; y++) {
            for (let x = 0; x < this.width; x++) {
                if (this.mask[y * this.width + x] > 0) {
                    minX = Math.min(minX, x);
                    minY = Math.min(minY, y);
                    maxX = Math.max(maxX, x);
                    maxY = Math.max(maxY, y);
                    hasSelection = true;
                }
            }
        }

        if (hasSelection) {
            this.bounds = { x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1 };
        } else {
            this.bounds = null;
            this.active = false;
        }
    }

    // Check if point is in selection
    containsPoint(x, y) {
        if (!this.mask) return true; // No selection means all selected
        x = Math.floor(x);
        y = Math.floor(y);
        if (x < 0 || x >= this.width || y < 0 || y >= this.height) return false;
        return this.mask[y * this.width + x] > 0;
    }

    // Get mask value at point
    getMaskValue(x, y) {
        if (!this.mask) return 255;
        x = Math.floor(x);
        y = Math.floor(y);
        if (x < 0 || x >= this.width || y < 0 || y >= this.height) return 0;
        return this.mask[y * this.width + x];
    }

    // Apply selection mask to image data
    applyToImageData(imageData) {
        if (!this.mask) return imageData;

        const pixels = imageData.data;
        for (let i = 0; i < this.mask.length; i++) {
            const alpha = this.mask[i] / 255;
            pixels[i * 4 + 3] = Math.round(pixels[i * 4 + 3] * alpha);
        }

        return imageData;
    }

    // Get selected region as image data
    getSelectedImageData(sourceImageData) {
        if (!this.mask || !this.bounds) return null;

        const { x, y, width, height } = this.bounds;
        const result = new ImageData(width, height);
        const srcPixels = sourceImageData.data;
        const dstPixels = result.data;

        for (let dy = 0; dy < height; dy++) {
            for (let dx = 0; dx < width; dx++) {
                const srcX = x + dx;
                const srcY = y + dy;
                const srcIdx = (srcY * this.width + srcX) * 4;
                const dstIdx = (dy * width + dx) * 4;
                const alpha = this.mask[srcY * this.width + srcX] / 255;

                dstPixels[dstIdx] = srcPixels[srcIdx];
                dstPixels[dstIdx + 1] = srcPixels[srcIdx + 1];
                dstPixels[dstIdx + 2] = srcPixels[srcIdx + 2];
                dstPixels[dstIdx + 3] = Math.round(srcPixels[srcIdx + 3] * alpha);
            }
        }

        return result;
    }

    // Draw marching ants on canvas
    drawMarchingAnts(ctx, offset = 0) {
        if (!this.mask) return;

        ctx.save();
        ctx.strokeStyle = '#000';
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.lineDashOffset = offset;

        // Create path from mask edges
        const path = this.createEdgePath();
        if (path.length > 0) {
            ctx.beginPath();
            path.forEach((segment, i) => {
                if (i === 0) {
                    ctx.moveTo(segment.x, segment.y);
                } else {
                    ctx.lineTo(segment.x, segment.y);
                }
            });
            ctx.stroke();

            // Draw white underneath
            ctx.strokeStyle = '#fff';
            ctx.lineDashOffset = offset + 4;
            ctx.beginPath();
            path.forEach((segment, i) => {
                if (i === 0) {
                    ctx.moveTo(segment.x, segment.y);
                } else {
                    ctx.lineTo(segment.x, segment.y);
                }
            });
            ctx.stroke();
        }

        ctx.restore();
    }

    // Create edge path from mask (simplified)
    createEdgePath() {
        if (!this.mask || !this.bounds) return [];

        const path = [];
        const { x: bx, y: by, width: bw, height: bh } = this.bounds;

        // Simple edge detection - find boundary pixels
        for (let y = by; y < by + bh; y++) {
            for (let x = bx; x < bx + bw; x++) {
                const idx = y * this.width + x;
                if (this.mask[idx] > 127) {
                    // Check if this is an edge pixel
                    const left = x > 0 ? this.mask[idx - 1] : 0;
                    const right = x < this.width - 1 ? this.mask[idx + 1] : 0;
                    const top = y > 0 ? this.mask[idx - this.width] : 0;
                    const bottom = y < this.height - 1 ? this.mask[idx + this.width] : 0;

                    if (left < 128 || right < 128 || top < 128 || bottom < 128) {
                        path.push({ x, y });
                    }
                }
            }
        }

        return path;
    }

    // Clone selection
    clone() {
        const cloned = new Selection(this.width, this.height);
        if (this.mask) {
            cloned.mask = new Uint8Array(this.mask);
        }
        if (this.bounds) {
            cloned.bounds = { ...this.bounds };
        }
        cloned.feather = this.feather;
        cloned.active = this.active;
        cloned.type = this.type;
        return cloned;
    }

    // Resize selection
    resize(newWidth, newHeight) {
        if (!this.mask) {
            this.width = newWidth;
            this.height = newHeight;
            return;
        }

        const newMask = new Uint8Array(newWidth * newHeight);
        const scaleX = this.width / newWidth;
        const scaleY = this.height / newHeight;

        for (let y = 0; y < newHeight; y++) {
            for (let x = 0; x < newWidth; x++) {
                const srcX = Math.floor(x * scaleX);
                const srcY = Math.floor(y * scaleY);
                newMask[y * newWidth + x] = this.mask[srcY * this.width + srcX];
            }
        }

        this.mask = newMask;
        this.width = newWidth;
        this.height = newHeight;
        this.updateBounds();
    }
}

// Export
window.Selection = Selection;
