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

        // API settings
        apiBaseUrl: 'https://labs.google/api',
        imageModel: 'GEM_PIX_2',
        aspectRatio: 'IMAGE_ASPECT_RATIO_LANDSCAPE',
        tool: 'flow',

        // NEW: Mode - 'textarea' (cu) hoac 'api' (moi - goi truc tiep API)
        mode: 'api',  // Mac dinh dung API mode de co reference images
    };

    // =========================================================================
    // STATE
    // =========================================================================
    const STATE = {
        isInitialized: false,
        isRunning: false,
        shouldStop: false,
        isSetupDone: false,  // NEW: Chi setup 1 lan

        // Queue - moi item la {sceneId, prompt} hoac string
        promptQueue: [],
        currentPromptIndex: 0,
        currentPrompt: '',
        currentSceneId: '',  // scene_001, scene_002, ...

        // Tracking
        totalImages: 0,
        downloadedImages: 0,
        errors: [],

        // NEW: Luu project URL va media_names cho reference
        projectUrl: '',      // URL cua project hien tai
        mediaNames: {},      // {sceneId: media_name} - de reference sau

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
    // API CALLER - Goi truc tiep batchGenerateImages API
    // =========================================================================
    const API = {
        // Lay projectId tu URL hien tai
        // URL format: https://labs.google/fx/vi/tools/flow/project/{projectId}
        getProjectId: () => {
            const url = window.location.href;
            const match = url.match(/\/project\/([a-f0-9-]+)/i);
            return match ? match[1] : null;
        },

        // Tao sessionId random
        generateSessionId: () => {
            return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
                const r = Math.random() * 16 | 0;
                const v = c === 'x' ? r : (r & 0x3 | 0x8);
                return v.toString(16);
            });
        },

        // Tao seed random
        generateSeed: () => {
            return Math.floor(Math.random() * 999999) + 1;
        },

        // Build request payload - GIONG HET google_flow_api.py
        buildPayload: (prompt, referenceNames = [], count = 2) => {
            const projectId = API.getProjectId();
            const sessionId = API.generateSessionId();

            // Build imageInputs voi day du fields (giong API)
            const imageInputs = referenceNames
                .filter(name => name && name.trim())
                .map(name => ({
                    name: name.trim(),
                    imageInputType: "IMAGE_INPUT_TYPE_REFERENCE"  // QUAN TRONG!
                }));

            // Build requests array
            const requests = [];
            for (let i = 0; i < count; i++) {
                requests.push({
                    clientContext: {
                        sessionId: sessionId,
                        projectId: projectId,
                        tool: CONFIG.tool
                    },
                    seed: API.generateSeed(),
                    imageModelName: CONFIG.imageModel,
                    imageAspectRatio: CONFIG.aspectRatio,
                    prompt: prompt,
                    imageInputs: imageInputs
                });
            }

            return { requests };
        },

        // Goi API tao anh
        generateImages: async (prompt, referenceNames = [], count = 2) => {
            const projectId = API.getProjectId();
            if (!projectId) {
                throw new Error('Khong tim thay projectId trong URL. Hay mo project truoc!');
            }

            const url = `${CONFIG.apiBaseUrl}/v1/projects/${projectId}/flowMedia:batchGenerateImages`;
            const payload = API.buildPayload(prompt, referenceNames, count);

            Utils.log(`API Call: ${url}`, 'info');
            Utils.log(`Prompt: ${prompt.slice(0, 50)}...`, 'info');
            if (referenceNames.length > 0) {
                Utils.log(`References: ${referenceNames.join(', ')}`, 'info');
            }

            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',  // Quan trong: gui cookies de xac thuc
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`API error ${response.status}: ${errorText.slice(0, 200)}`);
            }

            return await response.json();
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
                                    const mediaItem = data.media[i];
                                    const img = mediaItem?.image?.generatedImage;

                                    // QUAN TRONG: Lay media_name de reference sau!
                                    const mediaName = mediaItem?.name || '';
                                    const workflowId = mediaItem?.workflowId || '';

                                    if (img && img.fifeUrl) {
                                        const filename = Utils.generateFilename(i + 1);

                                        self.imageBuffer.push({
                                            url: img.fifeUrl,
                                            seed: img.seed,
                                            filename: filename,
                                            mediaName: mediaName,      // NEW: Luu media_name
                                            workflowId: workflowId,    // NEW: Luu workflow_id
                                        });

                                        // Luu media_name vao STATE de reference sau
                                        if (mediaName && STATE.currentSceneId) {
                                            STATE.mediaNames[STATE.currentSceneId] = mediaName;
                                            Utils.log(`Saved media_name for ${STATE.currentSceneId}: ${mediaName.slice(0, 50)}...`, 'success');
                                        }

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
            Utils.log('>>> Tim nut "Du an moi"...', 'info');
            const btns = document.querySelectorAll('button');
            Utils.log(`Tim thay ${btns.length} buttons`, 'info');

            for (const b of btns) {
                const text = b.textContent || '';
                if (text.includes('Dự án mới') || text.includes('New project')) {
                    Utils.log(`Click button: "${text.trim().slice(0, 30)}"`, 'info');
                    b.click();
                    Utils.log('OK - Da click "Du an moi"', 'success');
                    await Utils.sleep(CONFIG.delayAfterClick);
                    return true;
                }
            }

            // Log cac button de debug
            Utils.log('Cac button tim thay:', 'warn');
            btns.forEach((b, i) => {
                if (i < 10) Utils.log(`  [${i}] "${(b.textContent || '').trim().slice(0, 50)}"`, 'info');
            });
            Utils.log('FAIL - Khong tim thay nut "Du an moi"', 'error');
            return false;
        },

        // Chon "Tao hinh anh" tu dropdown
        selectImageGeneration: async () => {
            Utils.log('>>> Tim dropdown chon loai...', 'info');
            const dropdown = document.querySelector('button[role="combobox"]');
            if (!dropdown) {
                Utils.log('FAIL - Khong tim thay dropdown (button[role=combobox])', 'error');
                return false;
            }

            Utils.log('Click mo dropdown...', 'info');
            dropdown.click();
            await Utils.sleep(500);

            // Tim "Tao hinh anh" - duyet TAT CA elements, check size de dam bao la element that
            Utils.log('>>> Tim option "Tao hinh anh"...', 'info');
            const allElements = document.querySelectorAll('*');

            for (const el of allElements) {
                const text = el.textContent || '';
                if (text === 'Tạo hình ảnh' || text.includes('Tạo hình ảnh từ văn bản') ||
                    text === 'Generate image' || text.includes('Generate image from text')) {
                    // Check size - chi click element co kich thuoc hop ly
                    const rect = el.getBoundingClientRect();
                    if (rect.height > 10 && rect.height < 80 && rect.width > 50) {
                        Utils.log(`Click: "${text.trim().slice(0, 40)}" (h=${rect.height})`, 'info');
                        el.click();
                        Utils.log('OK - Da chon "Tao hinh anh"', 'success');
                        await Utils.sleep(CONFIG.delayAfterClick);
                        return true;
                    }
                }
            }

            Utils.log('FAIL - Khong tim thay option "Tao hinh anh"', 'error');
            return false;
        },

        // Focus textarea (giong token code)
        focusTextarea: async () => {
            const textarea = document.querySelector('textarea');
            if (!textarea) {
                Utils.log('Khong tim thay textarea', 'error');
                return false;
            }
            textarea.focus();
            textarea.click();
            Utils.log('Da focus textarea', 'success');
            return true;
        },

        // Dien prompt
        setPrompt: (prompt) => {
            const textarea = document.querySelector('textarea');
            if (!textarea) {
                Utils.log('Khong tim thay textarea', 'error');
                return false;
            }

            // Focus truoc khi set value
            textarea.focus();
            textarea.click();

            Utils.setTextareaValue(textarea, prompt);
            Utils.log(`Da dien: "${prompt.slice(0, 50)}..."`, 'success');
            return true;
        },

        // Gui prompt - Don gian chi can nhan Enter (giong token code)
        clickGenerate: async () => {
            Utils.log('Nhan Enter de gui...', 'info');

            const textarea = document.querySelector('textarea');
            if (textarea) {
                // Focus lai textarea
                textarea.focus();

                // Nhan Enter de gui (giong token code dung pag.press("enter"))
                textarea.dispatchEvent(new KeyboardEvent('keydown', {
                    key: 'Enter',
                    code: 'Enter',
                    keyCode: 13,
                    which: 13,
                    bubbles: true
                }));

                Utils.log('Da nhan Enter', 'success');
                return true;
            }

            Utils.log('FAIL - Khong tim thay nut gui', 'error');
            return false;
        }
    };

    // =========================================================================
    // MAIN RUNNER
    // =========================================================================
    const Runner = {
        // Xu ly 1 prompt
        // item co the la string hoac {sceneId, prompt, referenceFiles}
        processOnePrompt: async (item, index) => {
            // Parse item
            let prompt, sceneId, referenceFiles;
            if (typeof item === 'string') {
                prompt = item;
                sceneId = `scene_${String(index + 1).padStart(3, '0')}`;
                referenceFiles = [];
            } else {
                prompt = item.prompt;
                sceneId = item.sceneId || item.scene_id || `scene_${String(index + 1).padStart(3, '0')}`;
                referenceFiles = item.referenceFiles || item.reference_files || [];
            }

            STATE.currentPrompt = prompt;
            STATE.currentSceneId = sceneId;
            STATE.currentPromptIndex = index;

            Utils.log(`\n━━━ [${index + 1}/${STATE.promptQueue.length}] ${sceneId} ━━━`, 'info');

            // Lookup media_names cho references
            const referenceNames = [];
            if (referenceFiles && referenceFiles.length > 0) {
                for (const refFile of referenceFiles) {
                    // refFile co the la "nvc.png" hoac "nvc"
                    const refId = refFile.replace('.png', '').replace('.jpg', '');
                    const mediaName = STATE.mediaNames[refId];
                    if (mediaName) {
                        referenceNames.push(mediaName);
                        Utils.log(`  Reference: ${refId} → ${mediaName.slice(0, 40)}...`, 'info');
                    } else {
                        Utils.log(`  Reference: ${refId} → (chua co media_name, skip)`, 'warn');
                    }
                }
            }

            // =====================================================================
            // Build JSON prompt - GIONG HET API FORMAT
            // =====================================================================
            let textToSend;

            // LUON GUI JSON FORMAT (giong API) de dam bao chat luong
            const projectId = API.getProjectId();
            const sessionId = API.generateSessionId();

            // Build imageInputs voi day du fields (giong API)
            const imageInputs = referenceNames.map(name => ({
                name: name,
                imageInputType: "IMAGE_INPUT_TYPE_REFERENCE"  // QUAN TRONG!
            }));

            const jsonPayload = {
                requests: [{
                    clientContext: {
                        sessionId: sessionId,
                        projectId: projectId || "default",
                        tool: CONFIG.tool
                    },
                    seed: API.generateSeed(),
                    imageModelName: CONFIG.imageModel,
                    imageAspectRatio: CONFIG.aspectRatio,
                    prompt: prompt,
                    imageInputs: imageInputs
                }]
            };

            textToSend = JSON.stringify(jsonPayload);

            if (referenceNames.length > 0) {
                Utils.log(`[JSON MODE] Gui JSON voi ${referenceNames.length} references`, 'info');
            } else {
                Utils.log('[JSON MODE] Gui JSON (khong co references)', 'info');
            }
            Utils.log(`JSON: ${textToSend.slice(0, 150)}...`, 'info');

            // 1. Dien prompt (JSON hoac text)
            if (!UI.setPrompt(textToSend)) {
                return { success: false, error: 'Cannot set prompt' };
            }

            await Utils.sleep(CONFIG.delayAfterClick);

            // 2. Bat dau doi anh TRUOC khi click
            Utils.log('Bat dau theo doi response...', 'info');
            const waitPromise = FetchHook.waitForImages();

            // 3. Click tao
            Utils.log('Click nut Tao...', 'info');
            if (!await UI.clickGenerate()) {
                return { success: false, error: 'Cannot click generate' };
            }

            // 4. Doi anh
            Utils.log('Dang cho tao anh...', 'wait');
            const result = await waitPromise;

            // 5. Doi downloads hoan thanh
            if (result.success) {
                Utils.log('Dang tai anh...', 'wait');
                await Downloader.waitAllDownloads();
            }

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
        // CHI CHAY 1 LAN - giu nguyen project de reference images hoat dong!
        setup: async () => {
            // QUAN TRONG: Chi setup 1 lan! Khong mo project moi nua!
            if (STATE.isSetupDone) {
                Utils.log('Setup da chay roi, skip (giu nguyen project)', 'info');
                // Chi can focus textarea
                await UI.focusTextarea();
                await Utils.sleep(500);
                return;
            }

            Utils.log('=== SETUP UI (LAN DAU) ===', 'info');

            // 1. Click "Du an moi"
            Utils.log('Buoc 1: Click Du an moi...', 'info');
            await UI.clickNewProject();

            // 2. Doi 5 giay cho page load (giong token code)
            Utils.log('Doi 5s cho page load...', 'wait');
            await Utils.sleep(5000);

            // 3. Click dropdown + chon "Tao hinh anh"
            Utils.log('Buoc 2: Chon Tao hinh anh...', 'info');
            await UI.selectImageGeneration();

            // 4. Doi 3 giay (giong token code)
            Utils.log('Doi 3s...', 'wait');
            await Utils.sleep(3000);

            // 5. Focus textarea
            Utils.log('Buoc 3: Focus textarea...', 'info');
            await UI.focusTextarea();

            // 6. Doi 1 giay
            Utils.log('Doi 1s...', 'wait');
            await Utils.sleep(1000);

            // 7. LUU PROJECT URL
            STATE.projectUrl = window.location.href;
            Utils.log(`Project URL: ${STATE.projectUrl}`, 'success');

            // 8. Danh dau da setup xong
            STATE.isSetupDone = true;

            Utils.log('=== SETUP XONG - TAT CA ANH SE DUNG CUNG PROJECT ===', 'success');
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
            STATE.isSetupDone = false;
            STATE.projectUrl = '';
            STATE.mediaNames = {};
        },

        // NEW: Lay project URL hien tai
        getProjectUrl: () => {
            return STATE.projectUrl || window.location.href;
        },

        // NEW: Lay tat ca media_names da luu
        getMediaNames: () => {
            return { ...STATE.mediaNames };
        },

        // NEW: Lay media_name cho 1 scene_id
        getMediaName: (sceneId) => {
            return STATE.mediaNames[sceneId] || null;
        },

        // NEW: Set media_names tu Python (load tu cache)
        setMediaNames: (mediaNames) => {
            STATE.mediaNames = { ...STATE.mediaNames, ...mediaNames };
            Utils.log(`Loaded ${Object.keys(mediaNames).length} media_names from cache`, 'success');
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
