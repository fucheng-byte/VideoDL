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
from kivy.core.text import LabelBase
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserListView
from kivy.metrics import dp

import yt_dlp

# ----------------------------------------------------------------------
# 中文字體註冊：Kivy 預設字體(Roboto)不含中文字，會顯示成方塊/亂碼，
# 這裡改用內附的 Noto Sans TC 字體，並覆蓋掉預設的 "Roboto" 字體名稱，
# 這樣所有 Label/Button/TextInput 不用逐一設定 font_name 也能正常顯示中文。
# ----------------------------------------------------------------------
_FONT_PATH = os.path.join(os.path.dirname(__file__), "NotoSansTC-Regular.otf")
if os.path.exists(_FONT_PATH):
    LabelBase.register(name="Roboto", fn_regular=_FONT_PATH)

# ----------------------------------------------------------------------
# Android 專用：權限與預設下載路徑
# ----------------------------------------------------------------------
try:
    from android.permissions import request_permissions, Permission
    from jnius import autoclass

    ON_ANDROID = True
except ImportError:
    ON_ANDROID = False


def get_default_save_path():
    if ON_ANDROID:
        try:
            # 改用「App 專屬的外部儲存空間」，不需要額外的儲存權限即可寫入，
            # 可避開 Android 11+ 的 scoped storage 權限限制導致下載失敗的問題。
            # 路徑類似：/storage/emulated/0/Android/data/<package>/files/Download
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            context = PythonActivity.mActivity
            files_dir = context.getExternalFilesDir(None).getAbsolutePath()
            path = os.path.join(files_dir, "Download")
            os.makedirs(path, exist_ok=True)
            return path
        except Exception:
            return "/sdcard/Download"
    else:
        # 方便在電腦上先測試用
        return os.getcwd()


def get_ffmpeg_path():
    """在 Android 上尋找內建的 ffmpeg 執行檔（被包裝成 libffmpegbin.so 放在
    App 的原生函式庫目錄下，這是繞過 Android 執行檔限制的常見手法）。"""
    if not ON_ANDROID:
        return None
    try:
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        context = PythonActivity.mActivity
        native_lib_dir = context.getApplicationInfo().nativeLibraryDir
        ffmpeg_path = os.path.join(native_lib_dir, "libffmpegbin.so")
        if os.path.exists(ffmpeg_path):
            try:
                os.chmod(ffmpeg_path, 0o755)
            except Exception:
                pass
            return ffmpeg_path
    except Exception:
        pass
    return None


def get_browse_root_path():
    """瀏覽資料夾時的起始根目錄（盡量從使用者看得懂的公用空間開始瀏覽）"""
    if ON_ANDROID:
        try:
            from android.storage import primary_external_storage_path

            root = primary_external_storage_path()
            if os.path.isdir(root):
                return root
        except Exception:
            pass
        return "/storage/emulated/0"
    else:
        return os.path.expanduser("~")


# 解析度對應（現在有內建 ffmpeg 可以合併影音軌，改用一般的
# bestvideo+bestaudio 選擇策略，畫質選擇更完整；若合併失敗則自動降級
# 為單一檔案格式）
RES_OPTIONS = {
    "最高可用畫質（自動合併）": "bestvideo+bestaudio/best",
    "1080p 以下": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
    "720p 以下": "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
    "480p 以下": "bestvideo[height<=480]+bestaudio/best[height<=480]/best",
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
            color=(0, 0, 0, 1),
        )
        title_label.bind(size=lambda *_: setattr(title_label, "text_size", title_label.size))
        root.add_widget(title_label)

        # 網址輸入
        root.add_widget(Label(text="影片網址：", size_hint_y=None, height=dp(20), halign="left", color=(0, 0, 0, 1)))
        self.url_input = TextInput(
            hint_text="貼上影片連結...",
            multiline=False,
            size_hint_y=None,
            height=dp(45),
            foreground_color=(0, 0, 0, 1),
        )
        root.add_widget(self.url_input)

        # 儲存路徑
        root.add_widget(Label(text="儲存位置：", size_hint_y=None, height=dp(20), halign="left", color=(0, 0, 0, 1)))
        path_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(45), spacing=dp(5))
        self.path_input = TextInput(
            text=get_default_save_path(),
            multiline=False,
            size_hint_x=0.75,
            foreground_color=(0, 0, 0, 1),
        )
        path_row.add_widget(self.path_input)
        browse_btn = Button(text="瀏覽...", size_hint_x=0.25)
        browse_btn.bind(on_release=self.open_folder_chooser)
        path_row.add_widget(browse_btn)
        root.add_widget(path_row)

        # 提示：自訂資料夾在部分手機上可能因系統權限限制而無法寫入
        root.add_widget(
            Label(
                text="(若自選資料夾下載失敗，請改回預設位置)",
                size_hint_y=None,
                height=dp(18),
                halign="left",
                font_size=dp(11),
                color=(0.4, 0.4, 0.4, 1),
            )
        )

        # 解析度選擇
        root.add_widget(Label(text="選擇畫質：", size_hint_y=None, height=dp(20), halign="left", color=(0, 0, 0, 1)))
        self.res_spinner = Spinner(
            text="最高可用畫質（自動合併）",
            values=list(RES_OPTIONS.keys()),
            size_hint_y=None,
            height=dp(45),
            color=(0, 0, 0, 1),
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
        root.add_widget(Label(text="狀態訊息：", size_hint_y=None, height=dp(20), halign="left", color=(0, 0, 0, 1)))
        self.log_label = Label(
            text="準備就緒，請輸入網址後按下載。\n(已內建 ffmpeg，支援自動合併高畫質音影軌)",
            size_hint_y=None,
            halign="left",
            valign="top",
            font_size=dp(13),
            color=(0, 0, 0, 1),
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
    def open_folder_chooser(self, instance):
        content = BoxLayout(orientation="vertical", spacing=dp(5), padding=dp(5))

        chooser = FileChooserListView(
            path=get_browse_root_path(),
            dirselect=True,
            filters=[],
        )
        content.add_widget(chooser)

        btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(45), spacing=dp(5))
        select_btn = Button(text="選擇此資料夾")
        cancel_btn = Button(text="取消")
        btn_row.add_widget(select_btn)
        btn_row.add_widget(cancel_btn)
        content.add_widget(btn_row)

        popup = Popup(title="選擇儲存資料夾", content=content, size_hint=(0.9, 0.9))

        def on_select(*_):
            # dirselect=True 時，若使用者只是點進資料夾但沒有勾選，
            # chooser.path 會是目前所在的資料夾路徑，直接採用它最保險。
            chosen = chooser.selection[0] if chooser.selection else chooser.path
            if os.path.isdir(chosen):
                self.path_input.text = chosen
            popup.dismiss()

        def on_cancel(*_):
            popup.dismiss()

        select_btn.bind(on_release=on_select)
        cancel_btn.bind(on_release=on_cancel)

        popup.open()

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

        # 找內建的 ffmpeg，找得到就設定合併輸出成 mp4；
        # 找不到（例如舊版APK或桌面測試）就退回不需要合併的格式，避免直接報錯。
        ffmpeg_path = get_ffmpeg_path()
        if ffmpeg_path:
            ydl_opts["ffmpeg_location"] = ffmpeg_path
            ydl_opts["merge_output_format"] = "mp4"
            self.log(f"已找到內建 ffmpeg：{ffmpeg_path}")
        else:
            # 沒有 ffmpeg 時，把格式規則改成只挑單一完整檔案，避免合併失敗
            ydl_opts["format"] = ydl_opts["format"].split("+")[0].replace(
                "bestvideo", "best"
            ) + "[acodec!=none][vcodec!=none]/best"
            self.log("警告：未找到內建 ffmpeg，改用單一檔案下載模式")

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
