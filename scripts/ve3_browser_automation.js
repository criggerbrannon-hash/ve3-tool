/**
 * VE3 Browser Automation - Google Flow Image Generator
 * =====================================================
 * Script chay tren Console cua trinh duyet de tu dong tao anh tren Google Flow.
 *
 * HUONG DAN SU DUNG:
 * 1. Mo trang: https://labs.google/fx/vi/tools/flow
 * 2. Nhan F12 -> Console
 * 3. Copy toan bo noi dung file nay vao Console va nhan Enter
 * 4. Goi cac ham: VE3.generateOne("prompt") hoac VE3.generateBatch(["p1", "p2"])
 *
 * @version 2.0.0
 * @author VE3 Tool
 */

(function() {
    'use strict';

    // =========================================================================
    // CONFIGURATION
    // =========================================================================

    const CONFIG = {
        // Retry settings
        maxRetries: 3,
        retryDelayBase: 3000,      // 3 giay, se tang dan (exponential backoff)
        retryDelayMax: 15000,      // Toi da 15 giay

        // Timeout settings
        generateTimeout: 90000,    // 90 giay cho moi anh
        uiActionDelay: 500,        // Delay giua cac thao tac UI

        // Batch settings
        delayBetweenImages: 2000,  // 2 giay giua cac anh

        // Selectors - Cap nhat theo UI cua Google Flow
        selectors: {
            textarea: 'textarea',
            generateButton: [
                'button:has(.google-symbols):has-text("Tao")',
                'button[aria-label*="Send"]',
                'button[aria-label*="Gui"]',
                'button[type="submit"]'
            ],
            newProjectButton: [
                'button:contains("Du an moi")',
                'button:contains("New project")'
            ],
            dropdown: 'button[role="combobox"]',
            imageOption: [
                '[role="option"]:contains("Tao hinh anh")',
                '[role="option"]:contains("Generate image")',
                '[role="menuitem"]:contains("Tao hinh anh")'
            ]
        },

        // Debug mode
        debug: false
    };

    // =========================================================================
    // UTILITIES
    // =========================================================================

    const Utils = {
        /**
         * Sleep/delay function
         */
        sleep: (ms) => new Promise(resolve => setTimeout(resolve, ms)),

        /**
         * Log voi icon va timestamp
         */
        log: (msg, type = 'info') => {
            const icons = {
                info: '\u2139\ufe0f',
                success: '\u2705',
                error: '\u274c',
                warn: '\u26a0\ufe0f',
                wait: '\u23f3',
                debug: '\ud83d\udd0d'
            };
            const icon = icons[type] || '\u2022';
            const timestamp = new Date().toLocaleTimeString();
            console.log(`${icon} [${timestamp}] [VE3] ${msg}`);
        },

        /**
         * Log debug (chi hien khi CONFIG.debug = true)
         */
        debug: (msg) => {
            if (CONFIG.debug) {
                Utils.log(msg, 'debug');
            }
        },

        /**
         * Tim element theo nhieu selectors (tra ve element dau tien tim thay)
         */
        findElement: (selectors) => {
            const selectorList = Array.isArray(selectors) ? selectors : [selectors];

            for (const selector of selectorList) {
                try {
                    // Xu ly selector dac biet :contains() va :has-text()
                    if (selector.includes(':contains(') || selector.includes(':has-text(')) {
                        const match = selector.match(/:(?:contains|has-text)\("([^"]+)"\)/);
                        if (match) {
                            const text = match[1];
                            const baseSelector = selector.replace(/:(?:contains|has-text)\("[^"]+"\)/, '');
                            const elements = document.querySelectorAll(baseSelector || '*');

                            for (const el of elements) {
                                if (el.textContent && el.textContent.includes(text)) {
                                    return el;
                                }
                            }
                        }
                        continue;
                    }

                    // Selector binh thuong
                    const el = document.querySelector(selector);
                    if (el) {
                        Utils.debug(`Found element with selector: ${selector}`);
                        return el;
                    }
                } catch (e) {
                    Utils.debug(`Invalid selector: ${selector}`);
                }
            }
            return null;
        },

        /**
         * Set gia tri textarea theo cach tuong thich voi React
         */
        setTextareaValue: (textarea, value) => {
            if (!textarea) return false;

            textarea.focus();

            // Cach 1: Su dung native value setter (tuong thich React)
            const nativeSetter = Object.getOwnPropertyDescriptor(
                HTMLTextAreaElement.prototype, 'value'
            )?.set;

            if (nativeSetter) {
                nativeSetter.call(textarea, value);
            } else {
                textarea.value = value;
            }

            // Trigger cac event de React nhan biet thay doi
            textarea.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
            textarea.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));

            // Them: trigger keyup event
            textarea.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));

            return textarea.value === value;
        },

        /**
         * Tinh delay voi exponential backoff
         */
        getRetryDelay: (attempt) => {
            const delay = CONFIG.retryDelayBase * Math.pow(1.5, attempt);
            return Math.min(delay, CONFIG.retryDelayMax);
        }
    };

    // =========================================================================
    // FETCH INTERCEPTOR
    // =========================================================================

    const FetchInterceptor = {
        originalFetch: window.fetch,
        listeners: new Set(),
        isActive: false,

        /**
         * Bat dau intercept fetch requests
         */
        start: function() {
            if (this.isActive) return;

            const self = this;
            window.fetch = function(url, options) {
                const result = self.originalFetch.apply(this, arguments);

                // Chi xu ly request batchGenerateImages
                const urlStr = url?.toString() || '';
                if (urlStr.includes('batchGenerateImages')) {
                    result
                        .then(response => response.clone().json())
                        .then(data => {
                            self.notifyListeners(data, null);
                        })
                        .catch(error => {
                            self.notifyListeners(null, error);
                        });
                }

                return result;
            };

            this.isActive = true;
            Utils.debug('Fetch interceptor started');
        },

        /**
         * Dung intercept va khoi phuc fetch goc
         */
        stop: function() {
            if (!this.isActive) return;

            window.fetch = this.originalFetch;
            this.listeners.clear();
            this.isActive = false;
            Utils.debug('Fetch interceptor stopped');
        },

        /**
         * Them listener cho response
         */
        addListener: function(callback) {
            this.listeners.add(callback);
            return () => this.listeners.delete(callback);
        },

        /**
         * Thong bao tat ca listeners
         */
        notifyListeners: function(data, error) {
            for (const callback of this.listeners) {
                try {
                    callback(data, error);
                } catch (e) {
                    Utils.debug(`Listener error: ${e.message}`);
                }
            }
        }
    };

    // =========================================================================
    // UI ACTIONS
    // =========================================================================

    const UIActions = {
        /**
         * Tim va tra ve textarea
         */
        findTextarea: () => {
            const textarea = document.querySelector(CONFIG.selectors.textarea);
            if (!textarea) {
                Utils.log('Khong tim thay textarea', 'error');
            }
            return textarea;
        },

        /**
         * Dien prompt vao textarea
         */
        setPrompt: (prompt) => {
            const textarea = UIActions.findTextarea();
            if (!textarea) return false;

            const success = Utils.setTextareaValue(textarea, prompt);
            if (success) {
                Utils.log(`Da dien prompt: "${prompt.slice(0, 50)}..."`, 'success');
            } else {
                Utils.log('Khong dien duoc prompt', 'error');
            }
            return success;
        },

        /**
         * Click nut Tao/Generate
         */
        clickGenerate: async () => {
            // Tim nut co icon arrow_forward va text "Tao"
            const buttons = document.querySelectorAll('button');

            for (const btn of buttons) {
                const text = btn.textContent || '';
                const hasArrowIcon = text.includes('arrow_forward') ||
                                    btn.querySelector('.google-symbols, .material-icons');
                const hasCreateText = text.includes('Tao') ||
                                     text.includes('T\u1ea1o') ||
                                     text.includes('Create') ||
                                     text.includes('Generate');

                if (hasCreateText && (hasArrowIcon || btn.type === 'submit')) {
                    btn.click();
                    Utils.log('Da click nut Tao', 'success');
                    return true;
                }
            }

            // Fallback: Tim nut voi aria-label
            const ariaBtn = Utils.findElement([
                'button[aria-label*="Send"]',
                'button[aria-label*="Gui"]',
                'button[aria-label*="Create"]'
            ]);

            if (ariaBtn) {
                ariaBtn.click();
                Utils.log('Da click nut Tao (aria-label)', 'success');
                return true;
            }

            // Fallback: Nhan Enter trong textarea
            const textarea = UIActions.findTextarea();
            if (textarea) {
                textarea.dispatchEvent(new KeyboardEvent('keydown', {
                    key: 'Enter',
                    code: 'Enter',
                    keyCode: 13,
                    which: 13,
                    bubbles: true,
                    cancelable: true
                }));
                Utils.log('Da nhan Enter', 'success');
                return true;
            }

            Utils.log('Khong tim thay cach gui prompt', 'error');
            return false;
        },

        /**
         * Click nut "Du an moi" / "New project"
         */
        clickNewProject: async () => {
            const buttons = document.querySelectorAll('button');

            for (const btn of buttons) {
                const text = btn.textContent || '';
                if (text.includes('Du an moi') ||
                    text.includes('D\u1ef1 \u00e1n m\u1edbi') ||
                    text.includes('New project')) {
                    btn.click();
                    Utils.log('Da click "Du an moi"', 'success');
                    return true;
                }
            }

            Utils.log('Khong tim thay nut "Du an moi"', 'warn');
            return false;
        },

        /**
         * Chon "Tao hinh anh" tu dropdown
         */
        selectImageGeneration: async () => {
            // Click dropdown
            const dropdown = document.querySelector('button[role="combobox"]');
            if (!dropdown) {
                Utils.log('Khong tim thay dropdown', 'warn');
                return false;
            }

            dropdown.click();
            Utils.log('Da mo dropdown', 'success');

            await Utils.sleep(500);

            // Tim option "Tao hinh anh"
            const options = document.querySelectorAll('[role="option"], [role="menuitem"], li, div');
            for (const opt of options) {
                const text = opt.textContent || '';
                if (text.includes('Tao hinh anh') ||
                    text.includes('T\u1ea1o h\u00ecnh \u1ea3nh') ||
                    text.includes('Generate image')) {
                    opt.click();
                    Utils.log('Da chon "Tao hinh anh"', 'success');
                    return true;
                }
            }

            Utils.log('Khong tim thay option "Tao hinh anh"', 'warn');
            return false;
        }
    };

    // =========================================================================
    // IMAGE GENERATOR
    // =========================================================================

    const ImageGenerator = {
        state: {
            isRunning: false,
            shouldStop: false,
            generatedImages: [],
            errors: []
        },

        /**
         * Doi va bat anh tu API response
         */
        waitForImage: (timeout = CONFIG.generateTimeout) => {
            return new Promise((resolve, reject) => {
                let resolved = false;
                let timeoutId = null;
                let removeListener = null;

                // Cleanup function
                const cleanup = () => {
                    resolved = true;
                    if (timeoutId) clearTimeout(timeoutId);
                    if (removeListener) removeListener();
                };

                // Start interceptor
                FetchInterceptor.start();

                // Add listener
                removeListener = FetchInterceptor.addListener((data, error) => {
                    if (resolved) return;

                    if (error) {
                        cleanup();
                        reject(error);
                        return;
                    }

                    // Check loi tu API
                    if (data?.error) {
                        const errorMsg = data.error.message || JSON.stringify(data.error);
                        Utils.log(`API Error: ${errorMsg}`, 'error');
                        cleanup();
                        reject(new Error(errorMsg));
                        return;
                    }

                    // Extract images
                    const images = ImageGenerator.extractImages(data);
                    if (images.length > 0) {
                        Utils.log(`Nhan duoc ${images.length} anh!`, 'success');
                        cleanup();
                        resolve(images);
                    }
                });

                // Timeout
                timeoutId = setTimeout(() => {
                    if (!resolved) {
                        cleanup();
                        reject(new Error(`Timeout sau ${timeout/1000}s`));
                    }
                }, timeout);
            });
        },

        /**
         * Extract images tu response data
         */
        extractImages: (data) => {
            const images = [];

            if (!data?.media) return images;

            for (const mediaItem of data.media) {
                const genImage = mediaItem?.image?.generatedImage;
                if (genImage?.fifeUrl) {
                    images.push({
                        url: genImage.fifeUrl,
                        seed: genImage.seed,
                        prompt: genImage.prompt,
                        base64: genImage.encodedImage
                    });
                }
            }

            return images;
        },

        /**
         * Download anh
         */
        downloadImage: async (imageUrl, filename) => {
            try {
                const response = await fetch(imageUrl);
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const blob = await response.blob();
                const blobUrl = URL.createObjectURL(blob);

                const link = document.createElement('a');
                link.href = blobUrl;
                link.download = filename;
                link.style.display = 'none';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);

                // Cleanup blob URL sau 1 giay
                setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);

                Utils.log(`Da tai: ${filename}`, 'success');
                return true;
            } catch (e) {
                Utils.log(`Loi tai anh: ${e.message}`, 'error');
                return false;
            }
        },

        /**
         * Tao 1 anh voi retry logic
         */
        generateOne: async (prompt, options = {}) => {
            const {
                outputName = null,
                download = true
            } = options;

            let retryCount = 0;

            while (retryCount < CONFIG.maxRetries) {
                try {
                    Utils.log(`Dang tao anh (lan ${retryCount + 1})...`, 'wait');

                    // 1. Dien prompt
                    if (!UIActions.setPrompt(prompt)) {
                        throw new Error('Khong dien duoc prompt');
                    }

                    await Utils.sleep(CONFIG.uiActionDelay);

                    // 2. Bat dau doi anh TRUOC khi click
                    const imagePromise = ImageGenerator.waitForImage();

                    // 3. Click nut tao
                    if (!await UIActions.clickGenerate()) {
                        throw new Error('Khong click duoc nut tao');
                    }

                    // 4. Doi anh
                    const images = await imagePromise;

                    // 5. Download neu can
                    if (download && images.length > 0) {
                        for (let i = 0; i < images.length; i++) {
                            const filename = outputName ||
                                `ve3_${Date.now()}_${i + 1}.png`;
                            await ImageGenerator.downloadImage(images[i].url, filename);

                            ImageGenerator.state.generatedImages.push({
                                prompt,
                                url: images[i].url,
                                filename
                            });
                        }
                    }

                    Utils.log(`THANH CONG: "${prompt.slice(0, 30)}..."`, 'success');
                    return { success: true, images };

                } catch (e) {
                    retryCount++;
                    Utils.log(`Loi: ${e.message}`, 'error');
                    ImageGenerator.state.errors.push({ prompt, error: e.message });

                    if (retryCount < CONFIG.maxRetries) {
                        const delay = Utils.getRetryDelay(retryCount);
                        Utils.log(`Retry sau ${delay/1000}s...`, 'warn');
                        await Utils.sleep(delay);
                    }
                } finally {
                    // Luon cleanup interceptor
                    FetchInterceptor.stop();
                }
            }

            Utils.log(`THAT BAI sau ${CONFIG.maxRetries} lan thu`, 'error');
            return { success: false, images: [] };
        },

        /**
         * Tao nhieu anh tu danh sach prompts
         */
        generateBatch: async (prompts, options = {}) => {
            const {
                prefix = 've3',
                download = true,
                continueOnError = true
            } = options;

            Utils.log(`=== BAT DAU TAO ${prompts.length} ANH ===`, 'info');

            ImageGenerator.state.isRunning = true;
            ImageGenerator.state.shouldStop = false;
            ImageGenerator.state.generatedImages = [];
            ImageGenerator.state.errors = [];

            let successCount = 0;
            let failedCount = 0;

            for (let i = 0; i < prompts.length; i++) {
                // Kiem tra lenh dung
                if (ImageGenerator.state.shouldStop) {
                    Utils.log('Da dung boi nguoi dung', 'warn');
                    break;
                }

                Utils.log(`--- [${i + 1}/${prompts.length}] ---`, 'info');

                const filename = `${prefix}_${i + 1}_${Date.now()}.png`;
                const result = await ImageGenerator.generateOne(prompts[i], {
                    outputName: filename,
                    download
                });

                if (result.success) {
                    successCount++;
                } else {
                    failedCount++;
                    if (!continueOnError) {
                        Utils.log('Dung do loi (continueOnError = false)', 'error');
                        break;
                    }
                }

                // Delay giua cac anh
                if (i < prompts.length - 1 && !ImageGenerator.state.shouldStop) {
                    Utils.log(`Doi ${CONFIG.delayBetweenImages/1000}s...`, 'wait');
                    await Utils.sleep(CONFIG.delayBetweenImages);
                }
            }

            ImageGenerator.state.isRunning = false;

            Utils.log(`=== XONG: ${successCount} thanh cong, ${failedCount} that bai ===`, 'info');

            return {
                success: failedCount === 0,
                successCount,
                failedCount,
                images: ImageGenerator.state.generatedImages,
                errors: ImageGenerator.state.errors
            };
        },

        /**
         * Dung qua trinh tao anh
         */
        stop: () => {
            ImageGenerator.state.shouldStop = true;
            FetchInterceptor.stop();
            Utils.log('Da gui lenh dung', 'warn');
        }
    };

    // =========================================================================
    // PUBLIC API
    // =========================================================================

    window.VE3 = {
        // Configuration
        config: CONFIG,

        // Main functions
        generateOne: ImageGenerator.generateOne,
        generateBatch: ImageGenerator.generateBatch,
        stop: ImageGenerator.stop,

        // UI helpers
        ui: {
            setPrompt: UIActions.setPrompt,
            clickGenerate: UIActions.clickGenerate,
            clickNewProject: UIActions.clickNewProject,
            selectImageGeneration: UIActions.selectImageGeneration
        },

        // State
        getState: () => ({ ...ImageGenerator.state }),

        // Utilities
        utils: {
            sleep: Utils.sleep,
            log: Utils.log
        },

        // Debug mode
        setDebug: (enabled) => {
            CONFIG.debug = enabled;
            Utils.log(`Debug mode: ${enabled ? 'ON' : 'OFF'}`, 'info');
        },

        // Help
        help: () => {
            console.log(`
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
  VE3 BROWSER AUTOMATION - HUONG DAN SU DUNG
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

TAO 1 ANH:
  VE3.generateOne("prompt cua ban")
  VE3.generateOne("prompt", { download: false })

TAO NHIEU ANH:
  VE3.generateBatch(["prompt 1", "prompt 2", "prompt 3"])
  VE3.generateBatch(prompts, { prefix: "myproject", download: true })

DUNG:
  VE3.stop()

UI HELPERS:
  VE3.ui.setPrompt("prompt")      - Dien prompt vao textarea
  VE3.ui.clickGenerate()          - Click nut Tao
  VE3.ui.clickNewProject()        - Click "Du an moi"
  VE3.ui.selectImageGeneration()  - Chon "Tao hinh anh"

DEBUG:
  VE3.setDebug(true)              - Bat debug mode
  VE3.getState()                  - Xem trang thai hien tai
  VE3.help()                      - Hien thi huong dan nay

\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
`);
        }
    };

    // Log thong bao san sang
    Utils.log('VE3 Browser Automation da san sang!', 'success');
    console.log('\ud83d\udcd6 Goi VE3.help() de xem huong dan');

})();
