// VE3 Image Editor - Utility Functions

const Utils = {
    // Generate unique ID
    generateId() {
        return 'id_' + Math.random().toString(36).substr(2, 9) + Date.now().toString(36);
    },

    // Clamp value between min and max
    clamp(value, min, max) {
        return Math.min(Math.max(value, min), max);
    },

    // Linear interpolation
    lerp(a, b, t) {
        return a + (b - a) * t;
    },

    // Distance between two points
    distance(x1, y1, x2, y2) {
        return Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
    },

    // Angle between two points
    angle(x1, y1, x2, y2) {
        return Math.atan2(y2 - y1, x2 - x1);
    },

    // Degrees to radians
    degToRad(degrees) {
        return degrees * (Math.PI / 180);
    },

    // Radians to degrees
    radToDeg(radians) {
        return radians * (180 / Math.PI);
    },

    // Deep clone object
    deepClone(obj) {
        if (obj === null || typeof obj !== 'object') return obj;
        if (obj instanceof Date) return new Date(obj);
        if (obj instanceof Array) return obj.map(item => this.deepClone(item));
        if (obj instanceof ImageData) {
            return new ImageData(
                new Uint8ClampedArray(obj.data),
                obj.width,
                obj.height
            );
        }
        const clone = {};
        for (const key in obj) {
            if (obj.hasOwnProperty(key)) {
                clone[key] = this.deepClone(obj[key]);
            }
        }
        return clone;
    },

    // Debounce function
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    // Throttle function
    throttle(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    },

    // Format file size
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    // Get mouse position relative to element
    getMousePos(canvas, evt) {
        const rect = canvas.getBoundingClientRect();
        return {
            x: evt.clientX - rect.left,
            y: evt.clientY - rect.top
        };
    },

    // Load image from URL or file
    loadImage(source) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => resolve(img);
            img.onerror = reject;
            if (source instanceof File) {
                const reader = new FileReader();
                reader.onload = (e) => {
                    img.src = e.target.result;
                };
                reader.readAsDataURL(source);
            } else {
                img.src = source;
            }
        });
    },

    // Create canvas with dimensions
    createCanvas(width, height) {
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        return canvas;
    },

    // Copy canvas
    copyCanvas(sourceCanvas) {
        const canvas = this.createCanvas(sourceCanvas.width, sourceCanvas.height);
        const ctx = canvas.getContext('2d');
        ctx.drawImage(sourceCanvas, 0, 0);
        return canvas;
    },

    // Get image data from canvas
    getImageData(canvas) {
        const ctx = canvas.getContext('2d');
        return ctx.getImageData(0, 0, canvas.width, canvas.height);
    },

    // Put image data to canvas
    putImageData(canvas, imageData) {
        const ctx = canvas.getContext('2d');
        ctx.putImageData(imageData, 0, 0);
    },

    // Download canvas as image
    downloadCanvas(canvas, filename, format = 'png', quality = 0.92) {
        const link = document.createElement('a');
        const mimeType = format === 'jpg' ? 'image/jpeg' : `image/${format}`;
        link.download = filename;
        link.href = canvas.toDataURL(mimeType, quality);
        link.click();
    },

    // Convert canvas to blob
    canvasToBlob(canvas, format = 'png', quality = 0.92) {
        return new Promise((resolve) => {
            const mimeType = format === 'jpg' ? 'image/jpeg' : `image/${format}`;
            canvas.toBlob(resolve, mimeType, quality);
        });
    },

    // Merge multiple canvases
    mergeCanvases(canvases, width, height) {
        const merged = this.createCanvas(width, height);
        const ctx = merged.getContext('2d');
        canvases.forEach(canvas => {
            ctx.drawImage(canvas, 0, 0);
        });
        return merged;
    },

    // Apply gaussian blur to image data
    gaussianBlur(imageData, radius) {
        const pixels = imageData.data;
        const width = imageData.width;
        const height = imageData.height;

        const kernel = this.createGaussianKernel(radius);
        const tempData = new Uint8ClampedArray(pixels);

        // Horizontal pass
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                let r = 0, g = 0, b = 0, a = 0, weight = 0;
                for (let i = -radius; i <= radius; i++) {
                    const px = Math.min(Math.max(x + i, 0), width - 1);
                    const idx = (y * width + px) * 4;
                    const w = kernel[i + radius];
                    r += pixels[idx] * w;
                    g += pixels[idx + 1] * w;
                    b += pixels[idx + 2] * w;
                    a += pixels[idx + 3] * w;
                    weight += w;
                }
                const idx = (y * width + x) * 4;
                tempData[idx] = r / weight;
                tempData[idx + 1] = g / weight;
                tempData[idx + 2] = b / weight;
                tempData[idx + 3] = a / weight;
            }
        }

        // Vertical pass
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                let r = 0, g = 0, b = 0, a = 0, weight = 0;
                for (let i = -radius; i <= radius; i++) {
                    const py = Math.min(Math.max(y + i, 0), height - 1);
                    const idx = (py * width + x) * 4;
                    const w = kernel[i + radius];
                    r += tempData[idx] * w;
                    g += tempData[idx + 1] * w;
                    b += tempData[idx + 2] * w;
                    a += tempData[idx + 3] * w;
                    weight += w;
                }
                const idx = (y * width + x) * 4;
                pixels[idx] = r / weight;
                pixels[idx + 1] = g / weight;
                pixels[idx + 2] = b / weight;
                pixels[idx + 3] = a / weight;
            }
        }

        return imageData;
    },

    // Create gaussian kernel
    createGaussianKernel(radius) {
        const sigma = radius / 3;
        const size = radius * 2 + 1;
        const kernel = new Array(size);
        let sum = 0;

        for (let i = 0; i < size; i++) {
            const x = i - radius;
            kernel[i] = Math.exp(-(x * x) / (2 * sigma * sigma));
            sum += kernel[i];
        }

        // Normalize
        for (let i = 0; i < size; i++) {
            kernel[i] /= sum;
        }

        return kernel;
    },

    // Convolution filter
    convolve(imageData, kernel, divisor = 1, offset = 0) {
        const pixels = imageData.data;
        const width = imageData.width;
        const height = imageData.height;
        const output = new Uint8ClampedArray(pixels);

        const kSize = Math.sqrt(kernel.length);
        const half = Math.floor(kSize / 2);

        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                let r = 0, g = 0, b = 0;

                for (let ky = 0; ky < kSize; ky++) {
                    for (let kx = 0; kx < kSize; kx++) {
                        const px = Math.min(Math.max(x + kx - half, 0), width - 1);
                        const py = Math.min(Math.max(y + ky - half, 0), height - 1);
                        const idx = (py * width + px) * 4;
                        const weight = kernel[ky * kSize + kx];

                        r += pixels[idx] * weight;
                        g += pixels[idx + 1] * weight;
                        b += pixels[idx + 2] * weight;
                    }
                }

                const idx = (y * width + x) * 4;
                output[idx] = this.clamp(r / divisor + offset, 0, 255);
                output[idx + 1] = this.clamp(g / divisor + offset, 0, 255);
                output[idx + 2] = this.clamp(b / divisor + offset, 0, 255);
            }
        }

        imageData.data.set(output);
        return imageData;
    },

    // Point in polygon test
    pointInPolygon(x, y, polygon) {
        let inside = false;
        for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
            const xi = polygon[i].x, yi = polygon[i].y;
            const xj = polygon[j].x, yj = polygon[j].y;

            if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) {
                inside = !inside;
            }
        }
        return inside;
    },

    // Point in rectangle test
    pointInRect(x, y, rect) {
        return x >= rect.x && x <= rect.x + rect.width &&
               y >= rect.y && y <= rect.y + rect.height;
    },

    // Point in ellipse test
    pointInEllipse(x, y, cx, cy, rx, ry) {
        return ((x - cx) ** 2) / (rx ** 2) + ((y - cy) ** 2) / (ry ** 2) <= 1;
    },

    // Bresenham line algorithm
    bresenhamLine(x0, y0, x1, y1) {
        const points = [];
        const dx = Math.abs(x1 - x0);
        const dy = Math.abs(y1 - y0);
        const sx = x0 < x1 ? 1 : -1;
        const sy = y0 < y1 ? 1 : -1;
        let err = dx - dy;

        while (true) {
            points.push({ x: x0, y: y0 });
            if (x0 === x1 && y0 === y1) break;
            const e2 = 2 * err;
            if (e2 > -dy) {
                err -= dy;
                x0 += sx;
            }
            if (e2 < dx) {
                err += dx;
                y0 += sy;
            }
        }
        return points;
    },

    // Flood fill algorithm
    floodFill(imageData, startX, startY, fillColor, tolerance = 0) {
        const pixels = imageData.data;
        const width = imageData.width;
        const height = imageData.height;

        startX = Math.floor(startX);
        startY = Math.floor(startY);

        const startIdx = (startY * width + startX) * 4;
        const startR = pixels[startIdx];
        const startG = pixels[startIdx + 1];
        const startB = pixels[startIdx + 2];
        const startA = pixels[startIdx + 3];

        const visited = new Set();
        const stack = [[startX, startY]];

        const colorMatch = (idx) => {
            return Math.abs(pixels[idx] - startR) <= tolerance &&
                   Math.abs(pixels[idx + 1] - startG) <= tolerance &&
                   Math.abs(pixels[idx + 2] - startB) <= tolerance &&
                   Math.abs(pixels[idx + 3] - startA) <= tolerance;
        };

        while (stack.length > 0) {
            const [x, y] = stack.pop();
            const key = `${x},${y}`;

            if (x < 0 || x >= width || y < 0 || y >= height) continue;
            if (visited.has(key)) continue;

            const idx = (y * width + x) * 4;
            if (!colorMatch(idx)) continue;

            visited.add(key);

            pixels[idx] = fillColor.r;
            pixels[idx + 1] = fillColor.g;
            pixels[idx + 2] = fillColor.b;
            pixels[idx + 3] = fillColor.a;

            stack.push([x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]);
        }

        return imageData;
    },

    // Magic wand selection
    magicWandSelect(imageData, startX, startY, tolerance = 32, contiguous = true) {
        const pixels = imageData.data;
        const width = imageData.width;
        const height = imageData.height;
        const mask = new Uint8Array(width * height);

        startX = Math.floor(startX);
        startY = Math.floor(startY);

        const startIdx = (startY * width + startX) * 4;
        const startR = pixels[startIdx];
        const startG = pixels[startIdx + 1];
        const startB = pixels[startIdx + 2];

        const colorMatch = (idx) => {
            return Math.abs(pixels[idx] - startR) <= tolerance &&
                   Math.abs(pixels[idx + 1] - startG) <= tolerance &&
                   Math.abs(pixels[idx + 2] - startB) <= tolerance;
        };

        if (contiguous) {
            const visited = new Set();
            const stack = [[startX, startY]];

            while (stack.length > 0) {
                const [x, y] = stack.pop();
                const key = `${x},${y}`;

                if (x < 0 || x >= width || y < 0 || y >= height) continue;
                if (visited.has(key)) continue;

                const idx = (y * width + x) * 4;
                if (!colorMatch(idx)) continue;

                visited.add(key);
                mask[y * width + x] = 255;

                stack.push([x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]);
            }
        } else {
            for (let i = 0; i < width * height; i++) {
                if (colorMatch(i * 4)) {
                    mask[i] = 255;
                }
            }
        }

        return mask;
    }
};

// Export for use in other modules
window.Utils = Utils;
