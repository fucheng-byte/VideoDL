[app]

title = 影音下載工具
package.name = videodl
package.domain = org.friend.videodl

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,otf

version = 1.0

# 需要的 Python 套件
requirements = python3,kivy,yt-dlp==2026.8.19,certifi,mutagen,websockets

orientation = portrait
fullscreen = 0

# Android 權限
android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE

# API / SDK 相關設定（可依需求調整版本）
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
p4a.branch = v2024.01.21

# 允許存取外部空間（Android 11+ 的 scoped storage 若要寫 /sdcard/Download
# 需要 MANAGE_EXTERNAL_STORAGE，這裡先用基本權限，必要時再加）
# android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE

[buildozer]
log_level = 2
warn_on_root = 1
