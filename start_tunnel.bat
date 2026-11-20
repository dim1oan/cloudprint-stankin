@echo off
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "ALL_PROXY="
set "http_proxy="
set "https_proxy="
set "all_proxy="
set "NO_PROXY=*"
set "no_proxy=*"
echo Starting Cloudflare Tunnel...
cloudflared.exe tunnel --protocol http2 --url http://127.0.0.1:8000
pause
