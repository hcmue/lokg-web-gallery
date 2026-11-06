"""Single-teacher session authentication; student endpoints are public."""
from __future__ import annotations
import secrets
import time
from collections import defaultdict
from fastapi import Request, HTTPException
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from .config import Settings

COOKIE = 'lokg_admin_session'
TTL = 8 * 60 * 60

class Auth:
    def __init__(self, config: Settings):
        self.config = config
        self.serializer = URLSafeTimedSerializer(config.session_secret, salt='lokg-admin-v1') if config.session_secret else None
        self.failures: dict[str, list[float]] = defaultdict(list)

    def configured(self) -> bool:
        return bool(self.config.admin_password and self.config.session_secret and len(self.config.session_secret)>=32)

    def login(self, password: str, ip: str) -> str:
        if not self.configured():
            raise HTTPException(503, 'Admin chưa được cấu hình: đặt ADMIN_PASSWORD và SESSION_SECRET (ít nhất 32 ký tự).')
        now = time.monotonic()
        failures = [x for x in self.failures[ip] if now-x<300]
        self.failures[ip] = failures
        if len(failures)>=6:
            raise HTTPException(429, 'Đã thử quá nhiều lần. Vui lòng thử lại sau.')
        if not secrets.compare_digest(password.encode('utf-8'), self.config.admin_password.encode('utf-8')):
            self.failures[ip].append(now)
            raise HTTPException(401, 'Mật khẩu không đúng.')
        self.failures.pop(ip, None)
        return self.serializer.dumps({'role':'teacher'})

    def require(self, request: Request):
        token = request.cookies.get(COOKIE, '')
        if not token or not self.serializer:
            raise HTTPException(401, 'Vui lòng đăng nhập với tài khoản giáo viên.')
        try:
            data = self.serializer.loads(token, max_age=TTL)
        except (BadSignature, SignatureExpired):
            raise HTTPException(401, 'Phiên đăng nhập đã hết hạn.')
        if data.get('role') != 'teacher':
            raise HTTPException(403, 'Không đủ quyền.')
        # SameSite=Strict on the cookie plus explicit Origin validation protect browser mutations.
        if request.method not in {'GET','HEAD','OPTIONS'}:
            origin = request.headers.get('origin', '')
            host = request.headers.get('host', '')
            if origin:
                from urllib.parse import urlparse
                try:
                    parsed=urlparse(origin)
                except ValueError:
                    raise HTTPException(403,'Nguồn yêu cầu không hợp lệ.')
                if parsed.scheme not in {'http','https'} or parsed.netloc != host:
                    raise HTTPException(403,'Yêu cầu khác nguồn bị từ chối.')
        return True
