/**
 * VE3 Browser Automation - Google Flow Image Generator
 * =====================================================
 * Optimized version - Hook 1 lan, tu dong tai va gui prompt tiep
 *
 * HUONG DAN:
 * 1. Mo: https://labs.google/fx/vi/tools/flow
 * 2. F12 -> Console -> Paste code nay
 * 3. VE3.init() - Khoi tao 1 lan
 * 4. VE3.run(["prompt1", "prompt2"]) - Chay batch
 *
 * @version 3.0.0
 */

(function() {
    'use strict';

    // =========================================================================
    // CONFIGURATION
    // =========================================================================
    const CONFIG = {
        // Ten project (vd: KA1-0001)
        projectName: 'default',

        // Delays
        delayAfterClick: 500,
        delayBetweenPrompts: 2000,
        delayAfterDownload: 1000,

        // Timeout cho moi anh
        generateTimeout: 120000,  // 2 phut

        // Auto download
        autoDownload: true,
    };

    // =========================================================================
    // STATE
    // =========================================================================
    const STATE = {
        isInitialized: false,
        isRunning: false,
        shouldStop: false,

        // Queue - moi item la {sceneId, prompt} hoac string
        promptQueue: [],
        currentPromptIndex: 0,
        currentPrompt: '',
        currentSceneId: '',  // scene_001, scene_002, ...

        // Tracking
        totalImages: 0,
        downloadedImages: 0,
        errors: [],

        // Callback khi 1 prompt hoan thanh
        onPromptComplete: null,
        onAllComplete: null,
    };

    // =========================================================================
    // UTILITIES
    // =========================================================================
    const Utils = {
        sleep: (ms) => new Promise(r => setTimeout(r, ms)),

        log: (msg, type = 'info') => {
            const icons = {
                info: 'ℹ️', success: '✅', error: '❌',
                warn: '⚠️', wait: '⏳', img: '🖼️'
            };
            console.log(`${icons[type] || '•'} [VE3] ${msg}`);
        },

        // Tao ten file theo scene_id tu Excel
        // Format: {project}_{sceneId}_{index}.png
        // Vd: KA1-0001_scene_001_1.png, KA1-0001_scene_001_2.png
        generateFilename: (index) => {
            const sceneId = STATE.currentSceneId || `prompt_${STATE.currentPromptIndex + 1}`;
            // Neu chi tao 1 anh thi khong can _1, _2
            if (index === 1) {
                return `${CONFIG.projectName}_${sceneId}.png`;
            }
            return `${CONFIG.projectName}_${sceneId}_${index}.png`;
        },

        // Set textarea value (React compatible)
        setTextareaValue: (textarea, value) => {
            textarea.focus();
            const setter = Object.getOwnPropertyDescriptor(
                HTMLTextAreaElement.prototype, 'value'
            )?.set;
            if (setter) {
                setter.call(textarea, value);
            } else {
                textarea.value = value;
            }
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
            textarea.dispatchEvent(new Event('change', { bubbles: true }));
        }
    };

    // =========================================================================
    // DOWNLOAD MANAGER
    // =========================================================================
    const Downloader = {
        pendingDownloads: 0,

        download: async (url, filename) => {
            try {
                Downloader.pendingDownloads++;

                const res = await fetch(url);
                const blob = await res.blob();
                const blobUrl = URL.createObjectURL(blob);

                const a = document.createElement('a');
                a.href = blobUrl;
                a.download = filename;
                a.style.display = 'none';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);

                setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);

                STATE.downloadedImages++;
                Utils.log(`Đã tải: ${filename}`, 'success');

                Downloader.pendingDownloads--;
                return true;
            } catch (e) {
                Downloader.pendingDownloads--;
                Utils.log(`Lỗi tải ${filename}: ${e.message}`, 'error');
                return false;
            }
        },

        // Doi tat ca downloads hoan thanh
        waitAllDownloads: async () => {
            while (Downloader.pendingDownloads > 0) {
                await Utils.sleep(100);
            }
        }
    };

    // =========================================================================
    // FETCH HOOK - Chi init 1 lan
    // =========================================================================
    const FetchHook = {
        isHooked: false,
        originalFetch: null,
        imageBuffer: [],  // Buffer anh cho prompt hien tai
        resolveWait: null,

        init: function() {
            if (this.isHooked) {
                Utils.log('Hook đã được init rồi', 'warn');
                return;
            }

            this.originalFetch = window.fetch;
            const self = this;

            window.fetch = function(url, opts) {
                const result = self.originalFetch.apply(this, arguments);

                const urlStr = url?.toString() || '';

                // Bat response tu batchGenerateImages
                if (urlStr.includes('batchGenerateImages')) {
                    Utils.log('Đang tạo ảnh...', 'wait');

                    result.then(async res => {
                        try {
                            const data = await res.clone().json();

                            // Check loi
                            if (data.error) {
                                Utils.log(`API Error: ${data.error.message || JSON.stringify(data.error)}`, 'error');
                                STATE.errors.push(data.error);
                                if (self.resolveWait) {
                                    self.resolveWait({ success: false, error: data.error });
                                }
                                return;
                            }

                            // Extract va download anh
                            if (data.media && data.media.length > 0) {
                                Utils.log(`Nhận được ${data.media.length} ảnh!`, 'img');

                                const downloadPromises = [];

                                for (let i = 0; i < data.media.length; i++) {
                                    const img = data.media[i]?.image?.generatedImage;
                                    if (img && img.fifeUrl) {
                                        const filename = Utils.generateFilename(i + 1);

                                        self.imageBuffer.push({
                                            url: img.fifeUrl,
                                            seed: img.seed,
                                            filename: filename
                                        });

                                        if (CONFIG.autoDownload) {
                                            downloadPromises.push(
                                                Downloader.download(img.fifeUrl, filename)
                                            );
                                        }
                                    }
                                }

                                // Doi tat ca downloads
                                if (downloadPromises.length > 0) {
                                    await Promise.all(downloadPromises);
                                }

                                // Resolve promise dang cho
                                if (self.resolveWait) {
                                    self.resolveWait({
                                        success: true,
                                        images: [...self.imageBuffer]
                                    });
                                    self.imageBuffer = [];
                                }
                            }
                        } catch (e) {
                            Utils.log(`Parse error: ${e.message}`, 'error');
                            if (self.resolveWait) {
                                self.resolveWait({ success: false, error: e.message });
                            }
                        }
                    }).catch(e => {
                        Utils.log(`Fetch error: ${e.message}`, 'error');
                        if (self.resolveWait) {
                            self.resolveWait({ success: false, error: e.message });
                        }
                    });
                }

                return result;
            };

            this.isHooked = true;
            Utils.log('Hook đã sẵn sàng! Ảnh sẽ tự động tải về.', 'success');
        },

        // Doi cho den khi nhan duoc anh
        waitForImages: function(timeout = CONFIG.generateTimeout) {
            return new Promise((resolve) => {
                this.imageBuffer = [];
                this.resolveWait = resolve;

                // Timeout
                setTimeout(() => {
                    if (this.resolveWait === resolve) {
                        this.resolveWait = null;
                        resolve({ success: false, error: 'Timeout' });
                    }
                }, timeout);
            });
        },

        // Cleanup
        destroy: function() {
            if (this.originalFetch) {
                window.fetch = this.originalFetch;
                this.isHooked = false;
                Utils.log('Hook đã được gỡ', 'info');
            }
        }
    };

    // =========================================================================
    // UI ACTIONS
    // =========================================================================
    const UI = {
        // Click "Du an moi"
        clickNewProject: async () => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                const text = b.textContent || '';
                if (text.includes('Dự án mới') || text.includes('New project')) {
                    b.click();
                    Utils.log('Đã click "Dự án mới"', 'success');
                    await Utils.sleep(CONFIG.delayAfterClick);
                    return true;
                }
            }
            Utils.log('Không tìm thấy nút "Dự án mới"', 'warn');
            return false;
        },

        // Chon "Tao hinh anh" tu dropdown
        selectImageGeneration: async () => {
            const dropdown = document.querySelector('button[role="combobox"]');
            if (!dropdown) {
                Utils.log('Không tìm thấy dropdown', 'warn');
                return false;
            }

            dropdown.click();
            Utils.log('Đã mở dropdown', 'success');
            await Utils.sleep(500);

            const options = document.querySelectorAll('[role="option"], [role="menuitem"], li, div');
            for (const opt of options) {
                const text = opt.textContent || '';
                if (text.includes('Tạo hình ảnh') || text.includes('Generate image')) {
                    opt.click();
                    Utils.log('Đã chọn "Tạo hình ảnh"', 'success');
                    await Utils.sleep(CONFIG.delayAfterClick);
                    return true;
                }
            }

            Utils.log('Không tìm thấy option "Tạo hình ảnh"', 'warn');
            return false;
        },

        // Dien prompt
        setPrompt: (prompt) => {
            const textarea = document.querySelector('textarea');
            if (!textarea) {
                Utils.log('Không tìm thấy textarea', 'error');
                return false;
            }

            Utils.setTextareaValue(textarea, prompt);
            Utils.log(`Đã điền: "${prompt.slice(0, 50)}..."`, 'success');
            return true;
        },

        // Click nut Tao
        clickGenerate: async () => {
            // Tim nut co text "Tao" va icon arrow
            const buttons = document.querySelectorAll('button');

            for (const btn of buttons) {
                const text = btn.textContent || '';
                // Nut co "Tao" hoac "Create" va co icon
                if ((text.includes('Tạo') || text.includes('Create') || text.includes('arrow_forward'))
                    && (btn.querySelector('.google-symbols, .material-icons, svg') || text.includes('arrow'))) {
                    btn.click();
                    Utils.log('Đã click nút Tạo', 'success');
                    return true;
                }
            }

            // Fallback: tim nut submit gan textarea
            const textarea = document.querySelector('textarea');
            if (textarea) {
                const container = textarea.closest('form') || textarea.parentElement?.parentElement?.parentElement;
                if (container) {
                    const submitBtn = container.querySelector('button[type="submit"], button:has(svg)');
                    if (submitBtn) {
                        submitBtn.click();
                        Utils.log('Đã click nút submit', 'success');
                        return true;
                    }
                }

                // Fallback: Enter
                textarea.dispatchEvent(new KeyboardEvent('keydown', {
                    key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true
                }));
                Utils.log('Đã nhấn Enter', 'success');
                return true;
            }

            Utils.log('Không tìm thấy cách gửi', 'error');
            return false;
        }
    };

    // =========================================================================
    // MAIN RUNNER
    // =========================================================================
    const Runner = {
        // Xu ly 1 prompt
        // item co the la string hoac {sceneId, prompt}
        processOnePrompt: async (item, index) => {
            // Parse item
            let prompt, sceneId;
            if (typeof item === 'string') {
                prompt = item;
                sceneId = `scene_${String(index + 1).padStart(3, '0')}`;
            } else {
                prompt = item.prompt;
                sceneId = item.sceneId || item.scene_id || `scene_${String(index + 1).padStart(3, '0')}`;
            }

            STATE.currentPrompt = prompt;
            STATE.currentSceneId = sceneId;
            STATE.currentPromptIndex = index;

            Utils.log(`\n━━━ [${index + 1}/${STATE.promptQueue.length}] ${sceneId} ━━━`, 'info');

            // 1. Dien prompt
            if (!UI.setPrompt(prompt)) {
                return { success: false, error: 'Cannot set prompt' };
            }

            await Utils.sleep(CONFIG.delayAfterClick);

            // 2. Bat dau doi anh TRUOC khi click
            const waitPromise = FetchHook.waitForImages();

            // 3. Click tao
            if (!await UI.clickGenerate()) {
                return { success: false, error: 'Cannot click generate' };
            }

            // 4. Doi anh
            const result = await waitPromise;

            // 5. Doi downloads hoan thanh
            await Downloader.waitAllDownloads();

            // 6. Callback
            if (STATE.onPromptComplete) {
                STATE.onPromptComplete(index, prompt, result);
            }

            return result;
        },

        // Chay tat ca prompts trong queue
        runQueue: async () => {
            if (STATE.isRunning) {
                Utils.log('Đang chạy rồi!', 'warn');
                return;
            }

            STATE.isRunning = true;
            STATE.shouldStop = false;
            STATE.downloadedImages = 0;
            STATE.errors = [];

            const total = STATE.promptQueue.length;
            let success = 0;
            let failed = 0;

            Utils.log(`\n${'═'.repeat(50)}`, 'info');
            Utils.log(`BẮT ĐẦU TẠO ${total} ẢNH`, 'info');
            Utils.log(`Project: ${CONFIG.projectName}`, 'info');
            Utils.log(`${'═'.repeat(50)}`, 'info');

            for (let i = 0; i < total; i++) {
                if (STATE.shouldStop) {
                    Utils.log('Đã dừng bởi user', 'warn');
                    break;
                }

                const result = await Runner.processOnePrompt(STATE.promptQueue[i], i);

                if (result.success) {
                    success++;
                } else {
                    failed++;
                    Utils.log(`Lỗi prompt ${i + 1}: ${result.error}`, 'error');
                }

                // Delay giua cac prompt
                if (i < total - 1 && !STATE.shouldStop) {
                    Utils.log(`Đợi ${CONFIG.delayBetweenPrompts/1000}s...`, 'wait');
                    await Utils.sleep(CONFIG.delayBetweenPrompts);
                }
            }

            STATE.isRunning = false;

            Utils.log(`\n${'═'.repeat(50)}`, 'info');
            Utils.log(`HOÀN THÀNH: ${success} thành công, ${failed} thất bại`, 'info');
            Utils.log(`Tổng ảnh đã tải: ${STATE.downloadedImages}`, 'info');
            Utils.log(`${'═'.repeat(50)}`, 'info');

            // Callback
            if (STATE.onAllComplete) {
                STATE.onAllComplete({ success, failed, total: STATE.downloadedImages });
            }

            return { success, failed };
        }
    };

    // =========================================================================
    // PUBLIC API
    // =========================================================================
    window.VE3 = {
        // Config
        config: CONFIG,
        state: STATE,

        // Khoi tao (chi can goi 1 lan)
        init: (projectName = 'default') => {
            CONFIG.projectName = projectName;
            FetchHook.init();
            STATE.isInitialized = true;
            Utils.log(`Đã khởi tạo cho project: ${projectName}`, 'success');
            Utils.log('Gọi VE3.run(["prompt1", "prompt2"]) để bắt đầu', 'info');
        },

        // Chay voi danh sach prompts
        run: async (prompts, projectName = null) => {
            if (!STATE.isInitialized) {
                VE3.init(projectName || 'default');
            }

            if (projectName) {
                CONFIG.projectName = projectName;
            }

            if (!Array.isArray(prompts)) {
                prompts = [prompts];
            }

            STATE.promptQueue = prompts;
            return await Runner.runQueue();
        },

        // Tao 1 anh don le
        one: async (prompt, projectName = null) => {
            return await VE3.run([prompt], projectName);
        },

        // Dung
        stop: () => {
            STATE.shouldStop = true;
            Utils.log('Đã gửi lệnh dừng', 'warn');
        },

        // Setup UI (click New Project + chon Generate Image)
        setup: async () => {
            await UI.clickNewProject();
            await Utils.sleep(500);
            await UI.selectImageGeneration();
        },

        // Callbacks
        onPromptDone: (callback) => {
            STATE.onPromptComplete = callback;
        },

        onAllDone: (callback) => {
            STATE.onAllComplete = callback;
        },

        // Cleanup
        destroy: () => {
            FetchHook.destroy();
            STATE.isInitialized = false;
        },

        // Help
        help: () => {
            console.log(`
${'═'.repeat(60)}
  VE3 BROWSER AUTOMATION v3.0 - HƯỚNG DẪN
${'═'.repeat(60)}

KHỞI TẠO (chỉ 1 lần):
  VE3.init("KA1-0001")        - Khởi tạo với mã project

CHẠY VỚI SCENE ID (khuyên dùng):
  VE3.run([
    {sceneId: "scene_001", prompt: "a cat..."},
    {sceneId: "scene_002", prompt: "a dog..."}
  ])
  => File: KA1-0001_scene_001.png, KA1-0001_scene_002.png

CHẠY ĐƠN GIẢN:
  VE3.run(["prompt1", "prompt2"])
  => File: KA1-0001_scene_001.png, KA1-0001_scene_002.png

TẠO 1 ẢNH:
  VE3.one("prompt")

SETUP UI (nếu cần):
  VE3.setup()                 - Click "Dự án mới" + chọn "Tạo hình ảnh"

ĐIỀU KHIỂN:
  VE3.stop()                  - Dừng
  VE3.destroy()               - Gỡ hook

CONFIG:
  VE3.config.projectName      - Mã project (dùng cho tên file)
  VE3.config.autoDownload     - Tự động tải (true/false)
  VE3.config.delayBetweenPrompts - Delay giữa các prompt (ms)

LƯU Ý:
  - File tải về nằm trong Downloads
  - Python sẽ move vào thư mục img/ của project

${'═'.repeat(60)}
`);
        }
    };

    // Auto log
    Utils.log('VE3 v3.0 đã load! Gọi VE3.init("project_name") để bắt đầu.', 'success');

})();
