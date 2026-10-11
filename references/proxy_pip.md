# pip 走 SOCKS5 代理的安装排错

已知问题：Python 自带的 pip 使用的 vendored urllib3 对 `socks5://` + HTTPS 有 bug
（`PoolKey` 不接受 `key_proxy_ssl_context`），直接 `pip --proxy socks5://127.0.0.1:7897` 会失败。

## 可靠解法：本地 HTTP 代理转发到 SOCKS5
1. 起一个本地 HTTP 代理，把流量转到 SOCKS5（7897）。可用任意现成工具，例如：
   - `proxychains` / `privoxy` 配置 `forward-socks5`
   - 或一段 Python（用 `socks` 库监听 127.0.0.1:8123 转发到 7897）
2. 然后：
   ```
   python -m pip install --proxy http://127.0.0.1:8123 yt-dlp requests pysocks imageio-ffmpeg
   ```
3. Python 脚本本身（`requests`）仍用 `session.proxies={"http": socks5h://..., "https": socks5h://...}`，
   因为 `requests` + `PySocks` 对 `socks5h` 是正常的（只有 pip 的 urllib3 有坑）。

## 验证
```
python -c "import yt_dlp, requests, socks, imageio_ffmpeg; print('ok')"
```
