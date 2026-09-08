"""Desktop entry point. All Tk operations stay on the main thread."""

import json
import os
from pathlib import Path
import queue
import sys
import threading
from tkinter import filedialog

import customtkinter as ctk

from tronclass_client import Cancelled, TronClassClient, describe_error, parse_target


APP_DIRECTORY = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


class DownloaderApp(ctk.CTk):
    def __init__(self, settings_directory=APP_DIRECTORY):
        super().__init__()
        self.title("TronClass 下載器 v2.2.0 — 課程批次下載")
        self.geometry("680x760")
        self.minsize(620, 720)
        self.config_file = Path(settings_directory) / "config.json"
        self.events = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker = None
        self.last_directory = None
        self.closing = False
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(9, weight=1)

        ctk.CTkLabel(self, text="TronClass 教材下載器", font=("Arial", 24, "bold")).grid(row=0, column=0, pady=(20, 12))
        account = ctk.CTkFrame(self)
        account.grid(row=1, column=0, padx=24, sticky="ew")
        account.grid_columnconfigure((0, 1), weight=1)
        self.entry_id = ctk.CTkEntry(account, placeholder_text="學號")
        self.entry_id.grid(row=0, column=0, padx=12, pady=12, sticky="ew")
        self.entry_pwd = ctk.CTkEntry(account, placeholder_text="TronClass 密碼", show="*")
        self.entry_pwd.grid(row=0, column=1, padx=12, pady=12, sticky="ew")
        self.remember = ctk.BooleanVar(value=False)
        self.remember_box = ctk.CTkCheckBox(account, text="記住帳密（儲存在本機 config.json，未加密）", variable=self.remember,
                                         checkbox_width=16, checkbox_height=16, font=("Arial", 12))
        self.remember_box.grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="w")

        self.mode = ctk.CTkSegmentedButton(self, values=["整門課教材", "單一活動附件"])
        self.mode.set("整門課教材")
        self.mode.grid(row=2, column=0, padx=24, pady=(18, 10), sticky="ew")
        self.entry_url = ctk.CTkEntry(self, placeholder_text="貼上課程網址，或 learning-activity 網址", height=36)
        self.entry_url.grid(row=3, column=0, padx=24, sticky="ew")
        ctk.CTkLabel(self, text="整門課模式會整理全部活動的文件附件；不含影片、外部連結及線上測驗內容。",
                     font=("Arial", 12), wraplength=580).grid(row=4, column=0, padx=24, pady=(6, 12), sticky="w")

        folder = ctk.CTkFrame(self, fg_color="transparent")
        folder.grid(row=5, column=0, padx=24, sticky="ew")
        folder.grid_columnconfigure(0, weight=1)
        self.output = ctk.CTkEntry(folder)
        self.output.insert(0, str(Path(settings_directory) / "downloads"))
        self.output.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.browse_btn = ctk.CTkButton(folder, text="選擇資料夾", width=100, command=self.choose_folder)
        self.browse_btn.grid(row=0, column=1)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=6, column=0, padx=24, pady=16, sticky="ew")
        buttons.grid_columnconfigure((0, 1, 2), weight=1)
        self.download_btn = ctk.CTkButton(buttons, text="開始下載", command=self.start_download)
        self.download_btn.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        self.cancel_btn = ctk.CTkButton(buttons, text="取消", state="disabled", command=self.cancel_download)
        self.cancel_btn.grid(row=0, column=1, padx=6, sticky="ew")
        self.retry_btn = ctk.CTkButton(buttons, text="重新掃描並重試", state="disabled", command=self.start_download)
        self.retry_btn.grid(row=0, column=2, padx=(6, 0), sticky="ew")
        self.progress = ctk.CTkProgressBar(self)
        self.progress.set(0)
        self.progress.grid(row=7, column=0, padx=24, sticky="ew")
        self.status = ctk.CTkLabel(self, text="準備就緒", wraplength=600, anchor="w")
        self.status.grid(row=8, column=0, padx=24, pady=8, sticky="ew")
        self.log_box = ctk.CTkTextbox(self, state="disabled", height=190)
        self.log_box.grid(row=9, column=0, padx=24, sticky="nsew")
        self.open_btn = ctk.CTkButton(self, text="開啟下載資料夾", state="disabled", command=self.open_folder)
        self.open_btn.grid(row=10, column=0, pady=16)
        self.inputs = [self.entry_id, self.entry_pwd, self.remember_box, self.mode, self.entry_url, self.output, self.browse_btn]
        self.load_credentials()
        self.log("貼上網址後開始下載。重試會重新讀取清單，並略過已完成且校驗一致的附件。")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(80, self.poll_events)

    def log(self, message):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def choose_folder(self):
        selected = filedialog.askdirectory(parent=self, title="選擇教材儲存位置")
        if selected:
            self.output.delete(0, "end")
            self.output.insert(0, selected)

    def load_credentials(self):
        try:
            data = json.loads(self.config_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("remember"):
                self.entry_id.insert(0, str(data.get("username", "")))
                self.entry_pwd.insert(0, str(data.get("password", "")))
                self.remember.set(True)
        except FileNotFoundError:
            pass
        except (ValueError, OSError):
            self.log("讀取帳密設定失敗，請重新輸入。")

    def start_download(self):
        if self.worker is not None and self.worker.is_alive():
            return
        username, password = self.entry_id.get().strip(), self.entry_pwd.get()
        target, root = self.entry_url.get().strip(), self.output.get().strip()
        whole_course = self.mode.get() == "整門課教材"
        if not all((username, password, target, root)):
            self.log("請填寫學號、密碼、網址及儲存位置。")
            return
        try:
            _, activity = parse_target(target)
            if not whole_course and activity is None:
                self.log("單一活動模式請貼上包含 learning-activity#/活動ID 的網址。")
                return
            Path(root).mkdir(parents=True, exist_ok=True)
            if self.remember.get():
                self.config_file.write_text(json.dumps({"username": username, "password": password, "remember": True}), encoding="utf-8")
            else:
                self.config_file.unlink(missing_ok=True)
        except Exception as error:
            self.log(describe_error(error))
            return
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.cancel_event.clear()
        self.progress.set(0)
        self.status.configure(text="正在登入…")
        for widget in self.inputs:
            widget.configure(state="disabled")
        self.download_btn.configure(state="disabled")
        self.retry_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.worker = threading.Thread(target=self.run_worker, args=(username, password, target, root, whole_course), daemon=True)
        self.worker.start()

    def run_worker(self, username, password, target, root, whole_course):
        client = TronClassClient(cancel=self.cancel_event, emit=lambda kind, value: self.events.put((kind, value)))
        try:
            client.login(username, password)
            result = client.run(target, root, whole_course)
            self.events.put(("result", result))
        except Cancelled:
            self.events.put(("status", "已取消"))
        except Exception as error:
            self.events.put(("log", describe_error(error)))
            self.events.put(("status", "未完成，請查看下方訊息後重試。"))
        finally:
            client.close()
            self.events.put(("done", None))

    def poll_events(self):
        for _ in range(100):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.log(value)
            elif kind == "status":
                self.status.configure(text=value)
            elif kind == "progress":
                completed, total = value
                self.progress.set(completed / total if total else 0)
            elif kind == "result":
                label = "已取消" if value.cancelled else "處理結束（部分失敗）" if value.failures else "處理完成"
                summary = f"{label}：下載 {value.downloaded}、略過 {value.skipped}、失敗 {len(value.failures)}"
                self.status.configure(text=summary)
                self.log(summary)
                if value.excluded:
                    self.log(f"另有 {value.excluded} 個影音附件不在本次文件下載範圍。")
                self.log(f"檔案與下載報告：{value.directory}")
                self.last_directory = value.directory
                self.open_btn.configure(state="normal")
            elif kind == "done":
                for widget in self.inputs:
                    widget.configure(state="normal")
                self.download_btn.configure(state="normal")
                self.retry_btn.configure(state="normal")
                self.cancel_btn.configure(state="disabled")
        if self.closing and (self.worker is None or not self.worker.is_alive()):
            self.destroy()
            return
        self.after(80, self.poll_events)

    def cancel_download(self):
        self.cancel_event.set()
        self.cancel_btn.configure(state="disabled")
        self.status.configure(text="正在取消，等待目前連線結束…")

    def on_close(self):
        if self.worker is not None and self.worker.is_alive():
            self.closing = True
            self.cancel_download()
            self.log("正在安全結束下載，完成暫存檔清理後會關閉視窗。")
        else:
            self.destroy()

    def open_folder(self):
        if self.last_directory:
            try:
                os.startfile(self.last_directory)
            except (OSError, AttributeError):
                self.log(f"請手動開啟：{self.last_directory}")


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    DownloaderApp().mainloop()
