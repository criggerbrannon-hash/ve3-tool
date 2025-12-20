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
        consentTriggered: false,  // Da trigger consent dialog chua

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

                // DEBUG: Log all fetch calls to understand API
                if (urlStr.includes('labs.google') || urlStr.includes('generate') || urlStr.includes('flow')) {
                    Utils.log(`[FETCH] URL: ${urlStr.slice(0, 100)}...`, 'info');
                }

                // Bat response tu batchGenerateImages hoac cac endpoint tuong tu
                if (urlStr.includes('batchGenerateImages') || urlStr.includes('generateImages') || urlStr.includes('generate')) {
                    Utils.log(`[FETCH] Matched generate endpoint: ${urlStr.slice(0, 80)}...`, 'wait');

                    result.then(async res => {
                        try {
                            const data = await res.clone().json();

                            // Check loi
                            if (data.error) {
                                Utils.log(`API Error: ${data.error.message || JSON.stringify(data.error)}`, 'error');
                                STATE.errors.push(data.error);
                                if (self.resolveWait) {
                                    self.clearErrorCheck();
                                    self.resolveWait({ success: false, error: data.error });
                                }
                                return;
                            }

                            // DEBUG: Log raw response structure
                            Utils.log(`[DEBUG] Response keys: ${Object.keys(data).join(', ')}`, 'info');
                            Utils.log(`[DEBUG] data.media exists: ${!!data.media}, length: ${data.media?.length || 0}`, 'info');

                            // Extract va download anh
                            if (data.media && data.media.length > 0) {
                                Utils.log(`Nhận được ${data.media.length} ảnh!`, 'img');

                                const downloadPromises = [];

                                for (let i = 0; i < data.media.length; i++) {
                                    const mediaItem = data.media[i];
                                    const img = mediaItem?.image?.generatedImage;

                                    // DEBUG: Log mediaItem structure
                                    Utils.log(`[DEBUG] mediaItem keys: ${Object.keys(mediaItem || {}).join(', ')}`, 'info');

                                    // QUAN TRONG: Lay media_name de reference sau!
                                    const mediaName = mediaItem?.name || '';
                                    const workflowId = mediaItem?.workflowId || '';

                                    // DEBUG: Log mediaName
                                    Utils.log(`[DEBUG] mediaName = "${mediaName}", workflowId = "${workflowId}"`, 'info');

                                    if (img && img.fifeUrl) {
                                        const filename = Utils.generateFilename(i + 1);

                                        self.imageBuffer.push({
                                            url: img.fifeUrl,
                                            seed: img.seed,
                                            filename: filename,
                                            mediaName: mediaName,      // media_name de reference sau
                                            workflowId: workflowId,
                                            index: i,                  // Vi tri trong response
                                        });

                                        Utils.log(`Image ${i+1}: filename=${filename}, mediaName=${mediaName ? mediaName.slice(0,40)+'...' : 'NONE'}`, 'info');

                                        // KHONG tu dong luu mediaName vao STATE o day!
                                        // Python se chon anh tot nhat roi goi setMediaName() voi mediaName dung

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
                                    self.clearErrorCheck();  // Clear error toast checking
                                    self.resolveWait({
                                        success: true,
                                        images: [...self.imageBuffer]
                                    });
                                    self.imageBuffer = [];
                                }
                            } else {
                                // Khong co media trong response
                                Utils.log(`[DEBUG] No media in response. Full data: ${JSON.stringify(data).slice(0, 500)}`, 'warn');
                                // Van resolve voi empty images de khong bi hang
                                if (self.resolveWait) {
                                    self.clearErrorCheck();  // Clear error toast checking
                                    self.resolveWait({
                                        success: true,
                                        images: []
                                    });
                                }
                            }
                        } catch (e) {
                            Utils.log(`Parse error: ${e.message}`, 'error');
                            if (self.resolveWait) {
                                self.clearErrorCheck();
                                self.resolveWait({ success: false, error: e.message });
                            }
                        }
                    }).catch(e => {
                        Utils.log(`Fetch error: ${e.message}`, 'error');
                        if (self.resolveWait) {
                            self.clearErrorCheck();
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
        // Store error check interval ID for cleanup
        errorCheckIntervalId: null,

        waitForImages: function(timeout = CONFIG.generateTimeout) {
            const self = this;
            return new Promise((resolve) => {
                this.imageBuffer = [];
                this.resolveWait = resolve;

                // Check for error notification
                // Khi lỗi xuất hiện: <div class="sc-f6076f05-1 dGzeli"><button>Đóng</button></div>
                // Button "Đóng" + "Gửi ý kiến phản hồi" chỉ xuất hiện khi có lỗi
                const checkErrorNotification = () => {
                    // Method 1: Tìm div có class chứa "sc-f6076f05" với button "Đóng" bên trong
                    const toastDivs = document.querySelectorAll('div[class*="sc-f6076f05"]');
                    for (const div of toastDivs) {
                        const buttons = div.querySelectorAll('button');
                        for (const btn of buttons) {
                            const text = btn.textContent?.trim() || '';
                            if (text === 'Đóng') {
                                return { found: true, divClass: div.className };
                            }
                        }
                    }

                    // Method 2: Tìm button "Đóng" và check parent có class sc-f6076f05
                    const allButtons = document.querySelectorAll('button');
                    for (const btn of allButtons) {
                        const text = btn.textContent?.trim() || '';
                        if (text === 'Đóng') {
                            const parent = btn.parentElement;
                            if (parent && parent.className && parent.className.includes('sc-f6076f05')) {
                                return { found: true, divClass: parent.className };
                            }
                        }
                    }

                    return { found: false };
                };

                // Start error check polling
                Utils.log('[ERROR-CHECK] Bắt đầu theo dõi lỗi (mỗi 1 giây)...', 'info');
                let errorCheckCount = 0;

                // Poll for error every 1 second
                self.errorCheckIntervalId = setInterval(() => {
                    errorCheckCount++;
                    const result = checkErrorNotification();

                    // Log every 10 seconds to show it's still running
                    if (errorCheckCount % 10 === 0) {
                        Utils.log(`[ERROR-CHECK] Đã check ${errorCheckCount} lần...`, 'info');
                    }

                    if (result.found) {
                        Utils.log(`⚠️ Phát hiện toast lỗi! Class: ${result.divClass}`, 'error');
                        clearInterval(self.errorCheckIntervalId);
                        self.errorCheckIntervalId = null;
                        if (self.resolveWait === resolve) {
                            self.resolveWait = null;
                            resolve({ success: false, error: 'UI Error: Generation failed' });
                        }
                    }
                }, 1000);

                // Timeout
                setTimeout(() => {
                    if (self.errorCheckIntervalId) {
                        clearInterval(self.errorCheckIntervalId);
                        self.errorCheckIntervalId = null;
                    }
                    if (self.resolveWait === resolve) {
                        self.resolveWait = null;
                        resolve({ success: false, error: 'Timeout' });
                    }
                }, timeout);
            });
        },

        // Clear error check interval (called when images received successfully)
        clearErrorCheck: function() {
            if (this.errorCheckIntervalId) {
                clearInterval(this.errorCheckIntervalId);
                this.errorCheckIntervalId = null;
            }
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
        },

        // Upload anh reference tu base64
        // base64Data: string base64 cua anh (khong co prefix data:image/...)
        // filename: ten file (vd: nvc.png)

        // Trigger consent dialog khi bat dau du an moi
        // Flow: Click ADD -> Click Upload -> Click "Tôi đồng ý" -> ESC 2 lan
        triggerConsent: async () => {
            if (STATE.consentTriggered) {
                Utils.log('[CONSENT] Da trigger truoc do, skip', 'info');
                return true;
            }

            Utils.log('[CONSENT] Bat dau trigger consent...', 'info');

            // Step 1: Click ADD - thu nhieu selectors
            let addBtn = null;

            // Method 1: Tim i.google-symbols voi text "add"
            const addIcons = document.querySelectorAll('i.google-symbols');
            for (const icon of addIcons) {
                if (icon.textContent.trim() === 'add') {
                    addBtn = icon;
                    break;
                }
            }

            // Method 2: Tim mat-icon voi text "add"
            if (!addBtn) {
                const matIcons = document.querySelectorAll('mat-icon, .mat-icon, .material-icons');
                for (const icon of matIcons) {
                    if (icon.textContent.trim() === 'add') {
                        addBtn = icon;
                        break;
                    }
                }
            }

            // Method 3: Tim button co icon add ben trong
            if (!addBtn) {
                const allBtns = document.querySelectorAll('button');
                for (const btn of allBtns) {
                    const icon = btn.querySelector('i, mat-icon, .material-icons');
                    if (icon && icon.textContent.trim() === 'add') {
                        addBtn = btn;
                        break;
                    }
                }
            }

            if (addBtn) {
                addBtn.click();
                Utils.log('[CONSENT] Clicked ADD', 'info');
                await Utils.sleep(500);
            } else {
                Utils.log('[CONSENT] Khong thay nut ADD - skip consent', 'warn');
                STATE.consentTriggered = true;  // Danh dau da thu, khong thu lai
                return true;  // Van return true de tiep tuc upload
            }

            // Step 2: Click Upload (se trigger consent dialog)
            const uploadBtns = document.querySelectorAll('button');
            let uploadBtn = null;
            const uploadTexts = ['Tải lên', 'Tải ảnh lên', 'Upload', 'upload', 'Từ máy tính', 'From computer'];

            for (const btn of uploadBtns) {
                const text = btn.textContent || '';
                for (const pattern of uploadTexts) {
                    if (text.includes(pattern)) {
                        uploadBtn = btn;
                        break;
                    }
                }
                if (uploadBtn) break;
            }

            if (uploadBtn) {
                uploadBtn.click();
                Utils.log('[CONSENT] Clicked Upload - Cho dialog...', 'info');
                await Utils.sleep(800);
            }

            // Step 3: Click "Tôi đồng ý" neu co
            const buttons = document.querySelectorAll('button');
            let foundConsent = false;
            const consentTexts = ['Tôi đồng ý', 'Đồng ý', 'I agree', 'Agree', 'Accept'];
            for (const btn of buttons) {
                const text = btn.textContent.trim();
                for (const pattern of consentTexts) {
                    if (text === pattern || text.includes(pattern)) {
                        btn.click();
                        Utils.log(`[CONSENT] Clicked "${text}"`, 'success');
                        foundConsent = true;
                        await Utils.sleep(500);
                        break;
                    }
                }
                if (foundConsent) break;
            }

            if (!foundConsent) {
                Utils.log('[CONSENT] Khong thay dialog (co the da dong y truoc do)', 'info');
            }

            // Step 4: ESC 2 lan de dong file dialog
            for (let i = 0; i < 2; i++) {
                document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', keyCode: 27, bubbles: true }));
                await Utils.sleep(300);
            }
            Utils.log('[CONSENT] ESC 2 lan - Done', 'success');

            STATE.consentTriggered = true;
            return true;
        },

        // Helper: Check va click "Tôi đồng ý" neu xuat hien
        checkAndClickConsent: async () => {
            const buttons = document.querySelectorAll('button');
            const consentTexts = ['Tôi đồng ý', 'Đồng ý', 'I agree', 'Agree', 'Accept', 'OK', 'Cho phép', 'Allow'];
            for (const btn of buttons) {
                const text = btn.textContent.trim();
                for (const pattern of consentTexts) {
                    if (text === pattern || text.includes(pattern)) {
                        btn.click();
                        Utils.log('[CONSENT] Clicked consent button: ' + text, 'success');
                        await Utils.sleep(500);
                        return true;
                    }
                }
            }
            return false;
        },

        // Xoa tat ca reference images hien tai truoc khi upload moi
        clearReferenceImages: async () => {
            Utils.log('[CLEAR] Xoa reference images cu...', 'info');

            let deletedCount = 0;
            let maxAttempts = 10;  // Toi da 10 lan xoa

            // Loop de xoa het tat ca reference images
            for (let attempt = 0; attempt < maxAttempts; attempt++) {
                let foundAny = false;

                // Method 1: Tim icon "close" trong toan bo page (cho reference thumbnails)
                const allIcons = document.querySelectorAll('i.google-symbols, mat-icon, .material-icons');
                for (const icon of allIcons) {
                    const text = icon.textContent.trim().toLowerCase();
                    if (text === 'close') {
                        // Check xem icon nay co phai trong reference area khong
                        // (thuong nam trong container nho, khong phai header/dialog)
                        const parent = icon.closest('div');
                        if (parent && parent.offsetWidth < 200 && parent.offsetHeight < 200) {
                            icon.click();
                            deletedCount++;
                            foundAny = true;
                            Utils.log(`[CLEAR] Clicked close icon (attempt ${attempt + 1})`, 'info');
                            await Utils.sleep(500);
                            break;  // Sau moi lan click, bat dau lai tu dau
                        }
                    }
                }

                // Method 2: Tim button voi aria-label chua "delete", "remove", "xoa"
                if (!foundAny) {
                    const deleteButtons = document.querySelectorAll('[aria-label*="delete" i], [aria-label*="remove" i], [aria-label*="xóa" i], [aria-label*="xoa" i]');
                    for (const btn of deleteButtons) {
                        // Check size nho (reference thumbnail)
                        if (btn.offsetWidth < 100 && btn.offsetHeight < 100) {
                            btn.click();
                            deletedCount++;
                            foundAny = true;
                            Utils.log(`[CLEAR] Clicked delete button via aria-label`, 'info');
                            await Utils.sleep(500);
                            break;
                        }
                    }
                }

                // Method 3: Tim nut X trong cac thumbnail nho (50-150px)
                if (!foundAny) {
                    const allDivs = document.querySelectorAll('div');
                    for (const div of allDivs) {
                        const rect = div.getBoundingClientRect();
                        // Reference thumbnails thuong co size 50-150px
                        if (rect.width >= 50 && rect.width <= 150 && rect.height >= 50 && rect.height <= 150) {
                            const closeBtn = div.querySelector('button, [role="button"], i');
                            if (closeBtn && closeBtn.offsetWidth < 40) {
                                closeBtn.click();
                                deletedCount++;
                                foundAny = true;
                                Utils.log(`[CLEAR] Clicked thumbnail close button`, 'info');
                                await Utils.sleep(500);
                                break;
                            }
                        }
                    }
                }

                // Neu khong tim thay gi de xoa, dung lai
                if (!foundAny) {
                    break;
                }
            }

            if (deletedCount > 0) {
                Utils.log(`[CLEAR] Da xoa ${deletedCount} reference images`, 'success');
                await Utils.sleep(500);  // Doi UI update
            } else {
                Utils.log('[CLEAR] Khong tim thay reference images de xoa (co the chua co)', 'info');
            }

            return true;
        },

        uploadReferenceImage: async (base64Data, filename) => {
            Utils.log(`[UPLOAD] Bat dau upload reference: ${filename}`, 'info');

            // Step 1: Click nut "add" (icon add) - thu nhieu selector
            let addBtn = null;

            // Method 1: Tim i.google-symbols voi text "add"
            const addIcons = document.querySelectorAll('i.google-symbols');
            for (const icon of addIcons) {
                if (icon.textContent.trim() === 'add') {
                    addBtn = icon;
                    Utils.log('[UPLOAD] Found ADD via i.google-symbols', 'info');
                    break;
                }
            }

            // Method 2: Tim mat-icon voi text "add"
            if (!addBtn) {
                const matIcons = document.querySelectorAll('mat-icon, .mat-icon, .material-icons');
                for (const icon of matIcons) {
                    if (icon.textContent.trim() === 'add') {
                        addBtn = icon;
                        Utils.log('[UPLOAD] Found ADD via mat-icon', 'info');
                        break;
                    }
                }
            }

            // Method 3: Tim button co icon add ben trong
            if (!addBtn) {
                const allBtns = document.querySelectorAll('button');
                for (const btn of allBtns) {
                    const icon = btn.querySelector('i, mat-icon, .material-icons');
                    if (icon && icon.textContent.trim() === 'add') {
                        addBtn = btn;
                        Utils.log('[UPLOAD] Found ADD via button>icon', 'info');
                        break;
                    }
                }
            }

            // Method 4: Tim theo aria-label
            if (!addBtn) {
                const ariaBtn = document.querySelector('[aria-label*="add" i], [aria-label*="thêm" i], [aria-label*="Thêm" i]');
                if (ariaBtn) {
                    addBtn = ariaBtn;
                    Utils.log('[UPLOAD] Found ADD via aria-label', 'info');
                }
            }

            if (addBtn) {
                addBtn.click();
                Utils.log('[UPLOAD] Clicked ADD button', 'success');
                await Utils.sleep(500);
                // Check consent sau khi click ADD
                await UI.checkAndClickConsent();
            } else {
                // Debug: log all icons found
                Utils.log(`[UPLOAD] DEBUG: Found ${addIcons.length} i.google-symbols icons`, 'warn');
                for (let i = 0; i < Math.min(5, addIcons.length); i++) {
                    Utils.log(`[UPLOAD] Icon ${i}: "${addIcons[i].textContent.trim()}"`, 'info');
                }
                Utils.log('[UPLOAD] Khong tim thay nut ADD', 'error');
                return { success: false, error: 'ADD button not found' };
            }

            // Step 2: Click nut "upload" - thu nhieu text patterns
            await Utils.sleep(300);
            const uploadBtns = document.querySelectorAll('button');
            let uploadBtn = null;
            const uploadTexts = ['Tải lên', 'Tải ảnh lên', 'Upload', 'upload', 'Từ máy tính', 'From computer'];

            for (const btn of uploadBtns) {
                const text = btn.textContent || '';
                for (const pattern of uploadTexts) {
                    if (text.includes(pattern)) {
                        uploadBtn = btn;
                        Utils.log(`[UPLOAD] Found UPLOAD button with text: "${text.trim().slice(0,30)}"`, 'info');
                        break;
                    }
                }
                if (uploadBtn) break;
            }

            // Fallback: tim input[type=file] truc tiep
            if (!uploadBtn) {
                const fileInput = document.querySelector('input[type="file"]');
                if (fileInput) {
                    Utils.log('[UPLOAD] Found file input directly, skipping button click', 'info');
                    // Tiep tuc xuong step 3
                }
            }

            if (uploadBtn) {
                uploadBtn.click();
                Utils.log('[UPLOAD] Clicked UPLOAD button', 'success');
                await Utils.sleep(800);
                // Check consent sau khi click Upload - day la cho hay xuat hien nhat!
                await UI.checkAndClickConsent();
            } else if (!document.querySelector('input[type="file"]')) {
                // Debug: log all buttons
                Utils.log(`[UPLOAD] DEBUG: Found ${uploadBtns.length} buttons`, 'warn');
                for (let i = 0; i < Math.min(5, uploadBtns.length); i++) {
                    const text = uploadBtns[i].textContent || '';
                    Utils.log(`[UPLOAD] Btn ${i}: "${text.trim().slice(0,40)}"`, 'info');
                }
                Utils.log('[UPLOAD] Khong tim thay nut UPLOAD', 'error');
                return { success: false, error: 'UPLOAD button not found' };
            }

            // Step 3: Tim input file - doi them va check consent
            await Utils.sleep(500);
            await UI.checkAndClickConsent();

            let fileInput = document.querySelector('input[type="file"]');

            // Neu khong tim thay, thu doi them va check consent
            if (!fileInput) {
                Utils.log('[UPLOAD] Chua thay file input, doi them...', 'info');
                for (let i = 0; i < 5; i++) {
                    await Utils.sleep(500);
                    await UI.checkAndClickConsent();
                    fileInput = document.querySelector('input[type="file"]');
                    if (fileInput) break;
                }
            }

            if (!fileInput) {
                Utils.log('[UPLOAD] Khong tim thay file input', 'error');
                // ESC de dong dialog neu co
                document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', keyCode: 27, bubbles: true }));
                return { success: false, error: 'File input not found' };
            }

            // Step 4: Tao File tu base64 va set vao input
            try {
                // Decode base64 to binary
                const byteCharacters = atob(base64Data);
                const byteNumbers = new Array(byteCharacters.length);
                for (let i = 0; i < byteCharacters.length; i++) {
                    byteNumbers[i] = byteCharacters.charCodeAt(i);
                }
                const byteArray = new Uint8Array(byteNumbers);

                // Xac dinh MIME type tu filename
                let mimeType = 'image/png';
                if (filename.endsWith('.jpg') || filename.endsWith('.jpeg')) {
                    mimeType = 'image/jpeg';
                } else if (filename.endsWith('.webp')) {
                    mimeType = 'image/webp';
                }

                // Tao File object
                const file = new File([byteArray], filename, { type: mimeType });

                // Set file vao input bang DataTransfer
                const dataTransfer = new DataTransfer();
                dataTransfer.items.add(file);
                fileInput.files = dataTransfer.files;

                // Trigger change event
                fileInput.dispatchEvent(new Event('change', { bubbles: true }));
                fileInput.dispatchEvent(new Event('input', { bubbles: true }));

                Utils.log(`[UPLOAD] Da inject file: ${filename} (${(byteArray.length / 1024).toFixed(1)} KB)`, 'success');

                // Step 5: Doi va click nut "Cắt và lưu" - check consent trong khi doi
                await Utils.sleep(1000);
                await UI.checkAndClickConsent();

                let cropBtn = null;
                for (let attempt = 0; attempt < 10; attempt++) {
                    // Check consent moi lan loop
                    await UI.checkAndClickConsent();

                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        if (btn.textContent.includes('Cắt và lưu')) {
                            cropBtn = btn;
                            break;
                        }
                    }
                    if (cropBtn) break;
                    await Utils.sleep(500);
                }

                if (cropBtn) {
                    cropBtn.click();
                    Utils.log('[UPLOAD] Clicked "Cắt và lưu"', 'success');
                    await Utils.sleep(500);
                    // Check consent sau khi cat va luu
                    await UI.checkAndClickConsent();
                } else {
                    Utils.log('[UPLOAD] Khong tim thay nut "Cắt và lưu" (co the khong can)', 'warn');
                }

                // Step 6: Doi loading xong - dem so div co opacity: 1 trong .sc-51248dda-0
                Utils.log('[UPLOAD] Doi anh load...', 'info');
                const countLoadedImages = () => {
                    const container = document.querySelector('.sc-51248dda-0');
                    if (!container) return 0;
                    const divs = container.querySelectorAll('div[style*="opacity: 1"]');
                    return divs.length;
                };

                const initialCount = countLoadedImages();
                Utils.log(`[UPLOAD] Initial loaded count: ${initialCount}`, 'info');

                // Doi so luong tang len (max 20 giay) - check consent trong khi doi
                for (let i = 0; i < 40; i++) {
                    // Check consent moi 2 giay
                    if (i % 4 === 0) {
                        await UI.checkAndClickConsent();
                    }

                    const currentCount = countLoadedImages();
                    if (currentCount > initialCount) {
                        Utils.log(`[UPLOAD] Anh da load! Count: ${initialCount} -> ${currentCount}`, 'success');
                        break;
                    }
                    await Utils.sleep(500);
                }

                // Doi them 1 chut de dam bao
                await Utils.sleep(1000);
                await UI.checkAndClickConsent();

                Utils.log(`[UPLOAD] Hoan thanh: ${filename}`, 'success');
                return { success: true, filename: filename };
            } catch (e) {
                Utils.log(`[UPLOAD] Loi khi upload: ${e.message}`, 'error');
                return { success: false, error: e.message };
            }
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

            // Log reference files info (reference images da duoc upload truoc qua Python)
            if (referenceFiles && referenceFiles.length > 0) {
                Utils.log(`[REF] Using ${referenceFiles.length} reference(s): ${referenceFiles.join(', ')}`, 'info');
            } else {
                Utils.log(`[REF] No reference files`, 'info');
            }

            // =====================================================================
            // Build JSON prompt - Them reference annotation vao prompt
            // Reference images da duoc upload truoc qua VE3.uploadReferences()
            // Prompt tu Excel da co filename annotation: "James (nv1.png) walking..."
            // =====================================================================
            let textToSend;

            const jsonPayload = {
                prompt: prompt  // Prompt da co annotation tu Python
            };
            textToSend = JSON.stringify(jsonPayload);

            if (referenceFiles && referenceFiles.length > 0) {
                Utils.log(`[JSON MODE] Prompt with ${referenceFiles.length} reference(s)`, 'info');
            } else {
                Utils.log(`[JSON MODE] Prompt without references`, 'info');
            }
            Utils.log(`JSON: ${textToSend.slice(0, 200)}...`, 'info');

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

            // Them prompt_json vao result de Python co the luu vao Excel
            return { ...result, prompt_json: textToSend };
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
            const results = []; // Luu chi tiet result de tra ve cho Python

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
                results.push(result); // Luu lai result (bao gom prompt_json)

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

            // Tra ve ket qua chi tiet neu chi co 1 prompt (cho Python)
            // Bao gom prompt_json de luu vao Excel
            if (total === 1 && results.length === 1) {
                return results[0];
            }

            return { success, failed, results };
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

        // NEW: Lay media info (mediaName + seed) cho 1 scene_id
        getMediaInfo: (sceneId) => {
            const info = STATE.mediaNames[sceneId];
            // Ho tro ca format cu (string) va moi (object)
            if (typeof info === 'string') {
                return { mediaName: info, seed: null };
            }
            return info || null;
        },

        // Legacy: Lay chi mediaName (tuong thich nguoc)
        getMediaName: (sceneId) => {
            const info = STATE.mediaNames[sceneId];
            if (typeof info === 'string') return info;
            return info?.mediaName || null;
        },

        // NEW: Set media info (mediaName + seed) cho 1 scene_id
        setMediaName: (sceneId, mediaName, seed = null) => {
            STATE.mediaNames[sceneId] = { mediaName, seed };
            Utils.log(`Set mediaInfo for ${sceneId}: mediaName=${mediaName ? mediaName.slice(0,40)+'...' : 'NONE'}, seed=${seed}`, 'success');
        },

        // NEW: Set media_names tu Python (load tu cache)
        // Ho tro ca format cu (string) va moi (object with mediaName + seed)
        setMediaNames: (mediaNames) => {
            STATE.mediaNames = { ...STATE.mediaNames, ...mediaNames };
            Utils.log(`Loaded ${Object.keys(mediaNames).length} media_names from cache`, 'success');
        },

        // NEW: Danh dau da setup xong (dung khi navigate ve project cu)
        markSetupDone: () => {
            STATE.isSetupDone = true;
            STATE.projectUrl = window.location.href;
            Utils.log('Marked setup as done (existing project)', 'success');
        },

        // NEW: Trigger consent dialog (goi truoc khi upload lan dau)
        triggerConsent: async () => {
            return await UI.triggerConsent();
        },

        // NEW: Xoa tat ca reference images (goi truoc khi upload)
        clearReferences: async () => {
            return await UI.clearReferenceImages();
        },

        // NEW: Upload anh reference tu base64
        // Python se doc file local, convert sang base64, roi goi ham nay
        // base64Data: string base64 (khong co prefix data:image/...)
        // filename: ten file (vd: nvc.png)
        uploadReference: async (base64Data, filename) => {
            return await UI.uploadReferenceImage(base64Data, filename);
        },

        // NEW: Upload nhieu anh reference
        // images: [{base64: '...', filename: 'nvc.png'}, ...]
        // Returns: {success: boolean, successCount: number, errors: Array<{file, error}>}
        uploadReferences: async (images) => {
            Utils.log(`[UPLOAD] Bat dau upload ${images.length} reference images...`, 'info');

            // QUAN TRONG: Xoa reference images cu truoc khi upload moi
            await UI.clearReferenceImages();

            // Trigger consent truoc khi upload (chi lan dau)
            await UI.triggerConsent();

            if (images.length === 0) {
                return { success: true, successCount: 0, totalCount: 0, errors: [] };
            }

            // Helper: Tìm ADD button ở khu vực INPUT (dưới cùng trong viewport)
            // Có nhiều icon "add" trên trang, cần lấy cái ở dưới cùng
            const findBottomAddButton = () => {
                let addBtn = null;
                let maxY = 0;
                const addIcons = document.querySelectorAll('i.google-symbols');

                for (const icon of addIcons) {
                    if (icon.textContent.trim() === 'add') {
                        const rect = icon.getBoundingClientRect();
                        // Lấy cái trong viewport và có y cao nhất (dưới cùng)
                        if (rect.y < window.innerHeight && rect.y > maxY) {
                            maxY = rect.y;
                            addBtn = icon;
                        }
                    }
                }
                return { addBtn, y: maxY };
            };

            // Helper: Click nút "Tải lên" sau khi panel mở
            const clickUploadButton = async () => {
                await Utils.sleep(500);
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    const text = btn.textContent || '';
                    // Ưu tiên button có ".png" (nút upload thật)
                    if (text.includes('Tải lên') && text.includes('.png')) {
                        btn.click();
                        Utils.log('[UPLOAD] Clicked "Tải lên" button', 'success');
                        return true;
                    }
                }
                // Fallback
                for (const btn of buttons) {
                    const text = btn.textContent || '';
                    if (text.includes('Tải lên') || text.includes('Upload')) {
                        btn.click();
                        Utils.log('[UPLOAD] Clicked upload button (fallback)', 'success');
                        return true;
                    }
                }
                return false;
            };

            let errors = [];
            let successCount = 0;

            // Upload từng file một (vì file input không hỗ trợ multiple)
            for (let i = 0; i < images.length; i++) {
                const img = images[i];
                Utils.log(`[UPLOAD] Uploading ${i+1}/${images.length}: ${img.filename}`, 'info');

                try {
                    // Step 1: Tìm và click ADD button (dưới cùng viewport)
                    const { addBtn, y } = findBottomAddButton();
                    if (!addBtn) {
                        Utils.log('[UPLOAD] Khong tim thay nut ADD trong viewport', 'error');
                        errors.push({ file: img.filename, error: 'ADD button not found' });
                        continue;
                    }

                    addBtn.click();
                    Utils.log(`[UPLOAD] Clicked ADD at y=${y}`, 'info');
                    await Utils.sleep(600);

                    // Step 2: Click nút "Tải lên"
                    const uploadClicked = await clickUploadButton();
                    if (!uploadClicked) {
                        Utils.log('[UPLOAD] Khong tim thay nut "Tải lên"', 'error');
                        errors.push({ file: img.filename, error: '"Tải lên" button not found' });
                        continue;
                    }
                    await Utils.sleep(600);

                    // Check consent
                    await UI.checkAndClickConsent();
                    await Utils.sleep(300);

                    // Step 3: Find file input
                    let fileInput = document.querySelector('input[type="file"]');
                    if (!fileInput) {
                        for (let j = 0; j < 5; j++) {
                            await Utils.sleep(400);
                            fileInput = document.querySelector('input[type="file"]');
                            if (fileInput) break;
                        }
                    }

                    if (!fileInput) {
                        Utils.log('[UPLOAD] Khong tim thay file input', 'error');
                        errors.push({ file: img.filename, error: 'File input not found' });
                        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', keyCode: 27, bubbles: true }));
                        continue;
                    }

                    // Step 4: Create File and upload
                    const byteCharacters = atob(img.base64);
                    const byteNumbers = new Array(byteCharacters.length);
                    for (let j = 0; j < byteCharacters.length; j++) {
                        byteNumbers[j] = byteCharacters.charCodeAt(j);
                    }
                    const byteArray = new Uint8Array(byteNumbers);

                    let mimeType = 'image/png';
                    if (img.filename.endsWith('.jpg') || img.filename.endsWith('.jpeg')) {
                        mimeType = 'image/jpeg';
                    } else if (img.filename.endsWith('.webp')) {
                        mimeType = 'image/webp';
                    }

                    const file = new File([byteArray], img.filename, { type: mimeType });
                    const dataTransfer = new DataTransfer();
                    dataTransfer.items.add(file);
                    fileInput.files = dataTransfer.files;

                    // Trigger events
                    fileInput.dispatchEvent(new Event('change', { bubbles: true }));
                    fileInput.dispatchEvent(new Event('input', { bubbles: true }));

                    // Step 5: Wait for crop dialog and click "Cắt và lưu"
                    // Button có icon material-icons với text "crop"
                    await Utils.sleep(1000);
                    let cropClicked = false;
                    for (let attempt = 0; attempt < 10; attempt++) {
                        const cropBtn = [...document.querySelectorAll('button')].find(b => {
                            const icon = b.querySelector('i.material-icons');
                            return icon && icon.textContent.trim() === 'crop';
                        });
                        if (cropBtn) {
                            cropBtn.click();
                            Utils.log(`[UPLOAD] Clicked "Cắt và lưu" button`, 'success');
                            cropClicked = true;
                            break;
                        }
                        await Utils.sleep(300);
                    }

                    if (!cropClicked) {
                        Utils.log(`[UPLOAD] Warning: "Cắt và lưu" button not found, continuing...`, 'warn');
                    }

                    // Step 6: Doi loading xong - dem so div co opacity: 1 trong .sc-51248dda-0
                    Utils.log('[UPLOAD] Doi anh load...', 'info');
                    const countLoadedImages = () => {
                        const container = document.querySelector('.sc-51248dda-0');
                        if (!container) return 0;
                        const divs = container.querySelectorAll('div[style*="opacity: 1"]');
                        return divs.length;
                    };

                    const initialCount = countLoadedImages();

                    // Doi so luong tang len (max 20 giay)
                    for (let w = 0; w < 40; w++) {
                        // Check consent moi 2 giay
                        if (w % 4 === 0) {
                            await UI.checkAndClickConsent();
                        }

                        const currentCount = countLoadedImages();
                        if (currentCount > initialCount) {
                            Utils.log(`[UPLOAD] Anh da load! Count: ${initialCount} -> ${currentCount}`, 'success');
                            break;
                        }
                        await Utils.sleep(500);
                    }

                    // Doi them 1 chut de dam bao
                    await Utils.sleep(1000);
                    await UI.checkAndClickConsent();

                    successCount++;
                    Utils.log(`[UPLOAD] ✓ ${img.filename} thanh cong`, 'success');

                    // Wait for UI to settle before next file (ADD button reappear)
                    if (i < images.length - 1) {
                        Utils.log('[UPLOAD] Cho UI san sang cho file tiep theo...', 'info');
                        await Utils.sleep(2000);
                    }

                } catch (e) {
                    errors.push({ file: img.filename, error: e.message });
                    Utils.log(`[UPLOAD] ✗ ${img.filename}: ${e.message}`, 'error');
                }
            }

            Utils.log(`[UPLOAD] Hoan thanh: ${successCount}/${images.length} thanh cong`, successCount > 0 ? 'success' : 'error');

            return {
                success: successCount > 0,
                successCount: successCount,
                totalCount: images.length,
                errors: errors
            };
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
