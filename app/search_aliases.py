"""Vietnamese/English UI terminology for the teaching search app."""
from __future__ import annotations
import re,unicodedata
CATEGORY_ALIASES={
'ecommerce':['thương mại điện tử','ban hang','bán hàng','mua sắm','cua hang','shop','ecommerce','sản phẩm','giỏ hàng','product'],
'education':['giáo dục','khoa hoc','khóa học','lớp học','academy','education','course','learning'],
'business':['doanh nghiệp','cong ty','công ty','dich vu','business','corporate','consulting'],
'news':['tin tức','bai viet','bài viết','tin tuc','blog','news','magazine','article'],
'landing':['landing','quảng cáo','gioi thieu ung dung','marketing','feature','cta'],
'dashboard':['dashboard','quản trị','thống kê','đăng nhập','đăng ký','biểu mẫu','login','admin','analytics','form'],
}
COMPONENT_ALIASES={
'navbar':['thanh điều hướng','thanh menu','menu ngang','menu tren','navbar','navigation'],
'hero':['hero','banner','ảnh lớn','dau trang','đầu trang'],
'cards':['thẻ nội dung','thẻ thông tin','thẻ sản phẩm','card','cards'],
'search':['tìm kiếm','search box','search'],
'filter':['bộ lọc sản phẩm','product filter','bộ lọc','loc','lọc','filter'],
'grid':['product grid','lưới sản phẩm','lưới','grid','danh sách dạng lưới'],
'sidebar':['thanh bên','cột trái','cột phải','sidebar','menu dọc','menu trái'],
'cta':['kêu gọi hành động','nút hành động','cta','bắt đầu'],
'form':['biểu mẫu','form','nhập liệu','email','mật khẩu'],
'login':['đăng nhập','sign in','login'],
'dashboard':['dashboard','bảng điều khiển','quản trị'],
'chart':['biểu đồ','chart','đồ thị'],
'pricing':['bảng giá','pricing'],
'course':['khóa học','course'],
'product':['sản phẩm','product','mua hàng'],
'article':['bài viết','tin tức','article'],
'statistics':['thống kê','số liệu','chỉ số'],
'footer':['chân trang','footer'],
}
RELATION_ALIASES={
'left_of':['bên trái','phía trái','cột trái','left of','on the left','left'],
'above':['phía trên','bên trên','top','above','over'],
'inside':['bên trong','trong khung','inside','within','contains'],
'right_of':['bên phải','phía phải','cột phải','right of','on the right'],
'below':['phía dưới','bên dưới','below','under'],
'near':['bên cạnh','gần','near','adjacent'],
}


def normalize(text:str)->str:
    text=str(text or '').lower().replace('đ','d')
    text=''.join(c for c in unicodedata.normalize('NFKD',text) if not unicodedata.combining(c))
    return re.sub(r'\s+',' ',re.sub(r'[^a-z0-9]+',' ',text)).strip()


def tokens(text:str)->list[str]:return re.findall(r'[a-z0-9]+',normalize(text))


def detect(query:str):
    q=' '+normalize(query)+' '
    def has_alias(aliases):
        return any(' '+normalize(x)+' ' in q for x in aliases)
    cats={k for k,a in CATEGORY_ALIASES.items() if has_alias(a)}
    comps={k for k,a in COMPONENT_ALIASES.items() if has_alias(a)}
    rels={k for k,a in RELATION_ALIASES.items() if has_alias(a)}
    return cats,comps,rels

