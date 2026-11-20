"""观自行深监控台。"""
import os as _os


def _ensure_ca_bundle():
    """uv 装的 Python（python-build-standalone）在 Windows 上不带根证书，所有 HTTPS 都会
    CERTIFICATE_VERIFY_FAILED。这里在任何网络请求之前，把证书指向 certifi 自带的那份。
    用户自己设了且文件存在的（比如公司代理的证书）不动。"""
    try:
        import certifi
    except Exception:  # noqa
        return
    ca = certifi.where()
    for name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        cur = _os.environ.get(name)
        if not (cur and _os.path.exists(cur)):
            _os.environ[name] = ca


_ensure_ca_bundle()
