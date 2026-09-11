# -*- coding: utf-8 -*-
"""
全方位多平台影片下載器 - Android (Kivy) 版本
基於原本的 tkinter 桌面版改寫而成，供朋友間側載安裝使用。

注意：
1. Android 上沒有內建 ffmpeg，因此本版本改用「單一完整檔案」的下載策略
   （不需要合併影音軌），確保在手機上能穩定下載完成。
2. 需要「儲存空間」權限才能把檔案存到手機的下載資料夾。
"""

import os
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.metrics import dp

import yt_dlp

# ----------------------------------------------------------------------
# Android 專用：權限與預設下載路徑
# ----------------------------------------------------------------------
try:
    from android.permissions import request_permissions, Permission
    from android.storage import primary_external_storage_path

    ON_ANDROID = True
except ImportError:
    ON_ANDROID = False


def get_default_save_path():
    if ON_ANDROID:
        try:
            return os.path.join(primary_external_storage_path(), "Download")
        except Exception:
            return "/sdcard/Download"
    else:
        # 方便在電腦上先測試用
        return os.getcwd()


# 解析度對應（改用單一檔案格式，避免需要 ffmpeg 合併）
RES_OPTIONS = {
    "最高可用畫質（單一檔案）": "best",
    "1080p 以下": "best[height<=1080]",
    "720p 以下": "best[height<=720]",
    "480p 以下": "best[height<=480]",
}


class DownloaderLayout(BoxLayout):
    pass


class MyLogger:
    """轉接 yt-dlp 的訊息到畫面上的 Log 區塊"""

    def __init__(self, app_ref):
        self.app_ref = app_ref

    def debug(self, msg):
        if msg.startswith("[debug]"):
            return
        self.app_ref.log(msg)

    def info(self, msg):
        self.app_ref.log(msg)

    def warning(self, msg):
        self.app_ref.log(f"警告: {msg}")

    def error(self, msg):
        self.app_ref.log(f"錯誤: {msg}")


class VideoDLApp(App):
    def build(self):
        self.title = "影音下載工具"
        Window.clearcolor = (0.96, 0.96, 0.96, 1)

        if ON_ANDROID:
            request_permissions(
                [
                    Permission.WRITE_EXTERNAL_STORAGE,
                    Permission.READ_EXTERNAL_STORAGE,
                ]
            )

        root = BoxLayout(orientation="vertical", padding=dp(15), spacing=dp(10))

        title_label = Label(
            text="影音下載工具\n(YouTube / 哔哩哔哩 / X / TikTok / Discord)",
            size_hint_y=None,
            height=dp(60),
            font_size=dp(16),
            halign="center",
        )
        title_label.bind(size=lambda *_: setattr(title_label, "text_size", title_label.size))
        root.add_widget(title_label)

        # 網址輸入
        root.add_widget(Label(text="影片網址：", size_hint_y=None, height=dp(20), halign="left"))
        self.url_input = TextInput(
            hint_text="貼上影片連結...",
            multiline=False,
            size_hint_y=None,
            height=dp(45),
        )
        root.add_widget(self.url_input)

        # 儲存路徑
        root.add_widget(Label(text="儲存位置：", size_hint_y=None, height=dp(20), halign="left"))
        self.path_input = TextInput(
            text=get_default_save_path(),
            multiline=False,
            size_hint_y=None,
            height=dp(45),
        )
        root.add_widget(self.path_input)

        # 解析度選擇
        root.add_widget(Label(text="選擇畫質：", size_hint_y=None, height=dp(20), halign="left"))
        self.res_spinner = Spinner(
            text="最高可用畫質（單一檔案）",
            values=list(RES_OPTIONS.keys()),
            size_hint_y=None,
            height=dp(45),
        )
        root.add_widget(self.res_spinner)

        # 下載按鈕
        self.download_btn = Button(
            text="開始下載",
            size_hint_y=None,
            height=dp(55),
            background_color=(0.3, 0.7, 0.3, 1),
            font_size=dp(16),
        )
        self.download_btn.bind(on_release=self.start_download_thread)
        root.add_widget(self.download_btn)

        # Log 顯示區
        root.add_widget(Label(text="狀態訊息：", size_hint_y=None, height=dp(20), halign="left"))
        self.log_label = Label(
            text="準備就緒，請輸入網址後按下載。\n(Android 版不支援自動合併高畫質音影軌，"
            "已改用單一完整檔案下載模式)",
            size_hint_y=None,
            halign="left",
            valign="top",
            font_size=dp(13),
        )
        self.log_label.bind(
            width=lambda *_: setattr(self.log_label, "text_size", (self.log_label.width, None))
        )
        self.log_label.bind(texture_size=lambda *_: setattr(self.log_label, "height", self.log_label.texture_size[1]))

        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(self.log_label)
        root.add_widget(scroll)

        return root

    # ------------------------------------------------------------------
    def log(self, message):
        # yt-dlp 的 callback 可能在背景執行緒，用 Clock 排程回主執行緒更新 UI
        def _update(dt):
            self.log_label.text += f"\n{message}"

        Clock.schedule_once(_update, 0)

    def start_download_thread(self, instance):
        url = self.url_input.text.strip()
        save_path = self.path_input.text.strip()

        if not url:
            self.log("錯誤：請先輸入影片網址！")
            return
        if not os.path.isdir(save_path):
            try:
                os.makedirs(save_path, exist_ok=True)
            except Exception as e:
                self.log(f"錯誤：儲存資料夾無效且無法建立 - {e}")
                return

        format_opt = RES_OPTIONS.get(self.res_spinner.text, "best")

        self.download_btn.disabled = True
        self.download_btn.text = "下載中..."
        self.log(f"開始下載到: {save_path}")

        threading.Thread(
            target=self.download_process,
            args=(url, save_path, format_opt),
            daemon=True,
        ).start()

    def download_process(self, url, save_path, format_opt):
        outtmpl = os.path.join(save_path, "%(title)s [%(resolution)s].%(ext)s")

        ydl_opts = {
            "format": format_opt,
            "outtmpl": outtmpl,
            "logger": MyLogger(self),
            "noplaylist": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            self.log("下載完成！")
        except Exception as e:
            self.log(f"發生錯誤: {e}")
        finally:
            def _reset(dt):
                self.download_btn.disabled = False
                self.download_btn.text = "開始下載"

            Clock.schedule_once(_reset, 0)


if __name__ == "__main__":
    VideoDLApp().run()
