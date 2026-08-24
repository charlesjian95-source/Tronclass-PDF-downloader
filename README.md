# 🎓 NSYSU TronClass Downloader (中山大學網路大學終極下載器)

![Platform](https://img.shields.io/badge/Platform-Windows-blue.svg)
![Python](https://img.shields.io/badge/Python-3.x-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

這是一個專為 **國立中山大學網路大學 (TronClass)** 設計的自動化下載工具。
**🎉 全新 v1.0.0 版本已支援「免安裝執行檔」，不需具備任何程式基礎，雙擊即可直接使用！**

## ✨ Features (核心特色)
*   **免安裝環境**：提供打包好的 `.exe` 執行檔，電腦沒有安裝 Python 也能無痛使用。
*   **SSO 登入突破**：自動解析網頁 DOM Tree，抓取動態參數，無縫通過學校認證中心。
*   **狀態保持 (Session)**：登入一次即可自動管理 Cookie，精準提取真實檔案下載金鑰。
*   **資安防護**：採用終端機互動式讀取帳號密碼，原始碼公開透明，確保密碼零外洩風險。

---

## 🚀 快速使用教學 (推薦一般使用者)

如果你只想快速下載講義，請直接跟著以下步驟操作：

1. **下載程式**：前往本專案的 [Releases 頁面](https://github.com/charlesjian95-source/Tronclass-PDF-downloader/releases/latest)，下載最新的 `Downloader.exe` 檔案。
2. **執行程式**：雙擊打開 `Downloader.exe`。
   *(💡 小提醒：由於本程式未經微軟數位簽章，若 Windows Defender 跳出藍色警告畫面，請點擊「其他資訊」➔「仍要執行」即可)*
3. **輸入資訊**：程式啟動後，請依序在黑色終端機視窗中輸入：
   *   **學號**：例如 `B12345678`
   *   **密碼**：您的 TronClass 單一登入密碼
   *   **檔案網址**：貼上該章節的 learning-activity 網址

> 範例網址：https://elearn.nsysu.edu.tw/course/12345/learning-activity#/67890

<img width="800" alt="Image" src="https://github.com/user-attachments/assets/d0d04a4d-6115-45c6-a75f-da5ea7f0b620" />

腳本執行完畢後，PDF 教材將會**自動儲存於 `.exe` 檔案所在的同一個資料夾目錄下**。

---

## 💻 開發者指南 (從原始碼執行)

如果您想閱讀原始碼、自行修改程式，或是使用 Mac/Linux 系統，請參考以下步驟：

**【步驟 1】 Clone 專案與安裝套件**
```bash
git clone [https://github.com/charlesjian95-source/Tronclass-PDF-downloader.git](https://github.com/charlesjian95-source/Tronclass-PDF-downloader.git)
cd Tronclass-PDF-downloader
pip install -r requirements.txt
```

**【步驟 2】 啟動腳本**
```bash
python Downloader.py
```

---

## ⚠️ Disclaimer (免責聲明)

1. 本專案僅供程式語言學習、網路架構研究與學術交流使用。
2. 請勿將此腳本用於大量惡意爬取，以免對校方伺服器造成負擔。
3. 下載之課程教材版權均歸原作者及授課教授所有，請遵守智慧財產權，切勿隨意散佈。
