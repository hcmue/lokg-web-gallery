# Kiến trúc triển khai LOKG-IR (link-only, GitHub Pages)

## Quy trình giáo viên
1. Đưa mẫu HTML/CSS lên GitHub Pages. Kiểm tra URL mở được công khai.
2. Vào `https://<render-domain>/admin` và đăng nhập.
3. Nhập đúng **hai trường**: URL HTTPS của giao diện và danh sách từ khóa (dấu phẩy ngăn cách).
4. FastAPI kiểm tra tên miền, lưu một bản ghi YAML trong `data/catalog.yaml` trên GitHub bằng Contents API.
5. Chỉ mục LOKG-IR được dựng lại trong RAM sau khi lưu. Không tải nội dung HTML hoặc ảnh về Render.
6. Có thể sửa từ khóa, sửa URL hoặc xóa khỏi danh mục mà không làm mất trang Web gốc.

## Quy trình sinh viên
1. Vào trang `/` của Render, không cần tài khoản.
2. Nhập từ khóa; JavaScript gọi `GET /api/search?query=...&mode=lokg`.
3. FastAPI trả JSON chứa `page_url`, `title`, `tags`, `score` và thông tin xếp hạng.
4. Chọn “Xem giao diện” để mở đúng URL thuộc GitHub Pages (tab riêng).

## Dữ liệu và tri thức
Dữ liệu gốc là `data/catalog.yaml` (các trang Web có URL và từ khóa).
Từ khóa trở thành thực thể/khái niệm có cấu trúc; các mẫu có chung từ khóa đặc trưng được liên kết với nhau trong một chỉ mục đồ thị nhẹ.
Có thể xuất Markdown/YAML frontmatter cho một học liệu từ `/api/items/{id}/markdown`.
Quan hệ không gian `left_of`, `above`, `contains` **không được suy ra** từ URL hoặc từ khóa khi không có xác minh của giáo viên.

## Nơi lưu dữ liệu
- **GitHub Pages**: mã HTML/CSS + ảnh xem trước của từng mẫu.
- **GitHub repository**: `data/catalog.yaml` cùng lịch sử commit; nguồn dữ liệu quản trị.
- **Render FastAPI**: dữ liệu trong RAM và chỉ mục truy hồi; không cần lưu ảnh hoặc HTML.

## An toàn
- Không lưu mật khẩu GitHub hoặc token trong repository hoặc JavaScript.
- `GITHUB_TOKEN` là biến môi trường bí mật trên Render, với quyền Contents: Write chỉ đối với một repository được chọn.
- Chỉ cho nhập HTTPS dưới tên miền `*.github.io` hoặc danh sách được cấu hình riêng.
- Có rate-limit đăng nhập cơ bản, cookie HttpOnly/SameSite và từ chối Origin khác nguồn đối với thao tác quản trị.
- Không có chức năng tải nội dung URL về server, giảm rủi ro SSRF.

## Giới hạn học thuật
Ứng dụng tích hợp các hàm lõi `build_okf`, `entity_idf`, `make_lookups`, `link`, `sigma_candidates`, `sigma_score` của LOKG-IR MIWAI. Tuy nhiên, đầu vào là metadata từ khóa và vector TF-IDF văn bản, không phải ảnh trích đặc trưng CLIP như cấu hình thí nghiệm nghiên cứu. Vì vậy chỉ nên ghi “ứng dụng cơ chế truy hồi đồ thị LOKG-IR trong kho học liệu giao diện Web”, không khẳng định tái lập kết quả định lượng MIWAI.
