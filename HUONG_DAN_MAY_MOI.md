# HƯỚNG DẪN CÀI ĐẶT VE3 TOOL TRÊN MÁY MỚI

## BƯỚC 1: CÀI ĐẶT PHẦN MỀM CƠ BẢN

### 1.1 Cài Python
1. Vào: https://www.python.org/downloads/
2. Tải Python 3.11 hoặc mới hơn
3. Chạy file cài đặt
4. **QUAN TRỌNG**: Tick vào ô "Add Python to PATH"
5. Click Install

### 1.2 Cài Node.js
1. Vào: https://nodejs.org/
2. Tải bản LTS (khuyến nghị)
3. Chạy file cài đặt
4. Next > Next > Install

### 1.3 Cài Git
1. Vào: https://git-scm.com/downloads
2. Tải cho Windows
3. Chạy file cài đặt
4. Next > Next > Install (giữ mặc định)

### 1.4 Kiểm tra đã cài xong
Mở CMD (Windows + R, gõ cmd, Enter) và chạy:
```
python --version
node --version
git --version
```
Nếu cả 3 đều hiện version = OK

---

## BƯỚC 2: TẢI VE3 TOOL

### 2.1 Tạo thư mục làm việc
```
mkdir D:\AUTO
cd D:\AUTO
```

### 2.2 Clone tool
```
git clone https://github.com/criggerbrannon-hash/ve3-tool.git
cd ve3-tool
```

### 2.3 Cài thư viện Python
```
pip install -r requirements.txt
```

### 2.4 Cài imagefx-api
```
npm i -g @rohitaryal/imagefx-api
```

---

## BƯỚC 3: ĐỒNG BỘ CODE TỪ CÁC SESSION

### 3.1 Lần đầu tiên
```
git fetch --all
git checkout claude/ve3-image-generation-vmOC4
```

### 3.2 Mỗi khi có session mới
1. Chạy file `ADD_BRANCH.bat`
2. Paste tên branch mà Claude nói (ví dụ: claude/image-generation-api-t0qZp)
3. Enter

---

## BƯỚC 4: CHẠY TOOL

### Cách 1: Double-click
Mở thư mục ve3-tool, double-click `RUN.bat`

### Cách 2: CMD
```
cd D:\AUTO\ve3-tool
python ve3_pro.py
```

---

## CÁC FILE QUAN TRỌNG

| File | Mục đích |
|------|----------|
| `RUN.bat` | Chạy tool (tự động sync code) |
| `ADD_BRANCH.bat` | Thêm branch session mới |
| `SYNC.bat` | Đồng bộ code thủ công |
| `PUSH.bat` | Đẩy code lên server |
| `config/settings.yaml` | Cấu hình tool |
| `config/sync_branches.txt` | Danh sách branches |

---

## XỬ LÝ LỖI THƯỜNG GẶP

### Lỗi "python is not recognized"
- Cài lại Python, nhớ tick "Add to PATH"
- Hoặc chạy: `set PATH=%PATH%;C:\Python311`

### Lỗi "git is not recognized"
- Cài lại Git
- Khởi động lại CMD

### Lỗi "npm is not recognized"
- Cài lại Node.js
- Khởi động lại CMD

### Lỗi khi clone
```
git config --global http.sslVerify false
git clone https://github.com/criggerbrannon-hash/ve3-tool.git
```

---

## TÓM TẮT LỆNH

```cmd
:: === MÁY MỚI - CHẠY 1 LẦN ===
mkdir D:\AUTO
cd D:\AUTO
git clone https://github.com/criggerbrannon-hash/ve3-tool.git
cd ve3-tool
pip install -r requirements.txt
npm i -g @rohitaryal/imagefx-api
git fetch --all
git checkout claude/ve3-image-generation-vmOC4

:: === HÀNG NGÀY ===
cd D:\AUTO\ve3-tool
RUN.bat
```
