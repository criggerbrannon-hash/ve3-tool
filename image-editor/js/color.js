// VE3 Image Editor - Color Management

class Color {
    constructor(r = 0, g = 0, b = 0, a = 255) {
        this.r = r;
        this.g = g;
        this.b = b;
        this.a = a;
    }

    // Create from hex string
    static fromHex(hex) {
        hex = hex.replace('#', '');
        if (hex.length === 3) {
            hex = hex.split('').map(c => c + c).join('');
        }
        const r = parseInt(hex.substr(0, 2), 16);
        const g = parseInt(hex.substr(2, 2), 16);
        const b = parseInt(hex.substr(4, 2), 16);
        const a = hex.length === 8 ? parseInt(hex.substr(6, 2), 16) : 255;
        return new Color(r, g, b, a);
    }

    // Create from HSL
    static fromHSL(h, s, l, a = 255) {
        h = h / 360;
        s = s / 100;
        l = l / 100;

        let r, g, b;

        if (s === 0) {
            r = g = b = l;
        } else {
            const hue2rgb = (p, q, t) => {
                if (t < 0) t += 1;
                if (t > 1) t -= 1;
                if (t < 1/6) return p + (q - p) * 6 * t;
                if (t < 1/2) return q;
                if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
                return p;
            };

            const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
            const p = 2 * l - q;
            r = hue2rgb(p, q, h + 1/3);
            g = hue2rgb(p, q, h);
            b = hue2rgb(p, q, h - 1/3);
        }

        return new Color(
            Math.round(r * 255),
            Math.round(g * 255),
            Math.round(b * 255),
            a
        );
    }

    // Create from HSV/HSB
    static fromHSV(h, s, v, a = 255) {
        h = h / 360;
        s = s / 100;
        v = v / 100;

        let r, g, b;
        const i = Math.floor(h * 6);
        const f = h * 6 - i;
        const p = v * (1 - s);
        const q = v * (1 - f * s);
        const t = v * (1 - (1 - f) * s);

        switch (i % 6) {
            case 0: r = v; g = t; b = p; break;
            case 1: r = q; g = v; b = p; break;
            case 2: r = p; g = v; b = t; break;
            case 3: r = p; g = q; b = v; break;
            case 4: r = t; g = p; b = v; break;
            case 5: r = v; g = p; b = q; break;
        }

        return new Color(
            Math.round(r * 255),
            Math.round(g * 255),
            Math.round(b * 255),
            a
        );
    }

    // To hex string
    toHex(includeAlpha = false) {
        const hex = [this.r, this.g, this.b]
            .map(c => c.toString(16).padStart(2, '0'))
            .join('');
        if (includeAlpha) {
            return hex + this.a.toString(16).padStart(2, '0');
        }
        return hex;
    }

    // To HSL
    toHSL() {
        const r = this.r / 255;
        const g = this.g / 255;
        const b = this.b / 255;

        const max = Math.max(r, g, b);
        const min = Math.min(r, g, b);
        let h, s;
        const l = (max + min) / 2;

        if (max === min) {
            h = s = 0;
        } else {
            const d = max - min;
            s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
            switch (max) {
                case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
                case g: h = ((b - r) / d + 2) / 6; break;
                case b: h = ((r - g) / d + 4) / 6; break;
            }
        }

        return {
            h: Math.round(h * 360),
            s: Math.round(s * 100),
            l: Math.round(l * 100)
        };
    }

    // To HSV/HSB
    toHSV() {
        const r = this.r / 255;
        const g = this.g / 255;
        const b = this.b / 255;

        const max = Math.max(r, g, b);
        const min = Math.min(r, g, b);
        const d = max - min;

        let h, s;
        const v = max;

        s = max === 0 ? 0 : d / max;

        if (max === min) {
            h = 0;
        } else {
            switch (max) {
                case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
                case g: h = ((b - r) / d + 2) / 6; break;
                case b: h = ((r - g) / d + 4) / 6; break;
            }
        }

        return {
            h: Math.round(h * 360),
            s: Math.round(s * 100),
            v: Math.round(v * 100)
        };
    }

    // To RGBA string
    toRGBA() {
        return `rgba(${this.r}, ${this.g}, ${this.b}, ${this.a / 255})`;
    }

    // To RGB string
    toRGB() {
        return `rgb(${this.r}, ${this.g}, ${this.b})`;
    }

    // Clone color
    clone() {
        return new Color(this.r, this.g, this.b, this.a);
    }

    // Check if equal
    equals(color) {
        return this.r === color.r && this.g === color.g &&
               this.b === color.b && this.a === color.a;
    }

    // Blend with another color
    blend(color, amount) {
        return new Color(
            Math.round(Utils.lerp(this.r, color.r, amount)),
            Math.round(Utils.lerp(this.g, color.g, amount)),
            Math.round(Utils.lerp(this.b, color.b, amount)),
            Math.round(Utils.lerp(this.a, color.a, amount))
        );
    }

    // Lighten
    lighten(amount) {
        const hsl = this.toHSL();
        hsl.l = Math.min(100, hsl.l + amount);
        return Color.fromHSL(hsl.h, hsl.s, hsl.l, this.a);
    }

    // Darken
    darken(amount) {
        const hsl = this.toHSL();
        hsl.l = Math.max(0, hsl.l - amount);
        return Color.fromHSL(hsl.h, hsl.s, hsl.l, this.a);
    }

    // Saturate
    saturate(amount) {
        const hsl = this.toHSL();
        hsl.s = Math.min(100, hsl.s + amount);
        return Color.fromHSL(hsl.h, hsl.s, hsl.l, this.a);
    }

    // Desaturate
    desaturate(amount) {
        const hsl = this.toHSL();
        hsl.s = Math.max(0, hsl.s - amount);
        return Color.fromHSL(hsl.h, hsl.s, hsl.l, this.a);
    }

    // Invert
    invert() {
        return new Color(255 - this.r, 255 - this.g, 255 - this.b, this.a);
    }

    // Grayscale
    grayscale() {
        const gray = Math.round(0.299 * this.r + 0.587 * this.g + 0.114 * this.b);
        return new Color(gray, gray, gray, this.a);
    }

    // Get luminance
    getLuminance() {
        const a = [this.r, this.g, this.b].map(v => {
            v /= 255;
            return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        });
        return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722;
    }

    // Check if light or dark
    isLight() {
        return this.getLuminance() > 0.5;
    }
}

// Color Manager for managing foreground/background colors
class ColorManager {
    constructor() {
        this.foreground = new Color(0, 0, 0, 255);
        this.background = new Color(255, 255, 255, 255);
        this.history = [];
        this.maxHistory = 50;
        this.listeners = [];
    }

    // Set foreground color
    setForeground(color) {
        this.addToHistory(this.foreground);
        this.foreground = color instanceof Color ? color : Color.fromHex(color);
        this.notifyListeners('foreground');
    }

    // Set background color
    setBackground(color) {
        this.addToHistory(this.background);
        this.background = color instanceof Color ? color : Color.fromHex(color);
        this.notifyListeners('background');
    }

    // Swap colors
    swap() {
        const temp = this.foreground;
        this.foreground = this.background;
        this.background = temp;
        this.notifyListeners('swap');
    }

    // Reset to default
    reset() {
        this.foreground = new Color(0, 0, 0, 255);
        this.background = new Color(255, 255, 255, 255);
        this.notifyListeners('reset');
    }

    // Add color to history
    addToHistory(color) {
        if (!this.history.some(c => c.equals(color))) {
            this.history.unshift(color.clone());
            if (this.history.length > this.maxHistory) {
                this.history.pop();
            }
        }
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
        this.listeners.forEach(cb => cb(type, this.foreground, this.background));
    }
}

// Default color swatches
const DEFAULT_SWATCHES = [
    '#000000', '#ffffff', '#ff0000', '#00ff00', '#0000ff',
    '#ffff00', '#00ffff', '#ff00ff', '#ff8000', '#8000ff',
    '#0080ff', '#ff0080', '#80ff00', '#00ff80', '#800000',
    '#008000', '#000080', '#808000', '#008080', '#800080',
    '#ff8080', '#80ff80', '#8080ff', '#ffff80', '#80ffff',
    '#ff80ff', '#c0c0c0', '#808080', '#404040', '#202020',
    '#ffc0c0', '#c0ffc0', '#c0c0ff', '#ffffc0', '#c0ffff',
    '#ffc0ff', '#e0e0e0', '#a0a0a0', '#606060', '#303030'
];

// Export
window.Color = Color;
window.ColorManager = ColorManager;
window.DEFAULT_SWATCHES = DEFAULT_SWATCHES;
