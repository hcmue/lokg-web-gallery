# HƯỚNG DẪN TRIỂN KHAI LOKG-IR — GITHUB PAGES, RENDER VÀ THỐNG KÊ

**Phiên bản:** LOKG-IR Web Links + Usage Analytics.  
**Mục tiêu:** Giảng viên nhập URL GitHub Pages + từ khóa; sinh viên tìm kiếm tại trang chủ FastAPI trên Render, xem bộ đếm lượt truy cập; quản trị viên xem và xuất thống kê CSV.

## 0. Sơ đồ & nguyên tắc

- GitHub repository: chứa source Python, `docs/pages`, `docs/previews` và `data/catalog.yaml`.
- GitHub Pages: xuất bản `/docs` thành trang tĩnh. Ví dụ `https://TEN_GITHUB.github.io/lokg-web-gallery/pages/WEB-ECO-001.html`.
- Render: chạy `uvicorn app.main:app`; trang sinh viên tại `/`, admin tại `/admin`, API tìm kiếm tại `/api/search`.
- GitHub Contents API: giáo viên sửa danh mục, backend commit trực tiếp `data/catalog.yaml` vào repo.
- PostgreSQL bên ngoài: lưu các lượt mở trang, truy vấn, lượt click; tách biệt danh mục YAML.

**Quan trọng:** Không dùng SQLite ghi trực tiếp vào ổ đĩa Render Free vì dữ liệu mất sau restart/redeploy/spin-down. Không dùng cơ sở dữ liệu Render Postgres Free nếu cần giữ số liệu qua 30 ngày. Chi tiết: https://render.com/docs/free.

## 1. Chuẩn bị trên Windows

Cài Git, Python 3.11 và một trình soạn thảo (VS Code). Trong PowerShell kiểm tra:

```powershell
git --version
py -3.11 --version
```

Giải nén ZIP dự án sao cho thư mục gốc chứa `app`, `docs`, `data`, `render.yaml`, `.python-version`, `requirements.txt`, `scripts`.

```powershell
cd "D:\Projects\LOKG_IR_GitHub_Pages_Links"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Nếu PowerShell không cho chạy script, dùng `cmd` với `.venv\Scripts\activate.bat`, hoặc gọi trực tiếp `\.venv\Scripts\python.exe`.

Sửa `.env` cho chế độ local:

```ini
APP_ENV=development
CATALOG_BACKEND=local
CATALOG_PATH=./data/catalog.yaml
ADMIN_PASSWORD=MAT_KHAU_BI_MAT_DU_DAI
SESSION_SECRET=MOT_CHUOI_NGAU_NHIEN_IT_NHAT_32_KY_TU
ANALYTICS_ENABLED=true
DATABASE_URL=sqlite:///runtime_data/analytics.db
ANALYTICS_SECRET=CHUOI_BI_MAT_NGAU_NHIEN_IT_NHAT_32_KY_TU
ANALYTICS_STORE_QUERIES=true
ANALYTICS_RETENTION_DAYS=90
```

Đừng copy nguyên các chuỗi ví dụ vào dịch vụ thật: hãy tự tạo mật khẩu/khóa bí mật mạnh. Chạy:

```powershell
python -m pytest -q
uvicorn app.main:app --reload
```

Kiểm tra `http://127.0.0.1:8000/`, `/admin`, `/api/stats/public`. Khi frontend đã gọi `/api/analytics/visit`, bộ đếm bắt đầu tăng. Dữ liệu local được lưu ở `runtime_data/analytics.db`, đã nằm trong `.gitignore`.

## 2. Tạo repository GitHub và push mã nguồn

1. Đăng nhập https://github.com/ và tạo **New repository** tên gợi ý `lokg-web-gallery`.
2. Chọn **Public** để GitHub Pages dùng được theo phương án này. **KHÔNG** tích chọn “Add README”, `.gitignore` hoặc license khi tạo repo mới, tránh trùng commit đầu.
3. Vào PowerShell tại thư mục dự án:

```powershell
git init
git branch -M main
git add .
git status --short
git commit -m "Initial LOKG-IR Web library with analytics"
git remote add origin https://github.com/TEN_GITHUB/lokg-web-gallery.git
git push -u origin main
```

Thay `TEN_GITHUB` bằng tài khoản GitHub của bạn. Nếu Git báo thiếu danh tính, dùng `git config --global user.name "Ten cua ban"` và `git config --global user.email "email-da-xac-minh@example.com"` rồi commit lại. Nếu `origin` đã tồn tại, dùng `git remote set-url origin URL` thay cho `remote add`.

**Kiểm tra bí mật trước push:** `.env` không được xuất hiện trong `git status` hoặc commit; `.env.example` chỉ có placeholder, không chứa token thực. Không commit mật khẩu, GitHub token, `DATABASE_URL` hay file SQLite. Repository công khai cần được rà soát cả mã nguồn nghiên cứu và giấy phép.

## 3. Bật GitHub Pages cho 72 giao diện

1. Mở repo GitHub → **Settings → Pages**.
2. Tại **Build and deployment**, chọn **Deploy from a branch**.
3. Chọn **Branch `main`**, **Folder `/docs`** → **Save**.
4. Chờ build hoàn tất. URL dự kiến:

   - Thư viện: `https://TEN_GITHUB.github.io/lokg-web-gallery/`
   - Giao diện số 1: `https://TEN_GITHUB.github.io/lokg-web-gallery/pages/WEB-ECO-001.html`
   - Ảnh xem trước: `https://TEN_GITHUB.github.io/lokg-web-gallery/previews/WEB-ECO-001.webp`

5. Kiểm tra cả ba URL. Nếu 404, vào GitHub **Actions** tìm workflow Pages và xem log (GitHub Pages có thể cần vài phút để xuất bản).

Nguồn chính thức: https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site

## 4. Đưa 72 URL thực tế vào `catalog.yaml`

Sau khi URL GitHub Pages hoạt động, mở PowerShell tại thư mục dự án:

```powershell
python scripts/seed_catalog.py --base-url https://TEN_GITHUB.github.io/lokg-web-gallery
```

Lệnh tạo `data/catalog.yaml` gồm các URL GitHub Pages thực tế và từ khóa từ bộ 72 trang minh họa. Kiểm tra một vài dòng, sau đó:

```powershell
git add data/catalog.yaml
git commit -m "Publish 72 gallery URLs in YAML catalog"
git push origin main
```

**Lưu ý:** 72 mẫu là dữ liệu minh họa được thiết kế; không tự coi chúng là ảnh đã được giảng viên thẩm định hoặc kết quả thử nghiệm trên lớp.

## 5. Tạo PostgreSQL bên ngoài để lưu thống kê

Phương án đơn giản với Render Free là dùng Supabase PostgreSQL (đây là một dịch vụ riêng, cần tự tạo dự án và tuân thủ hạn mức/gói bạn chọn).

1. Vào https://supabase.com/ → tạo project → lưu mật khẩu DB an toàn.
2. Vào project → nút **Connect**.
3. Chọn **Session pooler** (thường dùng kết nối IPv4, cổng 5432), sao chép nguyên chuỗi URI được cung cấp.
4. Thay `[YOUR-PASSWORD]` bằng mật khẩu thực. Nếu mật khẩu chứa `@`, `#`, `?`, `&` hoặc ký tự đặc biệt, cần percent-encode trong URL.
5. Dùng URI này làm biến bí mật `DATABASE_URL` ở Render, ví dụ cấu trúc (không phải địa chỉ thật):

```text
postgresql://postgres.PROJECT_REF:MAT_KHAU@HOST_POOLER:5432/postgres?sslmode=require
```

Không dùng dấu ngoặc hoặc placeholder giả khi khai báo thực tế. Không đưa `DATABASE_URL` vào GitHub. Mã nguồn sẽ tự chuyển scheme `postgresql://` sang driver `psycopg` 3, tạo bảng `lokg_usage_events` ở lần khởi động đầu và bật **Row Level Security (RLS)** trên bảng PostgreSQL (không tạo policy cho truy cập `anon`). Backend kết nối bí mật qua role chủ sở hữu bảng; **không** đưa khóa database hoặc mật khẩu ra frontend. Nếu dùng Supabase, nên kiểm tra trong **Table Editor / Authentication / Policies** rằng bảng không có policy SELECT công khai.

Tài liệu chính thức: https://supabase.com/docs/guides/database/connecting-to-postgres

**Lựa chọn khác:** Render trả phí + Persistent Disk có thể dùng SQLite tại `/var/data/analytics.db` với `DATABASE_URL=sqlite:////var/data/analytics.db`, disk mount `/var/data`, `ANALYTICS_ALLOW_SQLITE_PRODUCTION=true`. Không dùng cấu hình này trên Render Free.

## 6. Cấp GitHub token cho backend

GitHub → ảnh đại diện → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.

- Resource owner: tài khoản sở hữu repo.
- Repository access: **Only select repositories** → chọn `lokg-web-gallery`.
- Repository permissions: **Contents → Read and write**.
- Ghi lại token vào trình quản lý bí mật; chỉ nhập token trong **Render Environment**.

Token dùng để giảng viên tạo/sửa/xóa metadata và commit `data/catalog.yaml`. Không yêu cầu quyền quản trị toàn tài khoản, không cấp quyền `Workflows` cho ứng dụng.

Nguồn chính thức: https://docs.github.com/en/rest/repos/contents

## 7. Deploy FastAPI trên Render

### Cách A — Dễ cấu hình: Web Service thủ công

1. Đăng nhập https://dashboard.render.com/ → **New → Web Service**.
2. **Connect GitHub** → chọn `TEN_GITHUB/lokg-web-gallery`.
3. Điền:

| Thuộc tính | Giá trị |
|---|---|
| Name | `lokg-ir-web-demo` (hoặc tên khác chưa trùng) |
| Branch | `main` |
| Language | `Python 3` |
| Root Directory | Để trống, vì `app` nằm ở gốc repo |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Instance Type | `Free` cho demo |

4. Trong **Environment** thêm các biến sau:

| Biến | Giá trị |
|---|---|
| `APP_ENV` | `production` |
| `CATALOG_BACKEND` | `github` |
| `GITHUB_REPOSITORY` | `TEN_GITHUB/lokg-web-gallery` |
| `GITHUB_BRANCH` | `main` |
| `GITHUB_CATALOG_PATH` | `data/catalog.yaml` |
| `GITHUB_TOKEN` | token cá nhân, bảo mật |
| `ALLOWED_PAGE_HOSTS` | `*.github.io` |
| `ADMIN_PASSWORD` | mật khẩu mạnh ít nhất 16 ký tự |
| `SESSION_SECRET` | chuỗi ngẫu nhiên ít nhất 32 ký tự |
| `ANALYTICS_ENABLED` | `true` |
| `DATABASE_URL` | Supabase **Session pooler** URI |
| `ANALYTICS_SECRET` | chuỗi ngẫu nhiên ổn định ít nhất 32 ký tự |
| `ANALYTICS_STORE_QUERIES` | `true` hoặc `false` |
| `ANALYTICS_RETENTION_DAYS` | `90` |

**Rất quan trọng:** `SESSION_SECRET` và `ANALYTICS_SECRET` phải giữ nguyên qua mỗi lần deploy. `DATABASE_URL` cũng phải giữ bí mật. Nếu không muốn lưu từ khóa do sinh viên nhập, đặt `ANALYTICS_STORE_QUERIES=false`; hệ thống vẫn đếm lượt tìm kiếm.

5. Trong Settings → **Build & Deploy → Build Filters**, thêm ignored paths `data/catalog.yaml` và `docs/**` để cập nhật học liệu không khiến Render build lại mỗi lần giáo viên lưu.
6. **Deploy Web Service**; khi thấy `Live`, truy cập URL do Render cung cấp, ví dụ `https://lokg-ir-web-demo.onrender.com/`.

### Cách B — Blueprint

Có sẵn `render.yaml` với cấu hình tương ứng, trong đó `DATABASE_URL` và `GITHUB_TOKEN` được đánh dấu `sync: false` để nhập trên Dashboard. Vào **New → Blueprint**, chọn repo và xác nhận biến môi trường bí mật. Chỉ dùng một trong hai cách để tránh tạo hai web services trùng chức năng.

**Ghim phiên bản Python:** File `.python-version` đặt `3.11`, tránh dùng Python 3.14 mặc định mới của Render, nhằm bảo đảm các thư viện khoa học có wheel tương thích. https://render.com/docs/python-version

Nguồn Render FastAPI: https://render.com/docs/deploy-fastapi

## 8. Kiểm tra ứng dụng sau deploy

Mở lần lượt:

1. `https://TEN_RENDER.onrender.com/api/health` → `ok: true`, `analytics_enabled: true`.
2. `https://TEN_RENDER.onrender.com/api/meta` → `total: 72` sau khi seed.
3. `https://TEN_RENDER.onrender.com/` → trang sinh viên.
4. `https://TEN_RENDER.onrender.com/api/stats/public` → JSON đếm lượt truy cập/tìm kiếm.
5. Tìm thử `navbar`, `dashboard sidebar`, `giáo dục khóa học` → kết quả có link `github.io` đúng.
6. `https://TEN_RENDER.onrender.com/admin` → đăng nhập, xem danh mục và thống kê; thử thêm 01 link mẫu **mới** với từ khóa riêng (sau đó có thể xóa).
7. Trên GitHub kiểm tra commit mới của `data/catalog.yaml` sau thao tác quản trị.
8. Xuất CSV tại trang `/admin` để kiểm tra các cột `date_utc, visits, searches, clicks`.

Có thể dùng tập lệnh kiểm tra URL sau khi triển khai:

```powershell
python scripts/smoke_test_deploy.py --api https://TEN_RENDER.onrender.com --pages https://TEN_GITHUB.github.io/lokg-web-gallery
```

Tập lệnh không thay đổi dữ liệu quản trị, mặc định không phát sinh lượt tìm kiếm có từ khóa. Dùng `--with-search` nếu muốn kiểm tra truy vấn thực tế (sẽ tăng 01 lượt tìm kiếm).

## 9. Thống kê và ý nghĩa số liệu

**Sinh viên / (công khai):** bộ đếm tổng lượt mở trang tìm kiếm, lượt tìm kiếm, số trình duyệt truy cập hôm nay. Cập nhật khi tải trang và sau tìm kiếm.

**Admin /admin (đăng nhập):** tổng lượt truy cập, lượt tìm kiếm, lượt mở các mẫu HTML, truy vấn không có kết quả, từ khóa phổ biến, số liệu theo ngày, xuất CSV.

**Cách tính:**

- **Lượt truy cập:** mỗi lần trình duyệt gọi `/api/analytics/visit`, chống đếm trùng cùng một cookie trong 30 giây. Không tính việc gọi API health hay mở `/admin`.
- **Trình duyệt hôm nay:** ước tính số cookie trình duyệt duy nhất theo ngày UTC (bằng HMAC có khóa). **Không đồng nghĩa số sinh viên/người duy nhất.**
- **Lượt tìm kiếm:** các truy vấn không rỗng tại `/api/search`, chỉ đếm trang đầu (`offset=0`). Đổi chế độ tìm kiếm tạo lượt mới; chuyển trang kết quả không tính thêm.
- **Lượt mở giao diện:** thao tác bấm liên kết “Xem giao diện” từ kết quả tìm kiếm. **Không** thống kê người mở trực tiếp GitHub Pages.
- **Không có kết quả:** tìm kiếm có từ khóa và số kết quả bằng 0.

**Quyền riêng tư:** không lưu IP hoặc tên người học; cookie ngẫu nhiên được băm có khóa riêng theo ngày; nội dung tìm kiếm được rút gọn, che email và một số mẫu số điện thoại; không nhập dữ liệu cá nhân vào ô tìm kiếm. Thời gian lưu mặc định tối đa 90 ngày (dữ liệu cũ được xóa khi server nhận hoạt động định kỳ và lúc khởi động). Tốt nhất xin ý kiến đơn vị về thông báo thu thập dữ liệu trước khi sử dụng với sinh viên.

**Giới hạn khoa học:** các bộ đếm là số liệu vận hành, **không tự chứng minh** LOKG-IR nâng cao chất lượng hoặc kết quả học tập. Cần thêm bài kiểm tra đối chứng/tập truy vấn chuẩn và đánh giá trước–sau để hoàn thiện mục 7 của sáng kiến.

## 10. Bảng xử lý lỗi nhanh

| Hiện tượng | Kiểm tra trước |
|---|---|
| GitHub Pages 404 | Repo public, `main /docs`, workflow GitHub Pages, đúng tên chữ hoa/chữ thường của HTML |
| Render build lỗi do Python | Kiểm tra `.python-version` là `3.11`; đọc Build Logs |
| Render start `RuntimeError ... GITHUB_TOKEN` | Thiếu `GITHUB_REPOSITORY`, `GITHUB_TOKEN` hoặc quyền Contents Write |
| Render start lỗi `DATABASE_URL` / `psycopg` | Kiểm tra URL Supabase Session pooler, mật khẩu đã URL-encode, yêu cầu SSL |
| Render bị ngủ khi lâu không dùng | Free service spin-down sau 15 phút không có traffic; lần mở tiếp theo sẽ chậm |
| Giao diện hiện bộ đếm “chưa bật” | `ANALYTICS_ENABLED=false`, thiếu DB hoặc chưa redeploy |
| Admin lưu YAML bị lỗi 409 | Có người/commit khác sửa `catalog.yaml`; tải lại /admin, thử lại |
| Không hiện 72 học liệu | Chạy và push `scripts/seed_catalog.py --base-url ...`, kiểm tra repo/branch |
| Mở giao diện bị lỗi | URL GitHub Pages thực tế, không nhập link `/docs/pages/...` |
| Truy vấn thống kê thấp hơn dự kiến | Bỏ qua query rỗng/load-more; bộ đếm không đo truy cập trực tiếp GitHub Pages |

## 11. Thu thập minh chứng cho hồ sơ sáng kiến

- MC-01: ảnh trang tìm kiếm Render và số lượt truy cập hiển thị (ghi ngày, URL).
- MC-02: ảnh trang Admin hiển thị danh mục, từ khóa và bảng thống kê.
- MC-03: ảnh GitHub Pages và một số mẫu HTML/CSS.
- MC-04: xuất `data/catalog.yaml` và lịch sử commit GitHub.
- MC-05: xuất CSV thống kê 7/30/90 ngày, nêu rõ chỉ số và thời gian UTC.
- MC-06: bảng kết quả đánh giá chất lượng truy hồi có nhãn kiểm chứng, tách biệt số liệu analytics.
- MC-07: biên bản/phiếu xác nhận áp dụng thử trong học phần thực tế.

**Chỉ ghi số liệu đã phát sinh thật từ hệ thống thực tế, tuyệt đối không trình bày dữ liệu kiểm thử tự động hoặc synthetic gallery như số người tham gia giảng dạy.**
