"""TronClass API and batch downloads, independent of the desktop interface."""

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import threading
import uuid
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://elearn.nsysu.edu.tw"
TIMEOUT = (10, 30)
MEDIA_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m3u8", ".mp3", ".wav", ".m4a"}


class DownloadError(Exception):
    pass


class Cancelled(DownloadError):
    pass


def parse_target(url):
    parsed = urlparse(url.strip())
    match = re.match(r"^/course/(\d+)(?:/|$)", parsed.path)
    if parsed.scheme != "https" or parsed.hostname != "elearn.nsysu.edu.tw" or not match:
        raise DownloadError("請貼上中山網路大學的 HTTPS 課程網址。")
    activity = re.fullmatch(r"/(\d+)(?:\?.*)?", parsed.fragment)
    return match.group(1), activity.group(1) if activity else None


def safe_name(name, limit=70):
    name = re.sub(r'[\x00-\x1f\\/:*?"<>|]', "_", str(name)).strip(" .")
    name = name[:limit].rstrip(" .") or "未命名"
    if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", name):
        name = "_" + name
    return name


def numeric_id(value):
    value = str(value)
    if not re.fullmatch(r"\d+", value):
        raise DownloadError("伺服器回傳無效的教材 ID。")
    return value


def describe_error(error):
    # Requests exceptions may contain signed download URLs; never log those.
    if isinstance(error, requests.exceptions.SSLError):
        return "HTTPS 憑證驗證失敗，請檢查電腦時間及憑證設定。"
    if isinstance(error, requests.Timeout):
        return "連線逾時，請稍後重試。"
    if isinstance(error, requests.RequestException):
        return "網路連線失敗，請檢查網路後重試。"
    if isinstance(error, DownloadError):
        return str(error)
    if isinstance(error, OSError):
        return "無法寫入檔案，請檢查資料夾權限、路徑長度與剩餘空間。"
    return "發生未預期的錯誤，請重試。"


@dataclass
class BatchResult:
    downloaded: int = 0
    skipped: int = 0
    excluded: int = 0
    failures: list = field(default_factory=list)
    cancelled: bool = False
    directory: str = ""


def file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, data):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


class TronClassClient:
    def __init__(self, session=None, cancel=None, emit=None):
        self.session = session if session is not None else requests.Session()
        self.cancel = cancel if cancel is not None else threading.Event()
        self.emit = emit or (lambda kind, value: None)
        self.session.headers.update({"User-Agent": "Mozilla/5.0 TronClassDownloader"})

    def close(self):
        self.session.close()

    def check_cancelled(self):
        if self.cancel.is_set():
            raise Cancelled("已取消下載。")

    def request(self, method, url, **kwargs):
        self.check_cancelled()
        response = self.session.request(method, url, timeout=TIMEOUT, **kwargs)
        if not 200 <= response.status_code < 300:
            status = response.status_code
            response.close()
            if status in (401, 403):
                raise DownloadError(f"無法存取（HTTP {status}），請確認登入狀態及課程權限。")
            raise DownloadError(f"伺服器回應 HTTP {status}，請稍後重試。")
        return response

    def get_json(self, path, params=None):
        with self.request("GET", BASE_URL + path, params=params) as response:
            self.check_cancelled()
            try:
                value = response.json()
            except ValueError:
                raise DownloadError("伺服器未回傳教材資料，可能需要重新登入或網站格式已更新。") from None
            if not isinstance(value, (dict, list)):
                raise DownloadError("伺服器回傳的資料格式不符預期。")
            return value

    def login(self, username, password):
        self.emit("log", "正在登入中山網路大學…")
        with self.request("GET", BASE_URL + "/login") as response:
            soup = BeautifulSoup(response.text, "html.parser")
            form = next((form for form in soup.find_all("form")
                         if form.find("input", {"type": "password"})), None)
            if form is None:
                raise DownloadError("找不到帳密登入表單，可能需要使用瀏覽器完成驗證。")
            action = urljoin(response.url, form.get("action") or response.url)
            destination = urlparse(action)
            if destination.scheme != "https" or not (destination.hostname or "").endswith(".nsysu.edu.tw"):
                raise DownloadError("登入表單指向非中山大學的 HTTPS 網址，已停止登入。")
            fields = {item["name"]: item.get("value", "") for item in form.find_all("input")
                      if item.get("name") and item.get("type") == "hidden"}
            fields.update(username=username, password=password)
        with self.request("POST", action, data=fields) as response:
            soup = BeautifulSoup(response.text, "html.parser")
            if soup.find("input", {"type": "password"}) or "Invalid username or password" in response.text:
                raise DownloadError("登入未完成，請檢查帳密或是否需要額外驗證。")
        self.emit("log", "登入流程完成，正在確認課程存取權限…")

    def list_all(self, path, key, params=None):
        """Handle paged responses and the school's unpaged activities response.

        Probe the next page even for a short page, since servers may cap page_size.
        Identical pages without pagination metadata mean the endpoint is unpaged.
        With metadata, repeated pages are an error rather than silent truncation.
        """
        result, seen, signatures = [], set(), set()
        for page in range(1, 10001):
            self.check_cancelled()
            payload = self.get_json(path, {**(params or {}), "page": page, "page_size": 100})
            rows = payload if isinstance(payload, list) else payload.get(key)
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise DownloadError(f"{key} 清單格式已變更，無法確認是否取得完整教材。")
            meta = payload if isinstance(payload, dict) else {}
            pagination = meta.get("pagination")
            if isinstance(pagination, dict):
                meta = {**meta, **pagination}
            total, pages = meta.get("total"), meta.get("pages")
            total = total if isinstance(total, int) and total >= 0 else None
            pages = pages if isinstance(pages, int) and pages >= 0 else None
            signature = json.dumps(rows, sort_keys=True)
            if rows and signature in signatures:
                if total is not None or pages is not None:
                    raise DownloadError("伺服器重複回傳同一頁，無法確認教材清單完整性。")
                break
            signatures.add(signature)
            for row in rows:
                identity = numeric_id(row.get("id"))
                if identity not in seen:
                    seen.add(identity)
                    result.append(row)
            if total is not None and len(result) >= total:
                break
            if not rows or (pages is not None and page >= pages):
                if total is not None and len(result) < total:
                    raise DownloadError("教材清單筆數不足，請重試；本次不會宣告下載完整。")
                break
            if self.cancel.wait(0.15):
                self.check_cancelled()
        else:
            raise DownloadError("教材清單超出分頁上限，請檢查平台回應。")
        return result

    def download_one(self, activity_id, upload, directory, manifest):
        reference = numeric_id(upload.get("reference_id"))
        key = f"{activity_id}:{reference}"
        name = str(upload.get("name") or f"附件_{reference}")
        # Include remote metadata so changed uploads do not reuse a stale copy.
        version = {key: upload.get(key) for key in ("name", "size", "updated_at", "md5", "sha256")}
        saved = manifest.get(key)
        if isinstance(saved, dict) and saved.get("version") == version:
            existing = (directory / saved.get("path", "")).resolve()
            if (existing.is_relative_to(directory.resolve()) and existing.is_file()
                    and existing.stat().st_size == saved.get("size")
                    and file_digest(existing) == saved.get("sha256")):
                self.check_cancelled()
                return False

        suffix = Path(name).suffix
        filename = (safe_name(Path(name).stem, 65) + "__" + reference + "." + safe_name(suffix[1:], 12)
                    if suffix else safe_name(name, 65) + "__" + reference)
        target = directory / filename
        counter = 2
        while target.exists():
            target = directory / f"{Path(filename).stem} ({counter}){Path(filename).suffix}"
            counter += 1
        temporary = directory / (uuid.uuid4().hex + ".part")
        data = self.get_json(f"/api/uploads/reference/document/{reference}/url", {
            "preview": "true", "refer_id": activity_id, "refer_type": "learning_activity",
        })
        real_url = data.get("url") if isinstance(data, dict) else None
        if not isinstance(real_url, str) or urlparse(real_url).scheme != "https":
            raise DownloadError("附件未提供有效的 HTTPS 下載網址。")
        try:
            with self.request("GET", real_url, stream=True) as response:
                if "text/html" in response.headers.get("Content-Type", "").lower():
                    raise DownloadError("下載回應是網頁而非附件，可能登入已過期。")
                digest, size = hashlib.sha256(), 0
                with temporary.open("wb") as output:
                    for chunk in response.iter_content(128 * 1024):
                        self.check_cancelled()
                        if chunk:
                            output.write(chunk)
                            digest.update(chunk)
                            size += len(chunk)
                self.check_cancelled()
                expected = response.headers.get("Content-Length")
                if expected and not response.headers.get("Content-Encoding") and size != int(expected):
                    raise DownloadError("附件傳輸不完整，請重試。")
                if size == 0:
                    raise DownloadError("附件內容為空，請重試。")
            # Exclusive creation protects existing files, including another running instance.
            with target.open("xb") as output, temporary.open("rb") as source:
                try:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        self.check_cancelled()
                        output.write(chunk)
                except BaseException:
                    output.close()
                    target.unlink(missing_ok=True)
                    raise
            manifest[key] = {"path": target.name, "size": size, "sha256": digest.hexdigest(), "version": version}
            return True
        finally:
            temporary.unlink(missing_ok=True)

    def run(self, target_url, output_root, whole_course=True):
        course_id, activity_id = parse_target(target_url)
        if not whole_course and activity_id is None:
            raise DownloadError("單一活動模式需要包含 learning-activity#/活動ID 的網址。")
        result = BatchResult()
        course_directory = Path(output_root).resolve() / f"課程_{course_id}"
        result.directory = str(course_directory)
        course_directory.mkdir(parents=True, exist_ok=True)
        try:
            modules = {}
            if whole_course:
                self.emit("log", "正在讀取課程章節與全部活動…")
                for module in self.list_all(f"/api/courses/{course_id}/modules", "modules"):
                    module_id = numeric_id(module["id"])
                    modules[module_id] = safe_name(module.get("name") or module.get("title") or "章節", 35) + "__" + module_id
                activities = self.list_all(f"/api/courses/{course_id}/activities", "activities", {"sub_course_id": 0})
            else:
                activities = [{"id": activity_id}]
            self.emit("log", f"找到 {len(activities)} 個活動，正在整理附件…")
            tasks, seen = [], set()
            for index, activity in enumerate(activities, 1):
                self.check_cancelled()
                aid = numeric_id(activity["id"])
                self.emit("status", f"整理教材 {index}/{len(activities)}")
                try:
                    detail = self.get_json(f"/api/activities/{aid}")
                    if not isinstance(detail, dict) or "uploads" not in detail:
                        # Non-document activities legitimately have no uploads.
                        if isinstance(detail, dict) and detail.get("type") and detail.get("type") != "material":
                            continue
                        raise DownloadError("活動未回傳附件清單，請確認權限或平台格式。")
                    uploads = detail["uploads"]
                    if not isinstance(uploads, list):
                        raise DownloadError("附件清單格式不符預期。")
                    module_id = str(detail.get("module_id") or activity.get("module_id") or "")
                    chapter = modules.get(module_id, "未分類" + ("__" + safe_name(module_id, 20) if module_id else ""))
                    activity_directory = course_directory / chapter / (safe_name(detail.get("title") or activity.get("title") or "活動", 35) + "__" + aid)
                    for upload in uploads:
                        if not isinstance(upload, dict):
                            raise DownloadError("附件資料格式不符預期。")
                        if Path(str(upload.get("name", ""))).suffix.lower() in MEDIA_EXTENSIONS:
                            result.excluded += 1
                            continue
                        reference = numeric_id(upload.get("reference_id"))
                        if (aid, reference) not in seen:
                            seen.add((aid, reference))
                            tasks.append((aid, upload, activity_directory))
                except Cancelled:
                    raise
                except Exception as error:
                    result.failures.append({"activity_id": aid, "stage": "清單", "error": describe_error(error)})
                    self.emit("log", f"活動 {aid} 讀取失敗：{describe_error(error)}")
                if self.cancel.wait(0.15):
                    self.check_cancelled()

            self.emit("log", f"共有 {len(tasks)} 個文件附件待處理。")
            self.emit("progress", (0, len(tasks)))
            for index, (aid, upload, directory) in enumerate(tasks, 1):
                self.check_cancelled()
                name = str(upload.get("name") or "未命名附件")
                self.emit("status", f"處理附件 {index}/{len(tasks)}：{name}")
                try:
                    directory.mkdir(parents=True, exist_ok=True)
                    manifest_path = directory / ".download-manifest.json"
                    try:
                        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                        if not isinstance(manifest, dict):
                            manifest = {}
                    except (FileNotFoundError, ValueError):
                        manifest = {}
                    downloaded = self.download_one(aid, upload, directory, manifest)
                    if downloaded:
                        write_json(manifest_path, manifest)
                        result.downloaded += 1
                        self.emit("log", f"已下載：{name}")
                    else:
                        result.skipped += 1
                        self.emit("log", f"已存在且校驗一致，略過：{name}")
                except Cancelled:
                    raise
                except Exception as error:
                    result.failures.append({"activity_id": aid, "reference_id": upload.get("reference_id"), "name": name, "stage": "下載", "error": describe_error(error)})
                    self.emit("log", f"下載失敗：{name} — {describe_error(error)}")
                self.emit("progress", (index, len(tasks)))
                if self.cancel.wait(0.2):
                    self.check_cancelled()
        except Cancelled:
            result.cancelled = True
        except Exception as error:
            result.failures.append({"stage": "課程清單", "error": describe_error(error)})
            self.emit("log", describe_error(error))
        finally:
            try:
                write_json(course_directory / ".download-report.json", result.__dict__)
            except OSError:
                self.emit("log", "無法儲存下載報告，請保留畫面上的失敗訊息。")
        return result
