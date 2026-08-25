import customtkinter as ctk
import threading
import requests
from bs4 import BeautifulSoup
import re
import urllib3
import os
import json

# 關閉 SSL 憑證警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 1. 介面基礎設定
# ==========================================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.geometry("550x550")
app.title("TronClass 下載器 v2.0")

CONFIG_FILE = "config.json"

# ==========================================
# 2. 爬蟲核心與狀態回報機制
# ==========================================
# 建立一個小工具，用來把原本的 print 訊息，推送到介面的文字框裡
def update_log(message):
    log_box.insert("end", message + "\n")
    log_box.see("end")  # 自動捲動到最底端

def nsysu_ultimate_downloader(username, password, target_url):
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })

    try:
        update_log("[1/5] 正在連接中山大學登入系統...")
        gate_res = session.get("https://elearn.nsysu.edu.tw/login", verify=False)
        
        soup = BeautifulSoup(gate_res.text, 'html.parser')
        form = soup.find('form')
        
        if not form:
            update_log("❌ 找不到登入表單，可能是網站大改版！")
            return
            
        post_url = form.get('action')
        update_log("[2/5] 成功攔截動態驗證網址，準備送出機密資料...")
        
        login_res = session.post(post_url, data={'username': username, 'password': password}, verify=False)
        
        if "Invalid username or password" in login_res.text or "無效" in login_res.text:
            update_log("❌ 登入失敗，請檢查學號或密碼！")
            return
            
        update_log("✅ 登入成功！通行證已自動保存。")

        update_log("[3/5] 正在分析課程網址...")
        match = re.search(r'learning-activity#/(\d+)', target_url)
        if not match:
            update_log("❌ 網址格式錯誤，請確認網址包含 learning-activity")
            return
        activity_id = match.group(1)

        update_log("[4/5] 正在探索隱藏檔案 ID...")
        info_api = f"https://elearn.nsysu.edu.tw/api/activities/{activity_id}"
        res_info = session.get(info_api, verify=False).json()
        
        try:
            file_id = res_info['uploads'][0]['reference_id']
            file_name = res_info['uploads'][0]['name']
        except (KeyError, IndexError):
            update_log("❌ 找不到檔案 ID，此頁面可能沒有夾帶檔案。")
            return

        update_log(f"[5/5] 取得真實網址並開始下載: {file_name}")
        download_api = f"https://elearn.nsysu.edu.tw/api/uploads/reference/document/{file_id}/url?preview=true&refer_id={activity_id}&refer_type=learning_activity"
        real_url = session.get(download_api, verify=False).json()['url']
        
        pdf_response = session.get(real_url, verify=False)
        
        if pdf_response.status_code == 200:
            with open(file_name, "wb") as f:
                f.write(pdf_response.content)
            full_path = os.path.abspath(file_name)
            update_log("🎉太神啦！檔案下載成功！")
            update_log(f"📁檔案位置:{full_path}")
            os.startfile(os.path.dirname(full_path))
        else:
            update_log("❌檔案下載失敗 (伺服器無回應)")
            
    except Exception as e:
        update_log(f"❌發生未預期的錯誤: {e}")
        
    finally:
        # 下載結束後，把按鈕恢復為可點擊狀態
        download_btn.configure(state="normal", text="開始下載")

# ==========================================
# 3. 按鈕觸發與執行緒分流
# ==========================================
def start_download_thread():
    user_id = entry_id.get()
    user_pwd = entry_pwd.get()
    target_url = entry_url.get()
    remember = remember_var.get() # 取得是否有打勾
    
    if not user_id or not user_pwd or not target_url:
        update_log("⚠️請確實填寫學號、密碼與網址！")
        return

    if remember:
        data = {"username": user_id, "password": user_pwd, "remember": True}
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    else:
        if os.path.exists(CONFIG_FILE):
            os.remove(CONFIG_FILE)
        
    # 按下按鈕後，先鎖死按鈕，防止使用者瘋狂連點產生多個下載任務
    download_btn.configure(state="disabled", text="下載中...")
    log_box.delete("0.0", "end") # 清空之前的對話紀錄
    
    # 建立一個背景工人（Thread），把下載任務交給他去跑
    worker = threading.Thread(target=nsysu_ultimate_downloader, args=(user_id, user_pwd, target_url))
    worker.start()

# ==========================================
# 4. GUI 元件排版設計
# ==========================================
title_label = ctk.CTkLabel(app, text="🎓 TronClass 下載器", font=("Arial", 24, "bold"))
title_label.pack(pady=(20, 10))

entry_id = ctk.CTkEntry(app, placeholder_text="請輸入學號 (如 B12345678)", width=350)
entry_id.pack(pady=10)

entry_pwd = ctk.CTkEntry(app, placeholder_text="請輸入 TronClass 密碼", show="*", width=350)
entry_pwd.pack(pady=(10,2))

remember_var = ctk.BooleanVar(value=False)
remember_checkbox = ctk.CTkCheckBox(app , text='記住帳號密碼' ,variable= remember_var ,font = ('Arial',13) , checkbox_height=16 ,checkbox_width=16 , border_width=2)
remember_checkbox.pack(pady = (0,5))

entry_url = ctk.CTkEntry(app, placeholder_text="請貼上 learning-activity 網址", width=350)
entry_url.pack(pady=10)

download_btn = ctk.CTkButton(app, text="開始下載", command=start_download_thread, width=350, font=("Arial", 14, "bold"))
download_btn.pack(pady=20)

# 狀態顯示文字框
log_box = ctk.CTkTextbox(app, width=450, height=180, font=("Arial", 13))
log_box.pack(pady=10)
log_box.insert("end", "歡迎使用！請輸入資料並點擊下載。\n")

# ==========================================
# 5. 啟動時自動讀取帳號密碼
# ==========================================
def load_credentials():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("remember"):
                    entry_id.insert(0, data.get("username", ""))
                    entry_pwd.insert(0, data.get("password", ""))
                    remember_var.set(True)
        except Exception as e:
            update_log(f"⚠️ 讀取設定檔失敗: {e}")

load_credentials() # 啟動時立刻執行讀取

# 啟動應用程式
app.mainloop()