# 🎨 VE3 Tool Pro

**Voice → Images** - Tự động tạo ảnh từ file voice/audio

## ✨ Tính năng

- 🎤 **Voice to SRT** - Chuyển audio thành phụ đề
- 📝 **SRT to Prompts** - AI tạo prompt từ nội dung
- 🖼️ **Prompts to Images** - Tạo ảnh bằng Google Flow
- 🚀 **1 Click** - Tự động toàn bộ quy trình
- ⚡ **Song song** - Nhiều accounts chạy cùng lúc

## 🔧 Cài đặt

### Yêu cầu
- Python 3.8+
- Git
- Chrome browser (đã đăng nhập Google)

### Setup nhanh

1. **Tải launcher:**
   ```
   Tạo folder C:\VE3Tool\
   Tải RUN.bat vào folder này
   ```

2. **Chạy lần đầu:**
   ```
   Double-click RUN.bat
   Sẽ tự động tải code và tạo file config
   ```

3. **Cấu hình:**
   - Mở `C:\VE3Tool\config\accounts.json`
   - Thêm Chrome profile paths
   - Thêm Groq API key (free: https://console.groq.com/keys)

4. **Chạy:**
   ```
   Double-click RUN.bat
   Chọn file voice → Bắt đầu!
   ```

## 📁 Cấu trúc

```
C:\VE3Tool\
├── RUN.bat              ← Launcher (không đổi)
├── config/
│   └── accounts.json    ← Config của bạn (giữ nguyên khi update)
├── PROJECTS/            ← Output (giữ nguyên khi update)
└── code/                ← Code (tự động update)
```

## ⚙️ Config

File `config/accounts.json`:

```json
{
    "chrome_path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "chrome_profiles": [
        "C:\\Users\\YOUR_NAME\\AppData\\Local\\Google\\Chrome\\User Data\\Profile 1"
    ],
    "api_keys": {
        "groq": ["gsk_YOUR_KEY"],
        "gemini": []
    },
    "settings": {
        "parallel": 2,
        "delay_between_images": 2
    }
}
```

### Tìm Chrome Profile Path:
1. Mở Chrome
2. Vào `chrome://version`
3. Tìm "Profile Path"
4. Copy đường dẫn

### Lấy Groq API Key (FREE):
1. Vào https://console.groq.com/keys
2. Tạo API key mới
3. Copy và dán vào config

## 📝 Sử dụng

1. Chạy `RUN.bat`
2. Chọn file voice (.mp3, .wav) hoặc thư mục
3. Click **BẮT ĐẦU**
4. Đợi tool tự động:
   - Lấy token từ Chrome
   - Chuyển voice → SRT
   - Tạo prompts bằng AI
   - Tạo ảnh

## 🔄 Update

Code tự động update mỗi lần chạy `RUN.bat`.

Config và Projects của bạn **không bị ảnh hưởng**.

## 📜 License

MIT

## 🤝 Author

Developed with Claude AI
