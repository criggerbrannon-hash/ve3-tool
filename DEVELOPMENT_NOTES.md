# VE3 Tool - Development Notes

## Version 1.0 (2024-12-31)
**Status: WORKING - Production Ready**

---

## Tính năng chính đã hoàn thành

### 1. Image Generation (Tạo ảnh)
- Sử dụng Google Flow API qua DrissionPage browser automation
- Proxy Webshare rotating (random IP mode)
- Xử lý 403/reCAPTCHA: Kill Chrome → Đổi IP → Restart
- Retry tự động khi fail

### 2. Video Generation (I2V - Image to Video)
- Sử dụng Google Flow API (Image to Video)
- Proxy Webshare rotating (random IP mode)
- Xử lý 403: Reset proxy + Restart Chrome (giống image gen)
- Retry tự động khi fail

### 3. Director System (Đạo diễn AI)
- AI phân tích truyện → tạo shooting plan
- Chia scenes thông minh (2-8s mỗi scene)
- Progressive save: lưu từng phần ngay khi xong

### 4. Gap Filling (Lấp gaps khi API fail)
- Step 1.5: AI tạo backup scenes trước (có character/location mapping)
- Detect timeline gaps (khoảng thời gian không có scene)
- Auto-retry 3 lần với backup data
- Force fill: đảm bảo 100% scenes có prompt

---

## Kiến trúc chính

```
ve3_pro.py              # Entry point chính
├── modules/
│   ├── smart_engine.py         # Engine điều phối chính
│   ├── prompts_generator.py    # AI tạo prompts + gap filling
│   ├── drission_flow_api.py    # Google Flow API (image + video)
│   ├── excel_manager.py        # Quản lý Excel (scenes, characters)
│   ├── browser_flow_generator.py  # Browser automation
│   └── image_to_video.py       # I2V conversion
├── webshare_proxy.py    # Webshare proxy management
└── proxy_bridge.py      # Proxy bridge server
```

---

## Cấu hình Proxy (Webshare Rotating)

```yaml
# config/settings.yaml
webshare:
  enabled: true
  mode: "rotating"  # rotating | direct
  rotating_endpoint: "p.webshare.io:80"
  username: "xxx-rotate"
  password: "xxx"
  random_ip: true  # Random IP mỗi request
```

---

## Flow xử lý 403 Error

### Image Generation:
1. Gặp 403 → Kill Chrome
2. Random IP mode: Restart Chrome (IP tự đổi)
3. Sticky Session mode: Tăng session ID → Restart
4. Direct proxy mode: Xoay IP qua API → Restart

### Video Generation (đã fix giống image):
1. Gặp 403 → Kill Chrome
2. Random IP mode: Restart Chrome (IP tự đổi)
3. Sticky Session mode: Tăng session ID → Restart
4. Direct proxy mode: Xoay IP qua API → Restart

---

## Gap Filling Flow

```
Step 1.5: AI Backup ──→ Lưu director_plan (có char/loc/prompt)
     ↓
Step 2-3: Director ──→ Tạo scenes (có thể fail)
     ↓
Gap Detection ──→ Tìm gaps trong timeline
     ↓
Gap Retry (x3) ──→ Fill từ backup (timestamp + text match)
                   └→ Nếu không có backup → dùng fallback method
     ↓
FORCE FILL ──→ Fill TẤT CẢ gaps còn lại
     ↓
✓ 100% scenes có prompt
```

---

## Commits quan trọng (Version 1.0)

- `dd5bb99` - Fix video 403: Reset proxy and restart Chrome
- `60735cb` - Improve gap filling to ensure ALL scenes get quality prompts
- `0406abb` - Replace keyword-based backup with AI-powered backup prompts
- `175df1f` - Add backup scenes with character/location/shot-type mapping
- `27dbaa4` - Add progressive save for director parts

---

## Các vấn đề đã biết (để fix sau)

1. **Proxy rotation**: Đôi khi cần nhiều lần rotate mới được IP tốt
2. **reCAPTCHA**: Một số IP bị block nhanh hơn những IP khác
3. **Gap detection**: Có thể miss một số edge cases với timestamps lạ

---

## Cách chạy

```bash
# Chạy tool
python ve3_pro.py

# Hoặc với GUI
python main_tab.py
```

---

## Session tiếp theo có thể làm

- [ ] Thêm retry thông minh hơn cho video (detect pattern fail)
- [ ] Cải thiện AI backup prompts quality
- [ ] Thêm monitoring/logging tốt hơn
- [ ] Optimize parallel processing

---

*Last updated: 2024-12-31*
