# VE3 Tool - Hướng dẫn làm việc với nhiều Session

## Vấn đề
- Mỗi Claude session có branch riêng
- Cần sync code giữa các session

## Giải pháp

### Branch chung để sync:
```
claude/ve3-image-generation-vmOC4
```

### Workflow

#### Khi BẮT ĐẦU session mới:
```cmd
cd D:\AUTO\ve3-tool-1912\ve3-tool
SYNC.bat
```
Hoặc:
```cmd
git fetch --all
git reset --hard origin/claude/ve3-image-generation-vmOC4
```

#### Khi MUỐN LƯU thay đổi:
```cmd
PUSH.bat
```
Hoặc:
```cmd
git add -A
git commit -m "Mo ta thay doi"
git push origin HEAD
```

#### Khi RUN tool:
```cmd
RUN.bat
```
(Tự động pull code mới nhất)

## Lệnh nhanh

| Mục đích | Lệnh |
|----------|------|
| Xem branch hiện tại | `git branch` |
| Xem thay đổi | `git status` |
| Xem commits gần nhất | `git log --oneline -5` |
| Xem tất cả branches | `git branch -a` |
| Sync code | `SYNC.bat` hoặc `git pull origin claude/ve3-image-generation-vmOC4` |
| Push code | `PUSH.bat` |

## Lưu ý
- Chạy `SYNC.bat` đầu mỗi session để có code mới nhất
- Chạy `PUSH.bat` khi muốn lưu thay đổi
- `RUN.bat` sẽ tự động sync trước khi chạy tool
