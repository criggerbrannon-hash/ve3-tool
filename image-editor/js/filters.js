// VE3 Image Editor - Image Filters

const Filters = {
    // Blur filter
    blur(imageData, radius = 5) {
        return Utils.gaussianBlur(imageData, Math.round(radius));
    },

    // Box blur (faster)
    boxBlur(imageData, radius = 5) {
        const pixels = imageData.data;
        const width = imageData.width;
        const height = imageData.height;
        const output = new Uint8ClampedArray(pixels);

        const size = radius * 2 + 1;
        const area = size * size;

        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                let r = 0, g = 0, b = 0, a = 0;

                for (let ky = -radius; ky <= radius; ky++) {
                    for (let kx = -radius; kx <= radius; kx++) {
                        const px = Utils.clamp(x + kx, 0, width - 1);
                        const py = Utils.clamp(y + ky, 0, height - 1);
                        const idx = (py * width + px) * 4;

                        r += pixels[idx];
                        g += pixels[idx + 1];
                        b += pixels[idx + 2];
                        a += pixels[idx + 3];
                    }
                }

                const idx = (y * width + x) * 4;
                output[idx] = r / area;
                output[idx + 1] = g / area;
                output[idx + 2] = b / area;
                output[idx + 3] = a / area;
            }
        }

        imageData.data.set(output);
        return imageData;
    },

    // Sharpen filter
    sharpen(imageData, amount = 1) {
        const kernel = [
            0, -amount, 0,
            -amount, 1 + 4 * amount, -amount,
            0, -amount, 0
        ];
        return Utils.convolve(imageData, kernel);
    },

    // Unsharp mask
    unsharpMask(imageData, amount = 1, radius = 1, threshold = 0) {
        const pixels = imageData.data;
        const width = imageData.width;
        const height = imageData.height;

        // Create blurred copy
        const blurredData = new ImageData(
            new Uint8ClampedArray(pixels),
            width,
            height
        );
        Utils.gaussianBlur(blurredData, radius);
        const blurred = blurredData.data;

        // Apply unsharp mask
        for (let i = 0; i < pixels.length; i += 4) {
            for (let c = 0; c < 3; c++) {
                const diff = pixels[i + c] - blurred[i + c];
                if (Math.abs(diff) > threshold) {
                    pixels[i + c] = Utils.clamp(pixels[i + c] + diff * amount, 0, 255);
                }
            }
        }

        return imageData;
    },

    // Edge detection (Sobel)
    edgeDetect(imageData) {
        const pixels = imageData.data;
        const width = imageData.width;
        const height = imageData.height;
        const output = new Uint8ClampedArray(pixels);

        const sobelX = [-1, 0, 1, -2, 0, 2, -1, 0, 1];
        const sobelY = [-1, -2, -1, 0, 0, 0, 1, 2, 1];

        for (let y = 1; y < height - 1; y++) {
            for (let x = 1; x < width - 1; x++) {
                let gx = 0, gy = 0;

                for (let ky = -1; ky <= 1; ky++) {
                    for (let kx = -1; kx <= 1; kx++) {
                        const idx = ((y + ky) * width + (x + kx)) * 4;
                        const gray = (pixels[idx] + pixels[idx + 1] + pixels[idx + 2]) / 3;
                        const ki = (ky + 1) * 3 + (kx + 1);
                        gx += gray * sobelX[ki];
                        gy += gray * sobelY[ki];
                    }
                }

                const magnitude = Math.min(255, Math.sqrt(gx * gx + gy * gy));
                const idx = (y * width + x) * 4;
                output[idx] = magnitude;
                output[idx + 1] = magnitude;
                output[idx + 2] = magnitude;
            }
        }

        imageData.data.set(output);
        return imageData;
    },

    // Emboss
    emboss(imageData, strength = 1) {
        const kernel = [
            -2 * strength, -strength, 0,
            -strength, 1, strength,
            0, strength, 2 * strength
        ];
        return Utils.convolve(imageData, kernel, 1, 128);
    },

    // Grayscale
    grayscale(imageData) {
        const pixels = imageData.data;
        for (let i = 0; i < pixels.length; i += 4) {
            const gray = 0.299 * pixels[i] + 0.587 * pixels[i + 1] + 0.114 * pixels[i + 2];
            pixels[i] = gray;
            pixels[i + 1] = gray;
            pixels[i + 2] = gray;
        }
        return imageData;
    },

    // Sepia
    sepia(imageData, amount = 100) {
        const pixels = imageData.data;
        const factor = amount / 100;

        for (let i = 0; i < pixels.length; i += 4) {
            const r = pixels[i];
            const g = pixels[i + 1];
            const b = pixels[i + 2];

            const sepiaR = Math.min(255, r * 0.393 + g * 0.769 + b * 0.189);
            const sepiaG = Math.min(255, r * 0.349 + g * 0.686 + b * 0.168);
            const sepiaB = Math.min(255, r * 0.272 + g * 0.534 + b * 0.131);

            pixels[i] = Utils.lerp(r, sepiaR, factor);
            pixels[i + 1] = Utils.lerp(g, sepiaG, factor);
            pixels[i + 2] = Utils.lerp(b, sepiaB, factor);
        }
        return imageData;
    },

    // Invert colors
    invert(imageData) {
        const pixels = imageData.data;
        for (let i = 0; i < pixels.length; i += 4) {
            pixels[i] = 255 - pixels[i];
            pixels[i + 1] = 255 - pixels[i + 1];
            pixels[i + 2] = 255 - pixels[i + 2];
        }
        return imageData;
    },

    // Posterize
    posterize(imageData, levels = 4) {
        const pixels = imageData.data;
        const step = 255 / (levels - 1);

        for (let i = 0; i < pixels.length; i += 4) {
            pixels[i] = Math.round(Math.round(pixels[i] / step) * step);
            pixels[i + 1] = Math.round(Math.round(pixels[i + 1] / step) * step);
            pixels[i + 2] = Math.round(Math.round(pixels[i + 2] / step) * step);
        }
        return imageData;
    },

    // Threshold
    threshold(imageData, level = 128) {
        const pixels = imageData.data;
        for (let i = 0; i < pixels.length; i += 4) {
            const gray = (pixels[i] + pixels[i + 1] + pixels[i + 2]) / 3;
            const value = gray >= level ? 255 : 0;
            pixels[i] = value;
            pixels[i + 1] = value;
            pixels[i + 2] = value;
        }
        return imageData;
    },

    // Add noise
    noise(imageData, amount = 25) {
        const pixels = imageData.data;
        for (let i = 0; i < pixels.length; i += 4) {
            const noise = (Math.random() - 0.5) * amount * 2;
            pixels[i] = Utils.clamp(pixels[i] + noise, 0, 255);
            pixels[i + 1] = Utils.clamp(pixels[i + 1] + noise, 0, 255);
            pixels[i + 2] = Utils.clamp(pixels[i + 2] + noise, 0, 255);
        }
        return imageData;
    },

    // Color noise
    colorNoise(imageData, amount = 25) {
        const pixels = imageData.data;
        for (let i = 0; i < pixels.length; i += 4) {
            pixels[i] = Utils.clamp(pixels[i] + (Math.random() - 0.5) * amount * 2, 0, 255);
            pixels[i + 1] = Utils.clamp(pixels[i + 1] + (Math.random() - 0.5) * amount * 2, 0, 255);
            pixels[i + 2] = Utils.clamp(pixels[i + 2] + (Math.random() - 0.5) * amount * 2, 0, 255);
        }
        return imageData;
    },

    // Pixelate
    pixelate(imageData, size = 10) {
        const pixels = imageData.data;
        const width = imageData.width;
        const height = imageData.height;

        for (let y = 0; y < height; y += size) {
            for (let x = 0; x < width; x += size) {
                // Get average color in block
                let r = 0, g = 0, b = 0, count = 0;

                for (let by = 0; by < size && y + by < height; by++) {
                    for (let bx = 0; bx < size && x + bx < width; bx++) {
                        const idx = ((y + by) * width + (x + bx)) * 4;
                        r += pixels[idx];
                        g += pixels[idx + 1];
                        b += pixels[idx + 2];
                        count++;
                    }
                }

                r = Math.round(r / count);
                g = Math.round(g / count);
                b = Math.round(b / count);

                // Fill block with average color
                for (let by = 0; by < size && y + by < height; by++) {
                    for (let bx = 0; bx < size && x + bx < width; bx++) {
                        const idx = ((y + by) * width + (x + bx)) * 4;
                        pixels[idx] = r;
                        pixels[idx + 1] = g;
                        pixels[idx + 2] = b;
                    }
                }
            }
        }
        return imageData;
    },

    // Vignette
    vignette(imageData, amount = 0.5, radius = 0.5) {
        const pixels = imageData.data;
        const width = imageData.width;
        const height = imageData.height;
        const cx = width / 2;
        const cy = height / 2;
        const maxDist = Math.sqrt(cx * cx + cy * cy);

        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                const idx = (y * width + x) * 4;
                const dist = Math.sqrt((x - cx) ** 2 + (y - cy) ** 2) / maxDist;
                const factor = 1 - Math.pow(dist / radius, 2) * amount;

                pixels[idx] = Utils.clamp(pixels[idx] * factor, 0, 255);
                pixels[idx + 1] = Utils.clamp(pixels[idx + 1] * factor, 0, 255);
                pixels[idx + 2] = Utils.clamp(pixels[idx + 2] * factor, 0, 255);
            }
        }
        return imageData;
    },

    // Oil painting effect
    oilPaint(imageData, radius = 4, levels = 20) {
        const pixels = imageData.data;
        const width = imageData.width;
        const height = imageData.height;
        const output = new Uint8ClampedArray(pixels);

        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                const intensityCount = new Array(levels).fill(0);
                const intensitySumR = new Array(levels).fill(0);
                const intensitySumG = new Array(levels).fill(0);
                const intensitySumB = new Array(levels).fill(0);

                for (let ky = -radius; ky <= radius; ky++) {
                    for (let kx = -radius; kx <= radius; kx++) {
                        const px = Utils.clamp(x + kx, 0, width - 1);
                        const py = Utils.clamp(y + ky, 0, height - 1);
                        const idx = (py * width + px) * 4;

                        const r = pixels[idx];
                        const g = pixels[idx + 1];
                        const b = pixels[idx + 2];
                        const intensity = Math.floor(((r + g + b) / 3) * levels / 256);

                        intensityCount[intensity]++;
                        intensitySumR[intensity] += r;
                        intensitySumG[intensity] += g;
                        intensitySumB[intensity] += b;
                    }
                }

                let maxCount = 0;
                let maxIndex = 0;
                for (let i = 0; i < levels; i++) {
                    if (intensityCount[i] > maxCount) {
                        maxCount = intensityCount[i];
                        maxIndex = i;
                    }
                }

                const idx = (y * width + x) * 4;
                output[idx] = intensitySumR[maxIndex] / maxCount;
                output[idx + 1] = intensitySumG[maxIndex] / maxCount;
                output[idx + 2] = intensitySumB[maxIndex] / maxCount;
            }
        }

        imageData.data.set(output);
        return imageData;
    },

    // Motion blur
    motionBlur(imageData, angle = 0, distance = 10) {
        const pixels = imageData.data;
        const width = imageData.width;
        const height = imageData.height;
        const output = new Uint8ClampedArray(pixels);

        const rad = Utils.degToRad(angle);
        const dx = Math.cos(rad);
        const dy = Math.sin(rad);

        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                let r = 0, g = 0, b = 0, a = 0, count = 0;

                for (let i = -distance; i <= distance; i++) {
                    const px = Math.round(x + dx * i);
                    const py = Math.round(y + dy * i);

                    if (px >= 0 && px < width && py >= 0 && py < height) {
                        const idx = (py * width + px) * 4;
                        r += pixels[idx];
                        g += pixels[idx + 1];
                        b += pixels[idx + 2];
                        a += pixels[idx + 3];
                        count++;
                    }
                }

                const idx = (y * width + x) * 4;
                output[idx] = r / count;
                output[idx + 1] = g / count;
                output[idx + 2] = b / count;
                output[idx + 3] = a / count;
            }
        }

        imageData.data.set(output);
        return imageData;
    },

    // Radial blur
    radialBlur(imageData, amount = 10, centerX = 0.5, centerY = 0.5) {
        const pixels = imageData.data;
        const width = imageData.width;
        const height = imageData.height;
        const output = new Uint8ClampedArray(pixels);

        const cx = width * centerX;
        const cy = height * centerY;

        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                const angle = Math.atan2(y - cy, x - cx);
                const dist = Math.sqrt((x - cx) ** 2 + (y - cy) ** 2);

                let r = 0, g = 0, b = 0, a = 0, count = 0;

                for (let i = -amount; i <= amount; i++) {
                    const newAngle = angle + (i / dist) * 0.1;
                    const px = Math.round(cx + Math.cos(newAngle) * dist);
                    const py = Math.round(cy + Math.sin(newAngle) * dist);

                    if (px >= 0 && px < width && py >= 0 && py < height) {
                        const idx = (py * width + px) * 4;
                        r += pixels[idx];
                        g += pixels[idx + 1];
                        b += pixels[idx + 2];
                        a += pixels[idx + 3];
                        count++;
                    }
                }

                if (count > 0) {
                    const idx = (y * width + x) * 4;
                    output[idx] = r / count;
                    output[idx + 1] = g / count;
                    output[idx + 2] = b / count;
                    output[idx + 3] = a / count;
                }
            }
        }

        imageData.data.set(output);
        return imageData;
    },

    // Color temperature
    colorTemperature(imageData, temperature = 0) {
        const pixels = imageData.data;
        const factor = temperature / 100;

        for (let i = 0; i < pixels.length; i += 4) {
            if (factor > 0) {
                // Warmer (more red/yellow)
                pixels[i] = Utils.clamp(pixels[i] + factor * 30, 0, 255);
                pixels[i + 2] = Utils.clamp(pixels[i + 2] - factor * 30, 0, 255);
            } else {
                // Cooler (more blue)
                pixels[i] = Utils.clamp(pixels[i] + factor * 30, 0, 255);
                pixels[i + 2] = Utils.clamp(pixels[i + 2] - factor * 30, 0, 255);
            }
        }
        return imageData;
    },

    // Duotone
    duotone(imageData, color1, color2) {
        const pixels = imageData.data;
        const c1 = color1 instanceof Color ? color1 : Color.fromHex(color1);
        const c2 = color2 instanceof Color ? color2 : Color.fromHex(color2);

        for (let i = 0; i < pixels.length; i += 4) {
            const gray = (pixels[i] + pixels[i + 1] + pixels[i + 2]) / 3 / 255;
            const blended = c1.blend(c2, gray);
            pixels[i] = blended.r;
            pixels[i + 1] = blended.g;
            pixels[i + 2] = blended.b;
        }
        return imageData;
    },

    // Channel mixer
    channelMix(imageData, matrix) {
        // matrix is 3x3: [rr, rg, rb, gr, gg, gb, br, bg, bb]
        const pixels = imageData.data;

        for (let i = 0; i < pixels.length; i += 4) {
            const r = pixels[i];
            const g = pixels[i + 1];
            const b = pixels[i + 2];

            pixels[i] = Utils.clamp(r * matrix[0] + g * matrix[1] + b * matrix[2], 0, 255);
            pixels[i + 1] = Utils.clamp(r * matrix[3] + g * matrix[4] + b * matrix[5], 0, 255);
            pixels[i + 2] = Utils.clamp(r * matrix[6] + g * matrix[7] + b * matrix[8], 0, 255);
        }
        return imageData;
    },

    // Solarize
    solarize(imageData, threshold = 128) {
        const pixels = imageData.data;
        for (let i = 0; i < pixels.length; i += 4) {
            if (pixels[i] > threshold) pixels[i] = 255 - pixels[i];
            if (pixels[i + 1] > threshold) pixels[i + 1] = 255 - pixels[i + 1];
            if (pixels[i + 2] > threshold) pixels[i + 2] = 255 - pixels[i + 2];
        }
        return imageData;
    },

    // Apply filter to selection only
    applyToSelection(imageData, selection, filterFn, ...args) {
        if (!selection || !selection.hasSelection()) {
            return filterFn(imageData, ...args);
        }

        const width = imageData.width;
        const height = imageData.height;
        const originalData = new Uint8ClampedArray(imageData.data);

        // Apply filter to entire image
        filterFn(imageData, ...args);

        // Blend based on selection mask
        const mask = selection.mask;
        const pixels = imageData.data;

        for (let i = 0; i < mask.length; i++) {
            const alpha = mask[i] / 255;
            const idx = i * 4;

            pixels[idx] = Utils.lerp(originalData[idx], pixels[idx], alpha);
            pixels[idx + 1] = Utils.lerp(originalData[idx + 1], pixels[idx + 1], alpha);
            pixels[idx + 2] = Utils.lerp(originalData[idx + 2], pixels[idx + 2], alpha);
        }

        return imageData;
    }
};

// Export
window.Filters = Filters;
