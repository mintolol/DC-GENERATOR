#!/usr/bin/env python3
"""
Humanizer Standalone - Execute Humanizer using tokens from input/tokens.txt
"""

import sys
import os

# UTF-8 encoding for Windows
if os.name == 'nt':
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass

# GUI mode detection
GUI_MODE = os.environ.get("GUI_MODE") == "1"

# Simplify output in GUI mode
if GUI_MODE:
    P = C = G = Y = D = RD = W = R = ""
    SIMPLE_OUTPUT = True
else:
    P = "\033[38;2;121;3;255m"
    C = "\033[38;2;3;248;252m"
    G = "\033[38;2;68;255;0m"
    Y = "\033[38;2;252;248;3m"
    D = "\033[38;2;92;94;91m"
    RD = "\033[38;2;255;80;80m"
    W = "\033[97m"
    R = "\033[0m"
    SIMPLE_OUTPUT = False
    try:
        import colorama
        colorama.init(autoreset=True)
    except Exception:
        pass

import json
import time
import random
import threading
import asyncio
import websockets
from python_socks.async_.asyncio import Proxy
import base64
import re
import hashlib
from urllib.parse import quote, urlparse
from datetime import datetime
import warnings
from urllib3.exceptions import InsecureRequestWarning
warnings.simplefilter('ignore', InsecureRequestWarning)

import primp
from colorama import Fore, Style
from PIL import Image

from pathlib import Path
from typing import List, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import uuid

# Directory configuration
SCRIPT_DIR = Path(__file__).resolve().parent.parent  # Go up from engine/
DATA_DIR = SCRIPT_DIR / "engine" / "data"
INPUT_DIR = SCRIPT_DIR / "input"
AVATARS_DIR = SCRIPT_DIR / "engine" / "avatar"

TOKENS_FILE = INPUT_DIR / "tokens.txt"
PROXIES_FILE = INPUT_DIR / "proxies.txt"
BIOS_FILE = DATA_DIR / "bios.txt"
NAMES_FILE = DATA_DIR / "names.txt"
PRONOUNS_FILE = DATA_DIR / "pronouns.txt"

# Load config.json
try:
    config_path = SCRIPT_DIR / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
except Exception as e:
    print(f"Failed to load config.json: {e}")
    config = {}

hz_config = config.get("humanizer", {})
MAX_THREADS = config.get("threading", {}).get("humanizer", hz_config.get("max_threads", 3))
AVATAR_DIMENSION = hz_config.get("avatar_dimension", 256)
MAX_AVATAR_CACHE = hz_config.get("max_avatar_cache", 100)
UPDATE_DISPLAY_NAME = hz_config.get("display_name", True)
UPDATE_BIO = hz_config.get("bio", True)
UPDATE_PRONOUNS = hz_config.get("pronouns", True)
UPDATE_AVATAR = hz_config.get("avatar", True)
UPDATE_HYPESQUAD = hz_config.get("hypesquad", True)
RETRY_LIMIT = hz_config.get("retries", 3)

# ========== Humanizer用定数 ==========
HYPESQUAD_HOUSES = {
    1: "Bravery",
    2: "Brilliance",
    3: "Balance"
}
DISCORD_API = "https://discord.com/api/v9"
DISCORD_GATEWAY = "wss://gateway.discord.gg/?v=9&encoding=json"
FALLBACK_BUILD_NUMBER = 519006
DISCORD_CLIENT_VERSION = "1.0.9171"
ELECTRON_VERSION = "34.5.1"
CHROME_VERSION_ELECTRON = "132"
DEFAULT_USER_AGENT = (
    f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    f"(KHTML, like Gecko) discord/{DISCORD_CLIENT_VERSION} "
    f"Chrome/{CHROME_VERSION_ELECTRON}.0.0.0 Electron/{ELECTRON_VERSION} Safari/537.36"
)

# グローバル変数
_async_loop = None
_async_loop_thread = None
print_lock = threading.Lock()
file_lock = threading.Lock()
proxy_manager = None

def _init_async_loop():
    """非同期イベントループを初期化"""
    global _async_loop, _async_loop_thread
    try:
        _async_loop = asyncio.new_event_loop()
        _async_loop_thread = threading.Thread(target=_async_loop.run_forever, daemon=True)
        _async_loop_thread.start()
    except Exception:
        pass

# モジュール読み込み時に初期化
_init_async_loop()

def fetch_build_number() -> int:
    """Discord のビルド番号を取得"""
    try:
        resp = primp.Client(verify=False).get("https://discord.com/login", timeout=10)
        if resp.status_code != 200:
            return FALLBACK_BUILD_NUMBER
        asset_urls = re.findall(r'/assets/([a-zA-Z0-9_-]+)\.js', resp.text)
        if not asset_urls:
            return FALLBACK_BUILD_NUMBER
        for asset_hash in reversed(asset_urls):
            try:
                js_resp = primp.Client(verify=False).get(
                    f"https://discord.com/assets/{asset_hash}.js",
                    timeout=10
                )
                if js_resp.status_code != 200:
                    continue
                match = re.search(r'buildNumber["\s:,]+(\d{4,7})', js_resp.text)
                if match:
                    return int(match.group(1))
            except Exception:
                continue
        return FALLBACK_BUILD_NUMBER
    except Exception:
        return FALLBACK_BUILD_NUMBER

BUILD_NUMBER = fetch_build_number()


class Logger:
    """Simple logging class"""
    @staticmethod
    def _safe_print(msg: str):
        """Print safely (avoid encoding errors)"""
        try:
            # Use print() instead of direct sys.stdout manipulation
            print(msg, flush=True)
        except ValueError as e:
            # Handle "I/O operation on closed file" - silently ignore
            if "closed file" in str(e):
                return
        except Exception:
            # Silently ignore all other print errors
            pass
    
    @staticmethod
    def status(msg: str):
        if SIMPLE_OUTPUT:
            Logger._safe_print(f"[OK] {msg}")
        else:
            Logger._safe_print(f"  {G}[OK]{R} {msg}")
    
    @staticmethod
    def info(msg: str):
        if SIMPLE_OUTPUT:
            Logger._safe_print(f"[*] {msg}")
        else:
            Logger._safe_print(f"  {C}[*]{R} {msg}")
    
    @staticmethod
    def warn(msg: str):
        if SIMPLE_OUTPUT:
            Logger._safe_print(f"[!] {msg}")
        else:
            Logger._safe_print(f"  {Y}[!]{R} {msg}")
    
    @staticmethod
    def error(msg: str):
        if SIMPLE_OUTPUT:
            Logger._safe_print(f"[X] {msg}")
        else:
            Logger._safe_print(f"  {RD}[X]{R} {msg}")


Log = Logger()

# ========== ヘルパー関数 ==========

def get_timestamp() -> str:
    """タイムスタンプを取得"""
    return datetime.now().strftime("%H:%M:%S")

def mask_token(token: str) -> str:
    """トークンをマスク表示"""
    if len(token) <= 20:
        return token[:10] + "****"
    return token[:10] + "****" + token[-10:]

def generate_super_properties(
    launch_id: str, signature: str, heartbeat_id: str, native_build: int
) -> str:
    """Discord x-super-properties を生成"""
    return base64.b64encode(json.dumps({
        "os": "Windows",
        "browser": "Discord Client",
        "release_channel": "stable",
        "client_version": DISCORD_CLIENT_VERSION,
        "os_version": "10.0.26100",
        "os_arch": "x64",
        "app_arch": "x64",
        "system_locale": "en-US",
        "has_client_mods": False,
        "browser_user_agent": DEFAULT_USER_AGENT,
        "browser_version": ELECTRON_VERSION,
        "client_build_number": BUILD_NUMBER,
        "native_build_number": native_build,
        "client_event_source": None,
        "client_launch_id": launch_id,
        "launch_signature": signature,
        "client_heartbeat_session_id": heartbeat_id,
    }, separators=(",", ":")).encode()).decode()

def log(log_type: str, token: str, message: str):
    """ログを出力（トークン情報付き）"""
    timestamp = get_timestamp()
    masked = mask_token(token)
    with print_lock:
        ts = f"{Fore.LIGHTBLACK_EX}[{timestamp}]{Style.RESET_ALL}"
        tok = f"{Fore.LIGHTBLACK_EX}[{Style.RESET_ALL}Token : {Fore.CYAN}{masked}{Style.RESET_ALL}{Fore.LIGHTBLACK_EX}]{Style.RESET_ALL}"
        if log_type == "SUCCESS":
            status = f"{Fore.GREEN}[SUCCESS]{Style.RESET_ALL}"
        elif log_type == "FAILED":
            status = f"{Fore.RED}[FAILED]{Style.RESET_ALL}"
        elif log_type == "WARN":
            status = f"{Fore.YELLOW}[WARN]{Style.RESET_ALL}"
        elif log_type == "INFO":
            status = f"{Fore.CYAN}[INFO]{Style.RESET_ALL}"
        else:
            status = f"[{log_type}]"
        if " : " in message and message.startswith("[") and message.endswith("]"):
            inner = message[1:-1]
            parts = inner.split(" : ", 1)
            if len(parts) == 2:
                desc, value = parts
                msg = f"{Fore.LIGHTBLACK_EX}[{Style.RESET_ALL}{Fore.WHITE}{desc}{Style.RESET_ALL} : {Fore.CYAN}{value}{Style.RESET_ALL}{Fore.LIGHTBLACK_EX}]{Style.RESET_ALL}"
            else:
                msg = f"{Fore.LIGHTBLACK_EX}[{Style.RESET_ALL}{Fore.WHITE}{inner}{Style.RESET_ALL}{Fore.LIGHTBLACK_EX}]{Style.RESET_ALL}"
        else:
            msg = message
        try:
            print(f"{ts} - {status} - {tok} → {msg}")
        except Exception:
            pass

def parse_proxy(proxy_string: str) -> Optional[str]:
    """プロキシ文字列をパース"""
    if not proxy_string:
        return None
    proxy = proxy_string.strip()
    if proxy.startswith('#'):
        return None
    if '://' in proxy:
        parsed = urlparse(proxy)
        if parsed.hostname and parsed.port:
            return proxy
        return None
    if '@' in proxy:
        # Format: user:pass@host:port
        try:
            auth, host_port = proxy.split('@')
            user, password = auth.split(':', 1)
            host, port = host_port.split(':', 1)
            return f"http://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}"
        except Exception:
            return None
    
    # Format: host:port:user:pass
    parts = proxy.split(":")
    if len(parts) == 4:
        host, port, user, password = parts
        return f"http://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}"
    elif len(parts) == 2:
        return f"http://{parts[0]}:{parts[1]}"
    return None


def load_file_lines(filepath: Path) -> List[str]:
    """Load lines from file"""
    if not filepath.exists():
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return [line.strip() for line in f.readlines() if line.strip()]
    except Exception:
        return []


# ========== Humanizer クラス ==========

class Humanizer:
    def __init__(self, token: str, proxy: Optional[str] = None):
        self.token = token
        self.proxy = proxy
        self.client = primp.Client(
            verify=False,
            proxy=parse_proxy(proxy) if proxy else None
        )
        self.user_agent = DEFAULT_USER_AGENT
        self.session_id = None
        self.proxy_failed = False
        self.is_locked = False
        self.installation_id = f"{random.randint(10**18, 10**19 - 1)}.{''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_', k=22))}"
        self._launch_id = str(uuid.uuid4())
        self._signature = str(uuid.uuid4())
        self._heartbeat_id = str(uuid.uuid4())
        self._native_build = random.randint(65600, 65800)
        self._super_props = generate_super_properties(
            self._launch_id, self._signature, self._heartbeat_id, self._native_build
        )
    
    def get_fingerprint(self):
        """Discord フィンガープリントを取得"""
        try:
            r = self.client.get("https://discord.com/api/v9/experiments", timeout=30)
            if r.status_code == 200:
                return r.json().get("fingerprint")
        except:
            pass
        return None
    
    async def _send_identify(self, ws) -> bool:
        """WebSocket IDENTIFY ペイロードを送信"""
        try:
            hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
            if hello.get("op") != 10:
                return False
            identify_payload = {
                "op": 2,
                "d": {
                    "token": self.token,
                    "capabilities": 16381,
                    "properties": {
                        "os": "Windows",
                        "browser": "Discord Client",
                        "release_channel": "stable",
                        "client_version": DISCORD_CLIENT_VERSION,
                        "os_version": "10.0.26100",
                        "os_arch": "x64",
                        "app_arch": "x64",
                        "system_locale": "en-US",
                        "browser_user_agent": self.user_agent,
                        "browser_version": ELECTRON_VERSION,
                        "os_sdk_version": "26100",
                        "client_build_number": BUILD_NUMBER,
                        "native_build_number": self._native_build,
                        "client_event_source": None,
                        "design_id": 0
                    },
                    "presence": {
                        "status": "online",
                        "since": 0,
                        "activities": [],
                        "afk": False
                    },
                    "compress": False,
                    "client_state": {
                        "guild_versions": {},
                        "highest_last_message_id": "0",
                        "read_state_version": 0,
                        "user_guild_settings_version": -1,
                        "user_settings_version": -1,
                        "private_channels_version": "0",
                        "api_code_version": 0
                    }
                }
            }
            await ws.send(json.dumps(identify_payload))
            return True
        except Exception:
            return False
    
    async def _wait_for_ready(self, ws) -> bool:
        """READY イベントを待機"""
        for _ in range(12):
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                op = msg.get("op")
                t = msg.get("t")
                if op == 11 or (op == 0 and t != "READY"):
                    continue
                if t == "READY":
                    self.session_id = msg["d"].get("session_id")
                    return True
                if op == 9:
                    return False
            except asyncio.TimeoutError:
                break
        return False
    
    async def update_account_with_live_session(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """ライブセッション経由でアカウントを更新"""
        if getattr(self, "is_locked", False):
            return {"success": False, "error": "Token Locked"}
        headers = self.get_headers()
        loop = asyncio.get_event_loop()
        if "avatar" not in payload:
            direct = await loop.run_in_executor(None, lambda: self.update_user_profile(payload, headers))
            if direct.get("success") or direct.get("captcha") or direct.get("rate_limited"):
                return direct
            if not direct.get("unknown_session"):
                return direct
        
        async def _ws_patch(ws) -> Dict[str, Any]:
            if not await self._send_identify(ws):
                return {"success": False, "error": "Gateway IDENTIFY failed"}
            if not await self._wait_for_ready(ws):
                return {"success": False, "error": "Gateway READY timeout"}
            return await loop.run_in_executor(None, lambda: self.update_user_profile(payload, headers))
        
        try:
            extra_headers = {"User-Agent": self.user_agent}
            if self.proxy:
                parsed_px = parse_proxy(self.proxy)
                if not parsed_px:
                    return {"success": False, "error": "Invalid proxy string"}
                proxy = Proxy.from_url(parsed_px)
                sock = await proxy.connect(dest_host="gateway.discord.gg", dest_port=443)
                async with websockets.connect(
                    DISCORD_GATEWAY,
                    additional_headers=extra_headers,
                    sock=sock,
                    server_hostname="gateway.discord.gg",
                    open_timeout=60,
                    close_timeout=10,
                    max_size=None
                ) as ws:
                    return await _ws_patch(ws)
            else:
                async with websockets.connect(
                    DISCORD_GATEWAY,
                    additional_headers=extra_headers,
                    open_timeout=60,
                    close_timeout=10,
                    max_size=None
                ) as ws:
                    return await _ws_patch(ws)
        except Exception as e:
            err_str = str(e)
            if not err_str:
                err_str = type(e).__name__
            if self.proxy and ("proxy" in err_str.lower() or "connect" in err_str.lower()):
                self.proxy_failed = True
            return {"success": False, "error": err_str}
    
    def update_account_sync(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """同期的にアカウントを更新"""
        if _async_loop is None:
            return {"success": False, "error": "Async loop not initialized"}
        
        max_retries = 2
        last_error = None
        for attempt in range(max_retries):
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self.update_account_with_live_session(payload), _async_loop
                )
                result = future.result()
                if result["success"]:
                    return result
                error = str(result.get("error", ""))
                if self._is_transient_error(error):
                    last_error = self._clean_error(error)
                    if proxy_manager and attempt < max_retries - 1:
                        new_proxy = proxy_manager.get_proxy()
                        if new_proxy:
                            self.proxy = new_proxy
                            self.client = primp.Client(verify=False, proxy=parse_proxy(new_proxy))
                        continue
                return result
            except Exception as e:
                last_error = self._clean_error(str(e))
                if attempt < max_retries - 1 and proxy_manager:
                    new_proxy = proxy_manager.get_proxy()
                    if new_proxy:
                        self.proxy = new_proxy
                        self.client = primp.Client(verify=False, proxy=parse_proxy(new_proxy))
                    continue
        return {"success": False, "error": last_error or "Max retries reached"}
    
    def _clean_error(self, error) -> str:
        """エラーメッセージをクリーニング"""
        error = str(error)
        if "RATE_LIMIT" in error or "rate limit" in error.lower() or "too often" in error.lower():
            return "Rate Limited"
        if "curl:" in error:
            if "(56)" in error:
                return "Proxy closed"
            elif "(28)" in error:
                return "Timeout"
            elif "(7)" in error:
                return "Proxy failed"
            else:
                match = re.search(r'curl: \((\d+)\)', error)
                if match:
                    return f"Curl {match.group(1)}"
        if "Unknown Session" in error:
            return "Bad session"
        if "received 4000" in error or "4000 (private" in error:
            return "Token locked / flagged (WS 4000)"
        if "received 4001" in error:
            return "Invalid token (WS 4001)"
        if "received 4004" in error:
            return "Auth failed (WS 4004)"
        if "received 4006" in error:
            return "Session invalid (WS 4006)"
        if "Unauthorized" in error or "401" in error:
            return "Unauthorized"
        if "captcha" in error.lower():
            return "Captcha"
        if "Invalid Form Body" in error:
            return "Invalid request"
        if "message" in error and "code" in error:
            match = re.search(r"'message': '([^']+)'", error)
            if match:
                msg = match.group(1)
                if len(msg) > 25:
                    return msg[:22] + "..."
                return msg
        if len(error) > 80:
            return error[:77] + "..."
        return error
    
    def get_headers(self) -> Dict[str, str]:
        """Discord API リクエストヘッダーを生成"""
        headers = {
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br",
            "accept-language": "en-US",
            "authorization": self.token,
            "content-type": "application/json",
            "user-agent": self.user_agent,
            "x-debug-options": "bugReporterEnabled",
            "x-discord-locale": "en-US",
            "x-discord-timezone": "Asia/Calcutta",
            "x-installation-id": self.installation_id,
            "x-super-properties": self._super_props
        }
        fp = self.get_fingerprint()
        if fp:
            headers["x-fingerprint"] = fp
        return headers
    
    def _is_transient_error(self, error_str: str) -> bool:
        """一時的なエラーかどうかを判定"""
        lower = error_str.lower()
        return any(kw in lower for kw in (
            "connection", "proxy", "timeout", "reset", "connect",
            "sending", "refused", "unreachable", "eof", "read error",
            "gateway ready", "gateway identify", "gateway",
            "no close frame", "connection closed", "websocket"
        ))
    
    def _api_call_with_retry(self, method: str, url: str, data: Dict[str, Any],
                              headers: Dict[str, str], max_retries: int = 5) -> Dict[str, Any]:
        """リトライ機能付きで API呼び出しを実行"""
        if getattr(self, "is_locked", False):
            return {"success": False, "error": "Token Locked"}
        last_result = None
        for attempt in range(max_retries):
            if getattr(self, "is_locked", False):
                return {"success": False, "error": "Token Locked"}
            try:
                if method.upper() == "POST":
                    resp = self.client.post(url, headers=headers, json=data, timeout=60)
                else:
                    resp = self.client.patch(url, headers=headers, json=data, timeout=60)
                if resp.status_code in (200, 204):
                    try:
                        data = resp.json() if resp.text and resp.status_code == 200 else {}
                    except Exception:
                        data = {}
                    return {"success": True, "data": data}
                try:
                    error_data = resp.json() if resp.text and resp.text.strip() else {}
                except Exception:
                    error_data = {}
                if error_data.get("captcha_key"):
                    return {"success": False, "captcha": True, "error": error_data}
                if resp.status_code == 400 and isinstance(error_data, dict):
                    code = error_data.get("code")
                    if code == 10020:
                        return {"success": False, "unknown_session": True, "error": "Unknown Session"}
                    errors = error_data.get("errors", {})
                    for field_errors in errors.values():
                        for err in field_errors.get("_errors", []):
                            if err.get("code") == "AVATAR_RATE_LIMIT":
                                return {"success": False, "rate_limited": True, "retry_after": 0, "error": "Avatar Rate Limited"}
                if resp.status_code == 429:
                    try:
                        ra_header = resp.headers.get("retry-after") or resp.headers.get("Retry-After")
                        ra_body = error_data.get("retry_after", 0) if isinstance(error_data, dict) else 0
                        retry_after = float(ra_header) if ra_header else float(ra_body or 0)
                    except (TypeError, ValueError):
                        retry_after = 0
                    wait_time = max(retry_after, 1.0)
                    time.sleep(wait_time)
                    continue
                last_result = {"success": False, "error": error_data}
                if resp.status_code in (401, 403):
                    self.is_locked = True
                    return last_result
            except Exception as e:
                error_str = str(e)
                last_result = {"success": False, "error": error_str}
                if self.proxy and self._is_transient_error(error_str):
                    self.proxy_failed = True
                if self._is_transient_error(error_str) and proxy_manager and attempt < max_retries - 1:
                    new_proxy = proxy_manager.get_proxy()
                    if new_proxy:
                        self.proxy = new_proxy
                        self.client = primp.Client(verify=False, proxy=parse_proxy(new_proxy))
                    continue
                if attempt >= max_retries - 1:
                    return last_result
        return last_result or {"success": False, "error": "Max retries reached"}
    
    def update_user_profile(self, data: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        """ユーザープロファイルを更新"""
        return self._api_call_with_retry("patch", f"{DISCORD_API}/users/@me", data, headers)
    
    def update_profile_fields(self, data: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        """プロファイルフィールドを更新"""
        return self._api_call_with_retry("patch", f"{DISCORD_API}/users/@me/profile", data, headers)
    
    def set_hypesquad(self, house_id: int, headers: Dict[str, str], retry_count: int = 0) -> Dict[str, Any]:
        """HypeSquad ハウスを設定"""
        time.sleep(random.uniform(2, 5))
        house_name = HYPESQUAD_HOUSES.get(house_id, "Unknown")
        try:
            check = self.client.get(
                f"{DISCORD_API}/users/@me",
                headers=headers,
                timeout=30
            )
            if check.status_code == 200:
                data = check.json()
                flags = data.get("flags", 0)
                if flags & 0xE:
                    existing_house = None
                    for hid, hname in HYPESQUAD_HOUSES.items():
                        if flags & (1 << hid):
                            existing_house = hname
                            break
                    if existing_house:
                        log("INFO", self.token, f"[HypeSquad Already Set : {existing_house}]")
                        return {"success": True, "house_name": existing_house, "already_set": True}
        except Exception:
            pass
        res = self._api_call_with_retry(
            "post",
            f"{DISCORD_API}/hypesquad/online",
            {"house_id": house_id},
            headers,
            max_retries=2
        )
        if res.get("success"):
            return {"success": True, "house_name": house_name}
        if retry_count < RETRY_LIMIT:
            log("WARN", self.token, f"[HypeSquad Retry : {retry_count + 1}/{RETRY_LIMIT} for {house_name}]")
            time.sleep(random.uniform(2.0, 4.0))
            return self.set_hypesquad(house_id, headers, retry_count + 1)
        return {"success": False, "error": f"HypeSquad {house_name} not applied - Account may already have a badge or is rate limited", "house_name": house_name}
    
    def process(self, names: List[str], bios: List[str], pronouns_list: List[str],
                avatar_files: List[Path], avatar_loader, update_flags: Dict[str, bool] = None) -> bool:
        """プロファイルカスタマイズを処理"""
        if update_flags is None:
            update_flags = {
                "display_name": UPDATE_DISPLAY_NAME,
                "bio": UPDATE_BIO,
                "pronouns": UPDATE_PRONOUNS,
                "avatar": UPDATE_AVATAR,
                "hypesquad": UPDATE_HYPESQUAD
            }
        
        headers = self.get_headers()
        success = True
        parallel_tasks = []
        account_payload = {}
        avatar_name = None
        
        if update_flags.get("avatar", True) and avatar_files:
            avatar_path = random.choice(avatar_files)
            avatar_b64 = avatar_loader(avatar_path)
            if avatar_b64:
                account_payload["avatar"] = avatar_b64
                av_hash = hashlib.md5(avatar_b64[:100].encode()).hexdigest()
                now = datetime.now()
                now_str = now.strftime("%B {d}, %Y at {t}").format(
                    d=now.day,
                    t=now.strftime("%I:%M %p").lstrip("0")
                )
                account_payload["avatar_description"] = f"{av_hash}, added {now_str}"
                avatar_name = avatar_path.name
        
        display_name = None
        if update_flags.get("display_name", True) and names:
            display_name = random.choice(names)
            account_payload["global_name"] = display_name
        
        if account_payload:
            parallel_tasks.append(("account", (account_payload, avatar_name, display_name)))
        
        profile_payload = {}
        bio = None
        if update_flags.get("bio", True) and bios:
            bio = random.choice(bios)
            profile_payload["bio"] = bio
        
        pronouns = None
        if update_flags.get("pronouns", True) and pronouns_list:
            pronouns = random.choice(pronouns_list)
            profile_payload["pronouns"] = pronouns
        
        if profile_payload:
            parallel_tasks.append(("profile", (profile_payload, bio, pronouns)))
        
        house_id = None
        house_name = None
        if update_flags.get("hypesquad", True):
            time.sleep(random.uniform(0, 3))
            house_id = random.choice([1, 2, 3])
            house_name = HYPESQUAD_HOUSES[house_id]
            parallel_tasks.append(("hypesquad", (house_id, house_name)))
        
        if parallel_tasks:
            def _run_field(task_type, value):
                if getattr(self, "is_locked", False):
                    return (task_type, {"success": False, "error": "Token Locked"}, value)
                h = headers.copy()
                if task_type == "account":
                    payload, _, _ = value
                    if "avatar" in payload:
                        return ("account", self.update_account_sync(payload), value)
                    else:
                        return ("account", self.update_user_profile(payload, h), value)
                elif task_type == "profile":
                    payload, _, _ = value
                    return ("profile", self.update_profile_fields(payload, h), value)
                elif task_type == "hypesquad":
                    hid, _ = value
                    return ("hypesquad", self.set_hypesquad(hid, h), value)
                return ("unknown", {"success": False, "error": "Unknown field type"}, value)
            
            with ThreadPoolExecutor(max_workers=len(parallel_tasks)) as field_executor:
                futures = [field_executor.submit(_run_field, tt, val) for tt, val in parallel_tasks]
                for future in as_completed(futures):
                    try:
                        task_type, result, values = future.result()
                    except Exception as e:
                        log("FAILED", self.token, f"[Field Error : {str(e)[:30]}]")
                        success = False
                        continue
                    
                    if task_type == "account":
                        _, aname, dname = values
                        if result["success"]:
                            pass
                        elif result.get("captcha"):
                            if aname: log("WARN", self.token, "[Avatar Failed : Captcha]")
                            if dname: log("WARN", self.token, "[Name Failed : Captcha]")
                            success = False
                        elif result.get("rate_limited"):
                            ra = result.get("retry_after", 0)
                            ra_str = f"{int(ra)}s" if ra else "unknown"
                            if aname: log("WARN", self.token, f"[Avatar Failed : Rate Limited ({ra_str})]")
                            if dname: log("WARN", self.token, f"[Name Failed : Rate Limited ({ra_str})]")
                            success = False
                        else:
                            error_msg = self._clean_error(result.get("error", "Unknown"))
                            if aname: log("FAILED", self.token, f"[Avatar Failed : {error_msg}]")
                            if dname: log("FAILED", self.token, f"[Name Failed : {error_msg}]")
                            success = False
                    elif task_type == "profile":
                        _, bname, pname = values
                        if result["success"]:
                            pass
                        elif result.get("captcha"):
                            if bname: log("WARN", self.token, "[Bio Failed : Captcha]")
                            if pname: log("WARN", self.token, "[Pronouns Failed : Captcha]")
                            success = False
                        else:
                            error_msg = self._clean_error(result.get("error", "Unknown"))
                            if bname: log("FAILED", self.token, f"[Bio Failed : {error_msg}]")
                            if pname: log("FAILED", self.token, f"[Pronouns Failed : {error_msg}]")
                            success = False
                    elif task_type == "hypesquad":
                        _, hsname = values
                        if result.get("success"):
                            applied_house = result.get("house_name", hsname)
                        else:
                            error_msg = self._clean_error(result.get("error", "Unknown"))
                            log("FAILED", self.token, f"[HypeSquad Failed : {hsname} - {error_msg}]")
                            success = False
        
        if self.proxy_failed and proxy_manager:
            proxy_manager.mark_bad(self.proxy)
        
        return success


def load_avatar_files() -> List[Path]:
    """Get list of avatar files"""
    if not AVATARS_DIR.exists():
        return []
    return list(AVATARS_DIR.glob("*.jpg")) + list(AVATARS_DIR.glob("*.png"))


def load_avatar_as_base64(avatar_path: Path) -> Optional[str]:
    """Encode avatar image as base64"""
    try:
        img = Image.open(avatar_path)
        img.thumbnail((AVATAR_DIMENSION, AVATAR_DIMENSION), Image.Resampling.LANCZOS)
        with open(avatar_path, "rb") as f:
            img_data = f.read()
        return f"data:image/jpeg;base64,{base64.b64encode(img_data).decode()}"
    except Exception as e:
        Log.error(f"Failed to load avatar {avatar_path}: {e}")
        return None


def load_tokens_from_file() -> List[str]:
    """Load tokens from input/tokens.txt"""
    if not TOKENS_FILE.exists():
        Log.error(f"{TOKENS_FILE} not found")
        return []
    
    try:
        with open(TOKENS_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        tokens = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Support "email:password:token" format
            parts = line.split(":")
            if len(parts) >= 3:
                tokens.append(":".join(parts[2:]))
            else:
                tokens.append(line)
        
        return list(dict.fromkeys(tokens))  # Remove duplicates
    except Exception as e:
        Log.error(f"Failed to load tokens: {e}")
        return []


def load_proxies() -> List[str]:
    """Load proxies"""
    if not PROXIES_FILE.exists():
        return []
    
    try:
        with open(PROXIES_FILE, "r", encoding="utf-8") as f:
            proxies = [line.strip() for line in f.readlines() if line.strip()]
        return proxies
    except Exception:
        return []


def humanize_single_token(token: str, proxy: Optional[str] = None) -> bool:
    """Humanize a single token using embedded Humanizer class"""
    try:
        # Load data lists
        name_list = load_file_lines(NAMES_FILE)
        bio_list = load_file_lines(BIOS_FILE)
        pronouns_list = load_file_lines(PRONOUNS_FILE)
        av_files = load_avatar_files()
        
        # Create Humanizer instance and process
        hz = Humanizer(token, proxy)
        success = hz.process(name_list, bio_list, pronouns_list, av_files, load_avatar_as_base64)
        
        return success
    except Exception as e:
        error_msg = str(e)[:200]
        Log.error(f"Humanizer error: {error_msg}")
        # Silently ignore traceback in GUI mode
        if not SIMPLE_OUTPUT:
            try:
                import traceback
                traceback.print_exc()
            except Exception:
                pass
        return False


def humanize_tokens_batch(tokens: List[str], use_proxies: bool = False, num_threads: int = 3) -> dict:
    """Humanize tokens in batch"""
    proxies = load_proxies() if use_proxies else []
    results = {
        "success": 0,
        "failed": 0,
        "tokens": []
    }
    
    def _humanize_worker(token: str, idx: int, total: int) -> tuple:
        proxy = None
        if proxies:
            proxy = parse_proxy(random.choice(proxies))
        
        try:
            success = humanize_single_token(token, proxy)
            if success:
                results["success"] += 1
                Log.status(f"[{idx}/{total}] Humanized: {token[:20]}...")
                return (token, True, None)
            else:
                results["failed"] += 1
                Log.warn(f"[{idx}/{total}] Failed: {token[:20]}...")
                return (token, False, "Unknown error")
        except Exception as e:
            results["failed"] += 1
            error_msg = str(e)[:80]
            Log.error(f"[{idx}/{total}] Error: {error_msg}")
            return (token, False, str(e))
    
    Log.info(f"Humanizing {len(tokens)} token(s) with {num_threads} thread(s)")
    if proxies:
        Log.info(f"Using {len(proxies)} proxy/proxies")
    else:
        Log.info(f"Running proxyless")
    
    with ThreadPoolExecutor(max_workers=min(num_threads, len(tokens))) as executor:
        futures = [
            executor.submit(_humanize_worker, token, i+1, len(tokens))
            for i, token in enumerate(tokens)
        ]
        
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                Log.error(f"Worker exception: {str(e)[:100]}")
    
    Log.info(f"Complete: {results['success']} success | {results['failed']} failed")
    return results


def print_banner():
    """Display banner"""
    try:
        print("\n=== Humanizer Standalone ===")
        print("Apply profile customization to any token\n")
    except Exception:
        pass


def interactive_mode():
    """Interactive mode"""
    print_banner()
    
    tokens = load_tokens_from_file()
    if not tokens:
        Log.error("No tokens found in input/tokens.txt")
        return
    
    Log.status(f"Loaded {len(tokens)} token(s) from input/tokens.txt")
    
    while True:
        try:
            print("\n=== Options ===")
            print("[1] Humanize all tokens")
            print("[2] Humanize specific token")
            print("[3] View config")
            print("[4] Exit")
            print()
            
            choice = input("Select option: ").strip()
            
            if choice == "1":
                use_proxies = "y" in input("Use proxies? (y/n): ").lower()
                try:
                    threads = int(input(f"Number of threads ({MAX_THREADS}): ") or MAX_THREADS)
                except ValueError:
                    threads = MAX_THREADS
                
                humanize_tokens_batch(tokens, use_proxies, threads)
            
            elif choice == "2":
                for i, token in enumerate(tokens, 1):
                    print(f"[{i}] {token[:20]}...")
                
                try:
                    idx = int(input("Select token number: ")) - 1
                    if 0 <= idx < len(tokens):
                        use_proxies = "y" in input("Use proxy? (y/n): ").lower()
                        proxy = None
                        if use_proxies:
                            proxies = load_proxies()
                            if proxies:
                                proxy = parse_proxy(random.choice(proxies))
                        
                        Log.info(f"Humanizing token: {tokens[idx][:20]}...")
                        success = humanize_single_token(tokens[idx], proxy)
                        if success:
                            Log.status("Humanization successful")
                        else:
                            Log.error("Humanization failed")
                except (ValueError, IndexError):
                    Log.error("Invalid selection")
            
            elif choice == "3":
                print("\n=== Current Config ===")
                print(f"Update Display Name: {UPDATE_DISPLAY_NAME}")
                print(f"Update Bio: {UPDATE_BIO}")
                print(f"Update Pronouns: {UPDATE_PRONOUNS}")
                print(f"Update Avatar: {UPDATE_AVATAR}")
                print(f"Update HypeSquad: {UPDATE_HYPESQUAD}")
                print(f"Max Threads: {MAX_THREADS}")
                print(f"Retry Limit: {RETRY_LIMIT}\n")
            
            elif choice == "4":
                print("Goodbye\n")
                break
            
            else:
                Log.error("Invalid option")
        except Exception as e:
            # Silently ignore errors in interactive mode
            Log.error(f"Error: {str(e)[:50]}")


def main():
    """Main process"""
    # Output debug information
    if os.environ.get("DEBUG_HUMANIZER") == "1":
        try:
            print(f"[DEBUG] SCRIPT_DIR: {SCRIPT_DIR}")
            print(f"[DEBUG] DATA_DIR: {DATA_DIR}")
            print(f"[DEBUG] INPUT_DIR: {INPUT_DIR}")
            print(f"[DEBUG] AVATARS_DIR: {AVATARS_DIR}")
            print(f"[DEBUG] UPDATE_DISPLAY_NAME: {UPDATE_DISPLAY_NAME}")
            print(f"[DEBUG] UPDATE_BIO: {UPDATE_BIO}")
            print(f"[DEBUG] UPDATE_PRONOUNS: {UPDATE_PRONOUNS}")
            print(f"[DEBUG] UPDATE_AVATAR: {UPDATE_AVATAR}")
        except Exception:
            pass
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--help":
            try:
                print("""
Humanizer Standalone

Usage:
  python humanizer_standalone.py              Interactive mode
  python humanizer_standalone.py all          Humanize all tokens
  python humanizer_standalone.py all_proxy    Humanize all tokens with proxies
  python humanizer_standalone.py <token>      Humanize specific token

""")
            except Exception:
                pass
        elif sys.argv[1] == "all":
            use_proxies = False
            tokens = load_tokens_from_file()
            if tokens:
                Log.info(f"Humanizing {len(tokens)} token(s)")
                humanize_tokens_batch(tokens, use_proxies, MAX_THREADS)
                Log.status("Humanizer completed")
            else:
                Log.error("No tokens found in input/tokens.txt")
        elif sys.argv[1] == "all_proxy":
            use_proxies = True
            tokens = load_tokens_from_file()
            if tokens:
                Log.info(f"Humanizing {len(tokens)} token(s) with proxies")
                humanize_tokens_batch(tokens, use_proxies, MAX_THREADS)
                Log.status("Humanizer completed")
            else:
                Log.error("No tokens found in input/tokens.txt")
        else:
            # Humanize specific token
            token = sys.argv[1]
            use_proxies = "--proxy" in sys.argv
            proxy = None
            if use_proxies:
                proxies = load_proxies()
                if proxies:
                    proxy = parse_proxy(random.choice(proxies))
            
            Log.info(f"Humanizing token: {token[:20]}...")
            success = humanize_single_token(token, proxy)
            if success:
                Log.status("Humanization successful")
            else:
                Log.error("Humanization failed")
    else:
        interactive_mode()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        Log.warn("Interrupted by user")
    except Exception as e:
        Log.error(f"Fatal error: {str(e)[:100]}")
