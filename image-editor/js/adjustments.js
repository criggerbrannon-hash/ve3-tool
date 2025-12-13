// VE3 Image Editor - Image Adjustments

const Adjustments = {
    // Brightness adjustment
    brightness(imageData, amount = 0) {
        const pixels = imageData.data;
        for (let i = 0; i < pixels.length; i += 4) {
            pixels[i] = Utils.clamp(pixels[i] + amount, 0, 255);
            pixels[i + 1] = Utils.clamp(pixels[i + 1] + amount, 0, 255);
            pixels[i + 2] = Utils.clamp(pixels[i + 2] + amount, 0, 255);
        }
        return imageData;
    },

    // Contrast adjustment
    contrast(imageData, amount = 0) {
        const pixels = imageData.data;
        const factor = (259 * (amount + 255)) / (255 * (259 - amount));

        for (let i = 0; i < pixels.length; i += 4) {
            pixels[i] = Utils.clamp(factor * (pixels[i] - 128) + 128, 0, 255);
            pixels[i + 1] = Utils.clamp(factor * (pixels[i + 1] - 128) + 128, 0, 255);
            pixels[i + 2] = Utils.clamp(factor * (pixels[i + 2] - 128) + 128, 0, 255);
        }
        return imageData;
    },

    // Combined brightness/contrast
    brightnessContrast(imageData, brightness = 0, contrast = 0) {
        this.brightness(imageData, brightness);
        this.contrast(imageData, contrast);
        return imageData;
    },

    // Exposure adjustment
    exposure(imageData, amount = 0) {
        const pixels = imageData.data;
        const factor = Math.pow(2, amount);

        for (let i = 0; i < pixels.length; i += 4) {
            pixels[i] = Utils.clamp(pixels[i] * factor, 0, 255);
            pixels[i + 1] = Utils.clamp(pixels[i + 1] * factor, 0, 255);
            pixels[i + 2] = Utils.clamp(pixels[i + 2] * factor, 0, 255);
        }
        return imageData;
    },

    // Gamma correction
    gamma(imageData, value = 1) {
        const pixels = imageData.data;
        const gammaCorrection = 1 / value;

        for (let i = 0; i < pixels.length; i += 4) {
            pixels[i] = Math.pow(pixels[i] / 255, gammaCorrection) * 255;
            pixels[i + 1] = Math.pow(pixels[i + 1] / 255, gammaCorrection) * 255;
            pixels[i + 2] = Math.pow(pixels[i + 2] / 255, gammaCorrection) * 255;
        }
        return imageData;
    },

    // Hue adjustment
    hue(imageData, amount = 0) {
        const pixels = imageData.data;

        for (let i = 0; i < pixels.length; i += 4) {
            const color = new Color(pixels[i], pixels[i + 1], pixels[i + 2]);
            const hsl = color.toHSL();
            hsl.h = (hsl.h + amount + 360) % 360;
            const newColor = Color.fromHSL(hsl.h, hsl.s, hsl.l);

            pixels[i] = newColor.r;
            pixels[i + 1] = newColor.g;
            pixels[i + 2] = newColor.b;
        }
        return imageData;
    },

    // Saturation adjustment
    saturation(imageData, amount = 0) {
        const pixels = imageData.data;
        const factor = 1 + amount / 100;

        for (let i = 0; i < pixels.length; i += 4) {
            const gray = 0.299 * pixels[i] + 0.587 * pixels[i + 1] + 0.114 * pixels[i + 2];

            pixels[i] = Utils.clamp(gray + factor * (pixels[i] - gray), 0, 255);
            pixels[i + 1] = Utils.clamp(gray + factor * (pixels[i + 1] - gray), 0, 255);
            pixels[i + 2] = Utils.clamp(gray + factor * (pixels[i + 2] - gray), 0, 255);
        }
        return imageData;
    },

    // Combined hue/saturation/lightness
    hueSaturationLightness(imageData, hue = 0, saturation = 0, lightness = 0) {
        const pixels = imageData.data;

        for (let i = 0; i < pixels.length; i += 4) {
            const color = new Color(pixels[i], pixels[i + 1], pixels[i + 2]);
            let hsl = color.toHSL();

            hsl.h = (hsl.h + hue + 360) % 360;
            hsl.s = Utils.clamp(hsl.s + saturation, 0, 100);
            hsl.l = Utils.clamp(hsl.l + lightness, 0, 100);

            const newColor = Color.fromHSL(hsl.h, hsl.s, hsl.l);
            pixels[i] = newColor.r;
            pixels[i + 1] = newColor.g;
            pixels[i + 2] = newColor.b;
        }
        return imageData;
    },

    // Vibrance adjustment (affects less saturated colors more)
    vibrance(imageData, amount = 0) {
        const pixels = imageData.data;
        const factor = amount / 100;

        for (let i = 0; i < pixels.length; i += 4) {
            const max = Math.max(pixels[i], pixels[i + 1], pixels[i + 2]);
            const avg = (pixels[i] + pixels[i + 1] + pixels[i + 2]) / 3;
            const saturation = (max - avg) / 127;
            const vibFactor = factor * (1 - saturation);

            pixels[i] = Utils.clamp(pixels[i] + (pixels[i] - avg) * vibFactor, 0, 255);
            pixels[i + 1] = Utils.clamp(pixels[i + 1] + (pixels[i + 1] - avg) * vibFactor, 0, 255);
            pixels[i + 2] = Utils.clamp(pixels[i + 2] + (pixels[i + 2] - avg) * vibFactor, 0, 255);
        }
        return imageData;
    },

    // Color balance
    colorBalance(imageData, shadows = {r: 0, g: 0, b: 0}, midtones = {r: 0, g: 0, b: 0}, highlights = {r: 0, g: 0, b: 0}) {
        const pixels = imageData.data;

        for (let i = 0; i < pixels.length; i += 4) {
            const r = pixels[i];
            const g = pixels[i + 1];
            const b = pixels[i + 2];
            const luminance = (r + g + b) / 3;

            // Calculate weights for shadows, midtones, highlights
            const shadowWeight = Math.pow(1 - luminance / 255, 2);
            const highlightWeight = Math.pow(luminance / 255, 2);
            const midtoneWeight = 1 - shadowWeight - highlightWeight;

            pixels[i] = Utils.clamp(r +
                shadows.r * shadowWeight +
                midtones.r * midtoneWeight +
                highlights.r * highlightWeight, 0, 255);
            pixels[i + 1] = Utils.clamp(g +
                shadows.g * shadowWeight +
                midtones.g * midtoneWeight +
                highlights.g * highlightWeight, 0, 255);
            pixels[i + 2] = Utils.clamp(b +
                shadows.b * shadowWeight +
                midtones.b * midtoneWeight +
                highlights.b * highlightWeight, 0, 255);
        }
        return imageData;
    },

    // Shadows/Highlights
    shadowsHighlights(imageData, shadows = 0, highlights = 0) {
        const pixels = imageData.data;

        for (let i = 0; i < pixels.length; i += 4) {
            const luminance = 0.299 * pixels[i] + 0.587 * pixels[i + 1] + 0.114 * pixels[i + 2];

            // Shadow adjustment (affects dark pixels)
            const shadowFactor = 1 - luminance / 255;
            const shadowAdjust = shadows * shadowFactor * shadowFactor;

            // Highlight adjustment (affects bright pixels)
            const highlightFactor = luminance / 255;
            const highlightAdjust = -highlights * highlightFactor * highlightFactor;

            const totalAdjust = shadowAdjust + highlightAdjust;

            pixels[i] = Utils.clamp(pixels[i] + totalAdjust, 0, 255);
            pixels[i + 1] = Utils.clamp(pixels[i + 1] + totalAdjust, 0, 255);
            pixels[i + 2] = Utils.clamp(pixels[i + 2] + totalAdjust, 0, 255);
        }
        return imageData;
    },

    // Levels adjustment
    levels(imageData, inputMin = 0, inputMax = 255, outputMin = 0, outputMax = 255, gamma = 1) {
        const pixels = imageData.data;
        const inputRange = inputMax - inputMin;
        const outputRange = outputMax - outputMin;

        for (let i = 0; i < pixels.length; i += 4) {
            for (let c = 0; c < 3; c++) {
                let value = pixels[i + c];

                // Input levels
                value = Utils.clamp((value - inputMin) / inputRange, 0, 1);

                // Gamma
                value = Math.pow(value, 1 / gamma);

                // Output levels
                value = value * outputRange + outputMin;

                pixels[i + c] = Utils.clamp(value, 0, 255);
            }
        }
        return imageData;
    },

    // Curves adjustment (using lookup table)
    curves(imageData, curvePoints) {
        // curvePoints is array of {x, y} from 0-255
        const lut = this.createCurveLUT(curvePoints);
        const pixels = imageData.data;

        for (let i = 0; i < pixels.length; i += 4) {
            pixels[i] = lut[pixels[i]];
            pixels[i + 1] = lut[pixels[i + 1]];
            pixels[i + 2] = lut[pixels[i + 2]];
        }
        return imageData;
    },

    // Create lookup table from curve points
    createCurveLUT(points) {
        const lut = new Uint8Array(256);

        // Sort points by x
        points.sort((a, b) => a.x - b.x);

        // Ensure we have endpoints
        if (points[0].x !== 0) {
            points.unshift({ x: 0, y: 0 });
        }
        if (points[points.length - 1].x !== 255) {
            points.push({ x: 255, y: 255 });
        }

        // Interpolate between points
        for (let i = 0; i < 256; i++) {
            // Find surrounding points
            let p1 = points[0];
            let p2 = points[points.length - 1];

            for (let j = 0; j < points.length - 1; j++) {
                if (i >= points[j].x && i <= points[j + 1].x) {
                    p1 = points[j];
                    p2 = points[j + 1];
                    break;
                }
            }

            // Linear interpolation
            const t = (i - p1.x) / (p2.x - p1.x || 1);
            lut[i] = Utils.clamp(Math.round(Utils.lerp(p1.y, p2.y, t)), 0, 255);
        }

        return lut;
    },

    // Channel curves (separate for R, G, B)
    channelCurves(imageData, redCurve, greenCurve, blueCurve) {
        const redLUT = redCurve ? this.createCurveLUT(redCurve) : null;
        const greenLUT = greenCurve ? this.createCurveLUT(greenCurve) : null;
        const blueLUT = blueCurve ? this.createCurveLUT(blueCurve) : null;
        const pixels = imageData.data;

        for (let i = 0; i < pixels.length; i += 4) {
            if (redLUT) pixels[i] = redLUT[pixels[i]];
            if (greenLUT) pixels[i + 1] = greenLUT[pixels[i + 1]];
            if (blueLUT) pixels[i + 2] = blueLUT[pixels[i + 2]];
        }
        return imageData;
    },

    // Auto levels
    autoLevels(imageData) {
        const pixels = imageData.data;

        // Find min/max for each channel
        let rMin = 255, rMax = 0;
        let gMin = 255, gMax = 0;
        let bMin = 255, bMax = 0;

        for (let i = 0; i < pixels.length; i += 4) {
            rMin = Math.min(rMin, pixels[i]);
            rMax = Math.max(rMax, pixels[i]);
            gMin = Math.min(gMin, pixels[i + 1]);
            gMax = Math.max(gMax, pixels[i + 1]);
            bMin = Math.min(bMin, pixels[i + 2]);
            bMax = Math.max(bMax, pixels[i + 2]);
        }

        // Stretch to full range
        const rRange = rMax - rMin || 1;
        const gRange = gMax - gMin || 1;
        const bRange = bMax - bMin || 1;

        for (let i = 0; i < pixels.length; i += 4) {
            pixels[i] = ((pixels[i] - rMin) / rRange) * 255;
            pixels[i + 1] = ((pixels[i + 1] - gMin) / gRange) * 255;
            pixels[i + 2] = ((pixels[i + 2] - bMin) / bRange) * 255;
        }
        return imageData;
    },

    // Auto contrast
    autoContrast(imageData) {
        const pixels = imageData.data;

        // Find min/max luminance
        let min = 255, max = 0;

        for (let i = 0; i < pixels.length; i += 4) {
            const lum = 0.299 * pixels[i] + 0.587 * pixels[i + 1] + 0.114 * pixels[i + 2];
            min = Math.min(min, lum);
            max = Math.max(max, lum);
        }

        // Stretch contrast
        const range = max - min || 1;

        for (let i = 0; i < pixels.length; i += 4) {
            pixels[i] = ((pixels[i] - min) / range) * 255;
            pixels[i + 1] = ((pixels[i + 1] - min) / range) * 255;
            pixels[i + 2] = ((pixels[i + 2] - min) / range) * 255;
        }
        return imageData;
    },

    // Auto color (white balance)
    autoColor(imageData) {
        const pixels = imageData.data;

        // Calculate average color
        let rSum = 0, gSum = 0, bSum = 0;
        const count = pixels.length / 4;

        for (let i = 0; i < pixels.length; i += 4) {
            rSum += pixels[i];
            gSum += pixels[i + 1];
            bSum += pixels[i + 2];
        }

        const rAvg = rSum / count;
        const gAvg = gSum / count;
        const bAvg = bSum / count;
        const gray = (rAvg + gAvg + bAvg) / 3;

        // Calculate correction factors
        const rFactor = gray / rAvg;
        const gFactor = gray / gAvg;
        const bFactor = gray / bAvg;

        for (let i = 0; i < pixels.length; i += 4) {
            pixels[i] = Utils.clamp(pixels[i] * rFactor, 0, 255);
            pixels[i + 1] = Utils.clamp(pixels[i + 1] * gFactor, 0, 255);
            pixels[i + 2] = Utils.clamp(pixels[i + 2] * bFactor, 0, 255);
        }
        return imageData;
    },

    // Equalize histogram
    equalize(imageData) {
        const pixels = imageData.data;
        const histogram = new Array(256).fill(0);
        const count = pixels.length / 4;

        // Build luminance histogram
        for (let i = 0; i < pixels.length; i += 4) {
            const lum = Math.round(0.299 * pixels[i] + 0.587 * pixels[i + 1] + 0.114 * pixels[i + 2]);
            histogram[lum]++;
        }

        // Calculate cumulative distribution
        const cdf = new Array(256);
        cdf[0] = histogram[0];
        for (let i = 1; i < 256; i++) {
            cdf[i] = cdf[i - 1] + histogram[i];
        }

        // Normalize CDF
        const cdfMin = cdf.find(v => v > 0);
        const lut = new Array(256);
        for (let i = 0; i < 256; i++) {
            lut[i] = Math.round((cdf[i] - cdfMin) / (count - cdfMin) * 255);
        }

        // Apply to image
        for (let i = 0; i < pixels.length; i += 4) {
            const lum = Math.round(0.299 * pixels[i] + 0.587 * pixels[i + 1] + 0.114 * pixels[i + 2]);
            const newLum = lut[lum];
            const factor = newLum / (lum || 1);

            pixels[i] = Utils.clamp(pixels[i] * factor, 0, 255);
            pixels[i + 1] = Utils.clamp(pixels[i + 1] * factor, 0, 255);
            pixels[i + 2] = Utils.clamp(pixels[i + 2] * factor, 0, 255);
        }
        return imageData;
    },

    // Apply adjustment to selection only
    applyToSelection(imageData, selection, adjustFn, ...args) {
        if (!selection || !selection.hasSelection()) {
            return adjustFn.call(this, imageData, ...args);
        }

        const width = imageData.width;
        const originalData = new Uint8ClampedArray(imageData.data);

        // Apply adjustment to entire image
        adjustFn.call(this, imageData, ...args);

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
window.Adjustments = Adjustments;
