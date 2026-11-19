# 中山大學 TronClass 教材下載器

輸入中山網路大學帳密、貼上課程網址，即可逐一下載該課程可存取的文件附件。
提供 CustomTkinter 桌面介面，並保留單一活動下載模式。

<img width="800" alt="TronClass 下載器操作畫面" src="https://github.com/user-attachments/assets/d0d04a4d-6115-45c6-a75f-da5ea7f0b620" />

## v2.3.0：課程成員查看與教材下載

- **整門課教材**：取得章節與活動清單，再下載各活動的所有附件。
- **單一活動附件**：貼上 `learning-activity#/活動ID` 網址，下載該活動的全部附件。
- **查看課程成員（需平台授權）**：貼上課程網址後，可嘗試查看該課程的成員姓名；名單只顯示在視窗中，不寫入下載資料夾。平台拒絕時會顯示具體權限錯誤。
- **已過存取期限的教材**：若登入後仍能取得附件資訊與預覽網址，即使教材頁面顯示存取期限已過，也能下載；若伺服器已撤銷存取權限，則無法下載。
- **原始檔與預覽檔**：優先下載原始 Office 檔；若平台拒絕原始檔但仍提供預覽，會儲存可取得的預覽。平台將 PowerPoint 轉成 PDF 時，檔名會使用 `.pdf`，不會把 PDF 誤存成 `.pptx`。
- **自動分類**：依課程 ID、章節與活動建立資料夾，檔名附上附件 ID，避免同名衝突。
- **重複下載檢查**：使用本機紀錄、大小及 SHA-256 校驗已完成的檔案；同時比較 API 提供的檔名、大小、更新時間等資訊。若平台在相同 ID 下更換檔案卻不更新任何中繼資料，請移除該活動的 `.download-manifest.json` 後重試。
- **取消與重試**：下載途中可取消；重試會重新掃描清單，略過校驗一致的檔案，補下載失敗或未完成的項目。單一附件失敗不會中止其他附件。
- **下載報告**：課程資料夾內的 `.download-report.json` 記錄本次成功數量及失敗項目，不包含帳密、Cookie 或下載簽章網址。

範圍限文件附件，不下載影片、音訊、外部連結內容或線上測驗題目；不會繳交作業或測驗。
只有帳號可存取的活動能下載；未開放或無權限的項目可能失敗或不出現在清單中。

**驗證狀態**：教材下載已完成實際帳號測試。成員查看已核對中山平台公開前端的 API 路徑並通過模擬回應測試；使用者回報學生帳號讀取成員名單時收到 HTTP 403。端點存在不代表學生有權限讀取。

## 從原始碼執行（Windows，Python 3.10 以上）

```powershell
git clone https://github.com/charlesjian95-source/Tronclass-PDF-downloader.git
cd Tronclass-PDF-downloader
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python Downloader_GUI.py
```

1. 輸入學號與 TronClass 密碼。
2. 選擇「整門課教材」（預設）。
3. 貼上課程網址，例如 `https://elearn.nsysu.edu.tw/course/12345/learning-activity`。貼上該課程的單一活動網址也可以下載整門課。
4. 選擇儲存位置，按「開始下載」。
5. 查看進度及結果；如有失敗，確認網路或權限後按「重新掃描並重試」。

若要嘗試查看名單，輸入學號、密碼及課程網址後按「查看課程成員（需平台授權）」；不需要選擇下載資料夾。若教材可讀但名單回應 HTTP 403，代表 TronClass 對此帳號關閉名單存取，程式不會改用其他資料來源繞過限制。

預設下載至程式旁的 `downloads` 資料夾，例如：

```text
downloads/
  課程_12345/
    第一章__123/
      課程簡介__456/
        講義__789.pdf
        .download-manifest.json
    .download-report.json
```

取消時會等待當前網路請求結束或逾時，再清理暫存檔；關閉視窗亦會先取消任務。
未完成附件不會列入成功紀錄，下次從該附件開頭重新下載。已存在的同名檔案不會被覆寫。
若舊版下載的 `.pptx` 無法由 PowerPoint 開啟，請檢查檔案開頭是否為 `%PDF-`；這代表平台提供的是 PDF 預覽，把副檔名改為 `.pdf` 即可開啟。更新後的下載器會檢查內容格式，重試時也不會把這類舊檔誤判為有效的 PPTX。

「記住帳密」沿用本機 `config.json`，**內容未加密**。此檔案、下載教材及虛擬環境已加入 `.gitignore`。
新版採用 HTTPS 憑證驗證；若憑證有問題會顯示錯誤，不會自動關閉驗證。

### 在 VS Code 執行

這個專案的套件安裝在 `.venv`。專案設定已將 Code Runner 的「Run Code」按鈕指定到 `.venv\Scripts\python.exe`，即使終端機顯示 Conda `base` 也會使用專案環境。
若終端機顯示 `>>>`，代表目前在 Python 互動模式；先輸入 `exit()` 回到 `PS>` 再重新執行。

若使用 VS Code Python 擴充套件的「執行 Python 檔案」，請點右下角的 Python 版本，選擇 `.venv\Scripts\python.exe`。若先前已選過 `base`，預設直譯器設定不會自動覆蓋，需手動切換一次。

也可以在「執行與偵錯」選擇「TronClass 下載器（專案 .venv）」並按 F5。此設定同樣明確指定專案虛擬環境。

在終端機直接執行：

```powershell
.\.venv\Scripts\python.exe Downloader_GUI.py
```

## 測試與打包

```powershell
# 核心測試（不登入、不連線學校）
.venv\Scripts\python -m unittest discover -s tests -p test_downloader.py -v

# 介面元件測試（需要桌面環境，使用暫存設定，不讀取真實帳密）
.venv\Scripts\python -m unittest discover -s tests -p test_gui.py -v

# 建立新版 EXE
.venv\Scripts\python -m pip install pyinstaller
.venv\Scripts\python -m PyInstaller --onefile --noconsole --collect-all customtkinter --name TronClass_Downloader Downloader_GUI.py
```

輸出為 `dist/TronClass_Downloader.exe`。尚未自行打包時，請執行 Python 原始碼測試新功能。

## 開發說明

- `Downloader_GUI.py`：介面、帳密設定與背景任務；使用 queue 將更新送回主執行緒。
- `tronclass_client.py`：登入、清單分頁、下載與紀錄，不依賴 GUI。
- `tests/`：模擬清單分頁、多附件、取消、失敗重試、損毀檔案、登入及 GUI 事件測試。

2026-09-08 與 2026-10-10 核對的中山平台公開前端：

- [章節與活動 API 呼叫](https://elearn.nsysu.edu.tw/static/77503-ccf74164.js)：`GET /api/courses/{course_id}/modules` 回傳 `modules`；`GET /api/courses/{course_id}/activities?sub_course_id=0` 回傳 `activities`。
- [課程成員 API 呼叫](https://elearn.nsysu.edu.tw/static/72914-965f4ad4.js)：公開前端的 `getMembers` 使用 `GET /api/courses/{course_id}/members`。是否提供名單仍以登入帳號的伺服器權限為準。
- 原版已使用 `GET /api/activities/{activity_id}` 的 `uploads`，及 `GET /api/uploads/reference/document/{reference_id}/url` 取得附件網址。

前端檔案雜湊與 API 可能隨平台改版而改變；清單格式不符、分頁資料不足或權限失敗時，程式會回報未完成。

本專案供學習與個人教材整理使用，請遵守教材的使用與分享授權。
