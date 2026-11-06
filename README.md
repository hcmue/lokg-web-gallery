# LOKG-IR Web Gallery - HCMUE

**Trang chính:** https://hcmue.github.io/lokg-web-gallery/  
**Backend:** FastAPI trên Render, URL `https://<service>.onrender.com` do chủ dự án cấu hình.  
**Giáo viên:** `https://<service>.onrender.com/admin`.  
**Mã nguồn và 72 học liệu demo:** repository `hcmue/lokg-web-gallery`.

## Triển khai

Đọc **[HUONG_DAN_TRIEN_KHAI_HCMUE.md](HUONG_DAN_TRIEN_KHAI_HCMUE.md)** để có đầy đủ lệnh Git, cấu hình GitHub Pages `/docs`, Render, CORS, analytics PostgreSQL và kiểm tra sự cố.

### 1. GitHub Pages

- Repo phải nằm trong tổ chức **hcmue** và có tên **lokg-web-gallery**.
- Settings → Pages → Deploy from a branch → `main` → `/docs`.
- Trang chủ thật là `docs/index.html`, dùng `docs/assets/app.js` gọi API Render.
- 72 mẫu HTML ở `docs/pages/`, ảnh WebP ở `docs/previews/`.
- Trước khi cấu hình Render, trang vẫn hiển thị 72 mẫu **chế độ duyệt tĩnh**, không phải kết quả LOKG-IR.

### 2. Render

- Connect repository GitHub `hcmue/lokg-web-gallery`; Auto Deploy **On Commit**.
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- `PUBLIC_FRONTEND_ORIGIN=https://hcmue.github.io` để cho phép trình duyệt GitHub Pages gọi API qua CORS.
- Metadata `data/catalog.yaml` được lưu trên GitHub; nguồn dữ liệu của Admin dùng GitHub Contents API.

### 3. Gắn URL Render vào trang chủ

Sửa `docs/config.js`, thay `https://REPLACE-WITH-YOUR-RENDER-SERVICE.onrender.com` bằng địa chỉ dịch vụ Render thực tế và push lại GitHub.

### 4. Thống kê

Trang chủ gọi `/api/stats/public`, ghi sự kiện qua `/api/analytics/visit`. Ghi số lượt truy cập cần `ANALYTICS_ENABLED=true`, `DATABASE_URL` PostgreSQL và `ANALYTICS_SECRET`. Chưa cấu hình thì giao diện vẫn sử dụng được, chỉ không có bộ đếm.

## Cấu trúc

```text
docs/    -> GitHub Pages: index.html, config.js, assets/, pages/, previews/
app/     -> FastAPI, tra cứu bằng lõi đồ thị LOKG-IR thích nghi từ mã MIWAI
app/static/admin.html -> quản trị giáo viên do Render phục vụ
data/catalog.yaml -> 72 liên kết HCMUE demo, giáo viên có thể cập nhật qua Admin
tests/   -> unit/integration tests
render.yaml -> Render Blueprint, Auto Deploy: commit
```

## Chạy thử local

```bash
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
# Windows PowerShell: Copy-Item .env.example .env
python -m pytest -q
uvicorn app.main:app --reload
```

Cấu hình `.env` trước, không commit mật khẩu, PAT hay chuỗi kết nối cơ sở dữ liệu. Khi phát triển frontend tĩnh riêng, chạy `python -m http.server 5500 -d docs`; nếu muốn trỏ về backend local, thay `docs/config.js` thành `http://127.0.0.1:8000` (chỉ dùng ở localhost) và đặt `PUBLIC_FRONTEND_ORIGIN=http://127.0.0.1:5500` trong backend `.env`.

## Giới hạn học thuật và riêng tư

- LOKG-IR dùng điểm văn bản TF-IDF và quan hệ từ metadata nhập tay; **không chạy toàn bộ pipeline CLIP** của bài báo gốc.
- Không tải lên hoặc phân tích nội dung giao diện từ URL; giáo viên chịu trách nhiệm từ khóa.
- 72 mẫu là **dữ liệu minh họa**, không phải minh chứng số lượng sinh viên đã dùng hay tác động học tập.
- Bộ đếm chỉ phản ánh sự kiện trình duyệt; không phải số người học duy nhất. Không lưu IP người dùng vào bảng sự kiện; truy vấn được làm sạch một số dạng định danh phổ biến trước khi lưu.
