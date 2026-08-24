import requests
from bs4 import BeautifulSoup
import re
import urllib3
import sys

# 關閉煩人的 SSL 憑證警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def nsysu_ultimate_downloader(username, password, target_url):
    # 🌟 創造萬能公事包，它會自動幫我們記憶所有 Cookie
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })

    # ==========================================
    # 階段一：自動破解 SSO 登入
    # ==========================================
    print("🔑 [1/5] 正在連接中山大學登入系統...")
    
    # 1. 拜訪初始登入閘口 (它會把我們重新導向到 identity 認證中心)
    login_gate = "https://elearn.nsysu.edu.tw/login"
    gate_res = session.get(login_gate, verify=False)
    
    # 2. 解析網頁原始碼，尋找藏有動態 execution 參數的提交網址 (Form Action)
    soup = BeautifulSoup(gate_res.text, 'html.parser')
    form = soup.find('form') # 抓取登入表單
    
    if not form:
        print("❌ 找不到登入表單，可能是網站大改版！")
        return
        
    post_url = form.get('action') # 這就是帶有 session_code 的動態網址！
    print("🔓 [2/5] 成功攔截動態驗證網址，準備送出機密資料...")
    
    # 3. 打包你的帳號密碼
    login_data = {
        'username': username,
        'password': password
    }
    
    # 4. 對著動態網址發射 POST 請求！
    login_res = session.post(post_url, data=login_data, verify=False)
    
    # 檢查是否登入成功 (判斷網頁裡面有沒有出現錯誤提示)
    if "Invalid username or password" in login_res.text or "無效" in login_res.text:
        print("❌ 登入失敗，請檢查帳號密碼！")
        return
        
    print("✅ 登入成功！通行證已自動保存。")

    # ==========================================
    # 階段二：無縫接軌檔案下載
    # ==========================================
    print(f"🔍 [3/5] 正在分析課程網址...")
    match = re.search(r'learning-activity#/(\d+)', target_url)
    if not match:
        print("❌ 網址格式錯誤")
        return
    activity_id = match.group(1)

    print(f"🕵️ [4/5] 正在探索隱藏檔案 ID...")
    info_api = f"https://elearn.nsysu.edu.tw/api/activities/{activity_id}"
    res_info = session.get(info_api, verify=False).json() 
    
    try:
        file_id = res_info['uploads'][0]['reference_id']
        file_name = res_info['uploads'][0]['name']
    except (KeyError, IndexError):
        print("❌ 找不到檔案 ID，此頁面可能沒有夾帶檔案。")
        return

    print(f"🔗 [5/5] 取得真實網址並開始下載: {file_name}")
    download_api = f"https://elearn.nsysu.edu.tw/api/uploads/reference/document/{file_id}/url?preview=true&refer_id={activity_id}&refer_type=learning_activity"
    res_url = session.get(download_api, verify=False).json()
    
    real_url = res_url['url']
    pdf_response = session.get(real_url, verify=False)
    
    if pdf_response.status_code == 200:
        with open(file_name, "wb") as f:
            f.write(pdf_response.content)
        print(f"🎉 太神啦！檔案下載成功，已儲存於目前的資料夾！")
    else:
        print("❌ 檔案下載失敗...")

def main():
    # ==========================================
    # 執行區
    # ==========================================
    my_id = input("輸入學號: ")
    my_pwd = input("輸入TronClass密碼: ")
    target = input("輸入欲下載檔案網址: ")
    nsysu_ultimate_downloader(my_id, my_pwd, target)

# 程式執行起點
if __name__ == "__main__":
    try:
        main()
        # 正常執行完畢後，暫停視窗
        input("\n請按 Enter 鍵關閉視窗...")
        
    except Exception as e:
        # 當發生任何錯誤時，攔截錯誤並顯示
        print("\n" + "="*40)
        print("❌ 程式執行過程中發生未預期錯誤：")
        print(e)
        print("="*40)
        
        # 發生錯誤後，暫停視窗讓使用者有時間閱讀錯誤訊息
        input("\n請確認上方錯誤訊息後，按 Enter 鍵關閉視窗...")
        sys.exit(1)