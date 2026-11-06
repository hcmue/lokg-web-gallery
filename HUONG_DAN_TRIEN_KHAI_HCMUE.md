# TRIỂN KHAI LOKG-IR WEB GALLERY TẠI HCMUE

**Mục tiêu**

- Trang chính (sinh viên): **https://hcmue.github.io/lokg-web-gallery/**
- 72 mẫu giao diện: `https://hcmue.github.io/lokg-web-gallery/pages/WEB-ECO-001.html`, v.v.
- Backend FastAPI: `https://<TEN-DICH-VU>.onrender.com` (tên cụ thể do Render cấp)
- Giáo viên đăng nhập tại `https://<TEN-DICH-VU>.onrender.com/admin`
- GitHub repository: `https://github.com/hcmue/lokg-web-gallery`

> Yêu cầu: tài khoản GitHub có quyền tạo hoặc push vào repository thuộc tổ chức `hcmue`. Không thể tạo trang ở `hcmue.github.io` chỉ bằng cách push vào tài khoản GitHub cá nhân.

## 1. Cấu trúc dự án

```text
lokg-web-gallery/
├── docs/                      # GitHub Pages xuất bản toàn bộ thư mục này
│   ├── index.html             # TRANG CHÍNH công khai
│   ├── config.js              # Địa chỉ API Render (công khai)
│   ├── gallery-fallback.json  # 72 mẫu để duyệt tĩnh khi Render chưa hoạt động
│   ├── privacy.html
│   ├── assets/
│   │   ├── app.js             # Gọi API tìm kiếm và bộ đếm
│   │   ├── styles.css
│   │   └── favicon.svg
│   ├── pages/                 # 72 mẫu HTML/CSS
│   └── previews/              # 72 ảnh WebP
├── app/                       # FastAPI + lõi truy hồi LOKG-IR
├── data/catalog.yaml          # Đã khai báo 72 liên kết HCMUE, chỉnh bằng Admin
├── tests/                     # Kiểm thử tự động
├── render.yaml                # Render Blueprint và Auto Deploy
├── requirements.txt
└── .env.example               # Biến cấu hình mẫu, KHÔNG chứa secrets thật
```

**Quan trọng:** `docs/index.html` là frontend thật tại GitHub Pages. `app/static/student.html` chỉ là trang dự phòng cũ trên máy chủ Render. URL chính người học sử dụng là GitHub Pages.

## 2. Tải mã nguồn và tạo GitHub repository

**Cách A — repository `hcmue/lokg-web-gallery` đã có sẵn (khuyên dùng nếu đã tạo).**

Mở **PowerShell**:

```powershell
cd D:\Projects
git clone https://github.com/hcmue/lokg-web-gallery.git
cd lokg-web-gallery
```

Chép toàn bộ nội dung thư mục dự án sau khi giải nén ZIP vào repository vừa clone, **không chép cả thư mục cha thành thư mục con**. Bạn phải nhìn thấy `docs`, `app`, `data`, `render.yaml` ngay tại gốc repository. Sau đó:

```powershell
git status
git add .
git commit -m "Add HCMUE LOKG-IR GitHub Pages frontend and FastAPI"
git push origin main
```

**Cách B — repository chưa tồn tại.**

1. Trên GitHub, tạo repository tên `lokg-web-gallery`, **Owner: hcmue**, Visibility: Public.
2. Không tạo README hoặc `.gitignore` tự động nếu dự định push thư mục dự án mới.
3. Giải nén ZIP vào `D:\Projects\lokg-web-gallery`, mở PowerShell tại đây và chạy:

```powershell
cd D:\Projects\lokg-web-gallery
git init
git branch -M main
git add .
git commit -m "Initial HCMUE LOKG-IR Web Gallery"
git remote add origin https://github.com/hcmue/lokg-web-gallery.git
git push -u origin main
```

**Kiểm tra:** Trên `https://github.com/hcmue/lokg-web-gallery`, phải nhìn thấy thư mục `docs` và tệp `docs/index.html`.

Nếu bị `Permission denied` hoặc HTTP 403, tài khoản hiện tại chưa có quyền push trong tổ chức `hcmue`. Hãy xin quyền *Write* (hoặc tạo repo bởi quản trị viên), rồi thử lại.

## 3. Bật GitHub Pages — frontend chính

Vào repository GitHub → **Settings → Pages**:

1. **Build and deployment → Source:** `Deploy from a branch`.
2. **Branch:** `main`.
3. **Folder:** `/docs`.
4. Nhấn **Save**.
5. Kiểm tra quá trình trong tab **Actions** nếu cần.

Khi build thành công, kiểm tra:

- **Trang chủ:** https://hcmue.github.io/lokg-web-gallery/
- **Mẫu 1:** https://hcmue.github.io/lokg-web-gallery/pages/WEB-ECO-001.html
- **Ảnh xem trước:** https://hcmue.github.io/lokg-web-gallery/previews/WEB-ECO-001.webp

Trang chủ có thể hiển thị danh mục tĩnh ngay cả trước khi có Render. Dòng “Chưa cấu hình địa chỉ Render” là trạng thái dự kiến ở giai đoạn này, không phải lỗi build Pages.

## 4. Tạo backend FastAPI trên Render

1. Vào https://dashboard.render.com/ → **New → Web Service** (hoặc New → Blueprint nếu sử dụng `render.yaml`).
2. Connect GitHub và chọn repository `hcmue/lokg-web-gallery`, branch `main`.
3. Nếu cấu hình thủ công, đặt:

| Trường | Giá trị |
|---|---|
| Language / Runtime | Python |
| Root directory | Để trống (gốc repo) |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/health` |
| Auto-Deploy | On Commit |

4. Trong mục **Environment**, thêm:

| Tên biến | Giá trị |
|---|---|
| `APP_ENV` | `production` |
| `CATALOG_BACKEND` | `github` |
| `GITHUB_REPOSITORY` | `hcmue/lokg-web-gallery` |
| `GITHUB_BRANCH` | `main` |
| `GITHUB_CATALOG_PATH` | `data/catalog.yaml` |
| `GITHUB_TOKEN` | Fine-grained token bí mật được cấp quyền `Contents: Read and write` cho repo |
| `ALLOWED_PAGE_HOSTS` | `hcmue.github.io` |
| `PUBLIC_FRONTEND_ORIGIN` | `https://hcmue.github.io` **(không có `/lokg-web-gallery`)** |
| `ADMIN_PASSWORD` | Mật khẩu mạnh, riêng tư, tối thiểu 16 ký tự |
| `SESSION_SECRET` | Khóa ngẫu nhiên tối thiểu 32 ký tự |
| `ANALYTICS_ENABLED` | `true` nếu đã có PostgreSQL; `false` nếu chưa cấu hình DB |
| `DATABASE_URL` | Chuỗi kết nối PostgreSQL, chỉ cần khi bật Analytics |
| `ANALYTICS_SECRET` | Khóa ngẫu nhiên tối thiểu 32 ký tự khi bật Analytics |
| `ANALYTICS_RETENTION_DAYS` | `90` |

**Tạo token:** GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens. Chọn repo thuộc tổ chức `hcmue`, quyền **Contents: Read and write**. Tổ chức có thể yêu cầu người quản trị phê duyệt token. Token không được đưa vào `docs/config.js`, Git commit hoặc mã JavaScript.

**Thống kê:** Bản `render.yaml` đã để `ANALYTICS_ENABLED=false` mặc định để triển khai không bị phụ thuộc cơ sở dữ liệu. Khi có PostgreSQL (ví dụ Supabase, Neon hoặc Render), thêm `DATABASE_URL` và chuyển `ANALYTICS_ENABLED=true` trong Render Environment; đồng bộ lại `render.yaml` nếu sau này cập nhật bằng Blueprint. Nếu bật thống kê mà thiếu `DATABASE_URL`, ứng dụng sẽ không khởi động.

Khi Render deploy thành công, kiểm tra:

```text
https://TEN-DICH-VU.onrender.com/api/health
https://TEN-DICH-VU.onrender.com/api/meta
https://TEN-DICH-VU.onrender.com/api/search?query=navbar&mode=lokg
https://TEN-DICH-VU.onrender.com/admin
```

`/api/health` phải báo `ok: true`, `items: 72` nếu danh mục chưa bị sửa/xóa. Nếu kết quả bằng 0, vào Admin → Tải lại dữ liệu, hoặc kiểm tra `data/catalog.yaml` và token GitHub.

## 5. Kết nối frontend Pages với Render

Mở **`docs/config.js`**, thay đúng **một chuỗi địa chỉ**:

```javascript
window.LOKG_CONFIG = Object.freeze({
  API_BASE_URL: "https://TEN-DICH-VU.onrender.com",
  PUBLIC_SITE_URL: "https://hcmue.github.io/lokg-web-gallery/",
  RESULT_LIMIT: 12
});
```

Lưu lại và push:

```powershell
git add docs/config.js
git commit -m "Connect HCMUE GitHub Pages with Render API"
git push origin main
```

GitHub Pages tự cập nhật trang chủ. Render cũng được cấu hình **On Commit**, nên mọi commit `main` có thể trigger rebuild Render (kể cả chỉ sửa `docs/config.js` hay `data/catalog.yaml`). Nếu về sau muốn tránh rebuild vì metadata, có thể dùng Render Build Filters; hiện bản này cố ý giữ **On Commit** theo yêu cầu.

**Bắt buộc kiểm tra CORS:** khi mở trang ở GitHub Pages, nhấn F12 → Network → `api/search`; phản hồi phải có header `access-control-allow-origin: https://hcmue.github.io`. Trong Render, biến `PUBLIC_FRONTEND_ORIGIN` phải là **origin**, không phải URL đầy đủ có đường dẫn.

## 6. Kiểm tra bộ đếm lượt truy cập (PostgreSQL)

Khi đã có PostgreSQL và các biến `DATABASE_URL`, `ANALYTICS_ENABLED=true`, `ANALYTICS_SECRET`, Render sẽ tự tạo bảng thống kê (nếu tài khoản DB có quyền tạo bảng) khi khởi động.

Mở GitHub Pages, đợi load danh mục và kiểm tra:

- “Lượt mở trang” và “Lượt tìm kiếm” trên trang chủ.
- `GET https://TEN-DICH-VU.onrender.com/api/stats/public`.
- `POST https://TEN-DICH-VU.onrender.com/api/analytics/visit` từ GitHub Pages (trình duyệt tạo mã ngẫu nhiên, backend HMAC hash theo ngày; không cần cookie cross-site).
- Giáo viên xem số liệu tại `https://TEN-DICH-VU.onrender.com/admin`.

Cần phân biệt **lượt mở trang** (khử trùng 30 giây trên cùng trình duyệt) với **số người thực**. Tránh yêu cầu người học nhập thông tin cá nhân trong ô tìm kiếm. Các lượt truy cập trực tiếp vào 72 HTML trên GitHub Pages không được backend ghi nhận là truy cập trang chính.

## 7. Cập nhật sau khi triển khai

**Sửa frontend:**

```powershell
git add docs
git commit -m "Improve public search frontend"
git push origin main
```

**Sửa backend:**

```powershell
git add app requirements.txt render.yaml
git commit -m "Update FastAPI search backend"
git push origin main
```

**Giáo viên nhập học liệu:** Vào `https://TEN-DICH-VU.onrender.com/admin`, đăng nhập, nhập URL trên HCMUE Pages và từ khóa. FastAPI sẽ commit `data/catalog.yaml` qua GitHub Contents API, rồi cập nhật chỉ mục. Với **On Commit**, commit dữ liệu này cũng sẽ trigger Render rebuild; không mất dữ liệu vì YAML nằm trên GitHub, số liệu thống kê nằm trên PostgreSQL.

## 8. Khắc phục nhanh

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| GitHub Pages 404 | Chưa tạo repo đúng Owner hoặc chưa bật `main /docs` | Kiểm tra Settings → Pages và quyền repository |
| Trang hiển thị 72 mẫu nhưng ghi “Danh mục tĩnh” | Chưa sửa `docs/config.js` hoặc API lỗi | Sửa URL Render, xem `/api/health`, bấm “Kết nối lại API” |
| CORS error | `PUBLIC_FRONTEND_ORIGIN` sai hoặc backend chưa deploy mới | Đặt `https://hcmue.github.io`, restart/redeploy Render |
| `/api/health` lỗi 503 | Thiếu GitHub Token/Password/DB hoặc đang cold start | Kiểm tra Render Logs, Env; nếu chưa có DB đặt Analytics false |
| Admin không lưu được YAML | Token thiếu Contents:write hoặc org chưa duyệt token | Kiểm tra token, branch protection, quyền ghi |
| Bộ đếm là `—` | Analytics tắt hoặc PostgreSQL chưa sẵn sàng | Bật Analytics, đặt `DATABASE_URL` và `ANALYTICS_SECRET` |
| Trang mở được nhưng kết quả rỗng | Danh mục chưa có hoặc chưa reload từ GitHub | Kiểm tra `data/catalog.yaml` có 72 mục, sử dụng `/admin` refresh |

## 9. Lưu ý minh chứng hồ sơ sáng kiến

- 72 giao diện trong bộ source là **dữ liệu demo tự tạo**, không tự động là số liệu giảng dạy thực tế.
- Lưu ảnh chụp **trang GitHub Pages**, **trang Render Admin**, **kết quả truy vấn**, và **báo cáo thống kê thật** sau khi triển khai.
- Ghi rõ sự khác nhau giữa **số lượt sử dụng** và **hiệu quả học tập**. Hiệu quả cần có thử nghiệm so sánh trước–sau.
- Lõi MIWAI được tái sử dụng cho duyệt đồ thị tri thức; bản triển khai Web dùng TF-IDF văn bản từ metadata thay cho CLIP ảnh nên không tương đương hoàn toàn cấu hình nghiên cứu trên Visual Genome.
