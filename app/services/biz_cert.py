"""사업자등록증 업로드 (2026-10-07). 개인정보라 static 밖(instance/biz_certs)에 두고
어드민 라우트(/admin/users/<id>/biz-cert)로만 내준다."""
import io
import os
import uuid

from flask import current_app
from PIL import Image

MAX_BYTES = 10 * 1024 * 1024
EXTS = {"jpg", "jpeg", "png", "webp", "pdf"}


class CertError(Exception):
    pass


def folder():
    return os.path.join(current_app.instance_path, "biz_certs")


def path(filename):
    return os.path.join(folder(), os.path.basename(filename))


def read_upload(file):
    """검증만 하고 (bytes, ext) 를 돌려준다 — 회원 생성 전에 오류를 낼 수 있게 저장과 나눴다."""
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in EXTS:
        raise CertError("사업자등록증은 JPG · PNG · WEBP · PDF 파일만 올릴 수 있습니다.")
    data = file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise CertError("사업자등록증 파일은 10MB 이하로 올려주세요.")
    if ext == "pdf":
        if not data.startswith(b"%PDF"):
            raise CertError("PDF 파일이 올바르지 않습니다.")
    else:
        try:
            Image.open(io.BytesIO(data)).verify()   # 확장자만 바꾼 파일 거르기
        except Exception:
            raise CertError("이미지 파일이 올바르지 않습니다.")
    return data, ("jpg" if ext == "jpeg" else ext)


def save(user_id, upload):
    data, ext = upload
    os.makedirs(folder(), exist_ok=True)
    name = f"{user_id}_{uuid.uuid4().hex[:12]}.{ext}"   # 추측 불가 이름 — 그래도 내주는 건 어드민 라우트뿐
    with open(path(name), "wb") as fp:
        fp.write(data)
    return name


if __name__ == "__main__":  # python -m app.services.biz_cert
    from werkzeug.datastructures import FileStorage
    from app import create_app
    with create_app().app_context():
        buf = io.BytesIO(); Image.new("RGB", (4, 4)).save(buf, "PNG")
        assert read_upload(FileStorage(io.BytesIO(buf.getvalue()), "a.png"))[1] == "png"
        assert read_upload(FileStorage(io.BytesIO(b"%PDF-1.4 x"), "a.PDF"))[1] == "pdf"
        for bad in ((b"not image", "a.jpg"), (b"x", "a.exe"), (b"MZ", "a.pdf")):
            try:
                read_upload(FileStorage(io.BytesIO(bad[0]), bad[1])); raise SystemExit(f"accepted {bad[1]}")
            except CertError:
                pass
        assert read_upload(FileStorage(io.BytesIO(b""), "")) is None
        print("biz_cert ok")
