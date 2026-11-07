# LOKG-IR Web Gallery - HCMUE
## Sáng kiến kinh nghiệm 2026 - Thực hiện: *Lương Trần Hy Hiến*

**Trang chính:** https://hcmue.github.io/lokg-web-gallery/  
**Backend:** FastAPI trên Render, URL `https://lokg-ir-web-links.onrender.com`.  
**Giao diện giáo viên để thêm tài nguyên mời (làm giàu dữ liệu):** `https://lokg-ir-web-links.onrender.com/admin`.  
**Mã nguồn và 72 học liệu demo:** repository `hcmue/lokg-web-gallery`.

## Giới hạn học thuật và riêng tư

- LOKG-IR dùng điểm văn bản TF-IDF và quan hệ từ metadata nhập tay; **không chạy toàn bộ pipeline CLIP** của bài báo gốc.
- Không tải lên hoặc phân tích nội dung giao diện từ URL; giáo viên chịu trách nhiệm từ khóa.
- 72 mẫu là **dữ liệu minh họa**, không phải minh chứng số lượng sinh viên đã dùng hay tác động học tập.
- Bộ đếm chỉ phản ánh sự kiện trình duyệt; không phải số người học duy nhất. Không lưu IP người dùng vào bảng sự kiện; truy vấn được làm sạch một số dạng định danh phổ biến trước khi lưu.


## Kho hoc lieu 150 mau

- 6 nhom x 25 mau, giu nguyen 72 mau goc.
- 78 mau moi: `docs/pages/WEB-XXX-013.html` den `WEB-XXX-025.html`.
- Anh xem truoc: `docs/previews/`; metadata: `data/catalog.yaml`.
- Huong dan su dung: `https://hcmue.github.io/lokg-web-gallery/huong-dan.html`.
- Khi sua YAML tren GitHub, Render can deploy lai hoac admin nhan tai lai du lieu.
