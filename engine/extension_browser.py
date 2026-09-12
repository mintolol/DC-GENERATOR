

import asyncio
import base64
import json
import os
import re
import threading
import time
import random
from pathlib import Path
BROWSER_WIDTH  = 350
BROWSER_HEIGHT = 500
MAX_CONCURRENT = 3
TASK_TIMEOUT   = 90       
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
EXTENSION_DIR = os.path.join(PROJECT_ROOT, "extension")
EXT_CONFIG_FILE = os.path.join(EXTENSION_DIR, "config.json")
CONFIG_FILE = os.path.join(PROJECT_ROOT, "config.json")
HTML_TEMPLATE = """<!DOCTYPE html>
<html><head>
<script src="https://js.hcaptcha.com/1/api.js?onload=hcaptchaOnLoad" async defer></script>
</head><body>
<div class="h-captcha" data-sitekey="SITE_KEY"></div>
</body></html>"""
def _load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}
def sync_api_key():
    # Remove MINTOtcha dependency completely
    # Extension browser works standalone, no API key needed
    return True
def _is_token_like(value):
    if not isinstance(value, str):
        return False
    token = value.strip()
    if len(token) < 25:
        return False
    return bool(re.search(r"[A-Za-z0-9_.-]{25,}", token))
def _encode_base64(text):
    return base64.b64encode(text.encode("utf-8")).decode("utf-8")
class ExtensionBrowser:
    
    def __init__(self):
        self.browser = None
        self.browser_lock = asyncio.Lock()
        self.semaphore = None
        self._initialized = False
        self._loop = None
        self._loop_thread = None
        self._solve_count = 0
        self._clear_every = 5
        self._last_proxy = None
        self._proxy_user = None
        self._proxy_pass = None
    def _ensure_loop(self):
        
        if self._loop and self._loop.is_running():
            return
        def run():
            self._loop = asyncio.new_event_loop()
            self._loop.set_exception_handler(lambda loop, ctx: None)
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()
        self._loop_thread = threading.Thread(target=run, daemon=True)
        self._loop_thread.start()
        for _ in range(50):
            if self._loop and self._loop.is_running():
                break
            time.sleep(0.1)
    async def _stop_browser(self):
        if self.browser:
            try:
                await asyncio.wait_for(self.browser.stop(), timeout=3)
            except Exception:
                pass
            self.browser = None
            self._initialized = False
    async def _init_async(self, proxy=None, user_agent=""):
        
        needs_restart = False
        if proxy != self._last_proxy and self._initialized:
            needs_restart = True
        if needs_restart:
            await self._stop_browser()
        if self._initialized and self.browser:
            return
        import truedriver as td
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        extension_dir = os.path.abspath(EXTENSION_DIR)
        import hashlib
        import tempfile
        import shutil
        
        # Hash proxy to create a dedicated, persistent but isolated profile per IP.
        # This allows hCaptcha to build a trust session per-proxy without corrupting the Chrome extension worker!
        safe_proxy_id = hashlib.md5((proxy or "default").encode()).hexdigest()[:12]
        persist_profile = os.path.join(tempfile.gettempdir(), f"cap9_node_{safe_proxy_id}")
        
        browser_args = [
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--lang=en-US",
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--disable-ipc-flooding-protection",
            "--disable-hang-monitor",
            "--remote-debugging-port=0",
            "--enable-unsafe-extension-debugging",
            "--no-sandbox",
            "--disable-features=CalculateNativeWinOcclusion",
            f"--window-size={BROWSER_WIDTH},{BROWSER_HEIGHT}",
            f"--user-data-dir={persist_profile}"
        ]
        # Override with a safe, un-abused UA to prevent hCaptcha ratelimits
        if user_agent:
            browser_args.append(f"--user-agent={user_agent}")
        else:
            safe_uas = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
            ]
            browser_args.append(f"--user-agent={random.choice(safe_uas)}")
        ext_exists = os.path.exists(extension_dir) and Path(extension_dir).joinpath("manifest.json").exists()
        if ext_exists:
            browser_args.append(f"--disable-extensions-except={extension_dir}")
            browser_args.append(f"--load-extension={extension_dir}")
            browser_args.append(
                "--disable-features=DisableDisableExtensionsExceptCommandLineSwitch,DisableLoadExtensionCommandLineSwitch"
            )
        
        self._proxy_user = None
        self._proxy_pass = None
        td_kwargs = {"browser_args": browser_args, "sandbox": False, "headless": False}
        if proxy:
            user_pwd = None
            server_str = proxy
            if "@" in proxy:
                # user:pass@host:port
                user_pwd, server_str = proxy.split("@", 1)
            elif proxy.count(":") == 3:
                # ip:port:user:pass format
                parts = proxy.split(":")
                server_str = f"{parts[0]}:{parts[1]}"
                user_pwd = f"{parts[2]}:{parts[3]}"
            server_url = f"http://{server_str}" if "://" not in server_str else server_str
            if user_pwd and ":" in user_pwd:
                user, pwd = user_pwd.split(":", 1)
                self._proxy_user = user
                self._proxy_pass = pwd
                td_kwargs["proxy"] = {"server": server_url, "username": user, "password": pwd}
            else:
                td_kwargs["proxy"] = server_url
        self._last_proxy = proxy

        self.browser = await asyncio.wait_for(
            td.start(**td_kwargs),
            timeout=45,
        )
        self._initialized = True

    async def _solve_async(self, sitekey, url, rqdata="", user_agent="", timeout=TASK_TIMEOUT, proxy=None):
        
        import truedriver as td
        from truedriver.cdp.fetch import HeaderEntry, RequestPattern, RequestStage
        from truedriver.cdp.network import ResourceType
        proxy_changed = proxy != self._last_proxy
        if not self._initialized or proxy_changed:
            await self._init_async(proxy=proxy, user_agent=user_agent)
        await self.semaphore.acquire()
        try:
            # MINTOtcha依存を削除 - 難読化されたコードを削除
            pass
        except Exception:
            pass
        page = None
        target_base_url = url.split("?", 1)[0]
        template_body = HTML_TEMPLATE.replace("SITE_KEY", sitekey)
        hcap_path = os.path.join(BASE_DIR, "hcaptcha.html")
        hcap_html = ""
        try:
            hcap_html = Path(hcap_path).read_text(encoding="utf-8")
        except Exception:
            hcap_html = "<html><body>hcaptcha template</body></html>"
        if rqdata:
            hcap_html = hcap_html.replace('Dr = t', f'Dr = "{rqdata}"')
            hcap_html = hcap_html.replace('Zr = t', f'Zr = "{rqdata}"')
        try:
            page = await self.browser.get("about:blank")
            async def request_handler(event):
                request_url = event.request.url
                handled = False
                try:
                    if request_url == url or request_url.startswith(target_base_url):
                        await page.send(td.cdp.fetch.fulfill_request(
                            request_id=event.request_id, response_code=200,
                            response_headers=[HeaderEntry("Content-Type", "text/html; charset=utf-8")],
                            body=_encode_base64(template_body),
                        ))
                        handled = True
                    elif "/static/hcaptcha.html" in request_url:
                        await page.send(td.cdp.fetch.fulfill_request(
                            request_id=event.request_id, response_code=200,
                            response_headers=[HeaderEntry("Content-Type", "text/html; charset=utf-8")],
                            body=_encode_base64(hcap_html),
                        ))
                        handled = True
                    if not handled:
                        await page.send(td.cdp.fetch.continue_request(request_id=event.request_id))
                except Exception:
                    pass
            handler_patterns = [
                RequestPattern(url_pattern=f"{target_base_url}*", request_stage=RequestStage.REQUEST, resource_type=ResourceType.DOCUMENT),
                RequestPattern(url_pattern="*static/hcaptcha.html*", request_stage=RequestStage.REQUEST, resource_type=ResourceType.DOCUMENT),
                RequestPattern(url_pattern="*api.js*", request_stage=RequestStage.REQUEST, resource_type=None),
            ]
            await page.send(td.cdp.fetch.enable(patterns=handler_patterns))
            page.add_handler(td.cdp.fetch.RequestPaused, request_handler)
            await page.get(url, timeout=10)
            try:
                noise_seed = random.randint(1, 100)
                spoof_js = """
                    Object.defineProperty(document, 'hidden', { get: () => false });
                    Object.defineProperty(document, 'visibilityState', { get: () => 'visible' });
                    document.dispatchEvent(new Event('visibilitychange'));
                (function() {
                    const seed = %d;
                    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
                    HTMLCanvasElement.prototype.toDataURL = function(type) {
                        const ctx = this.getContext('2d');
                        if (ctx) {
                            const imgData = ctx.getImageData(0, 0, this.width, this.height);
                            for (let i = 0; i < imgData.data.length; i += 4) {
                                imgData.data[i] = imgData.data[i] ^ ((seed + i) %% 3);
                            }
                            ctx.putImageData(imgData, 0, 0);
                        }
                        return origToDataURL.apply(this, arguments);
                    };
                    const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
                    CanvasRenderingContext2D.prototype.getImageData = function() {
                        const imgData = origGetImageData.apply(this, arguments);
                        for (let i = 0; i < imgData.data.length; i += 4) {
                            imgData.data[i] = imgData.data[i] ^ ((seed + i) %% 3);
                        }
                        return imgData;
                    };
                })();
                """ % (noise_seed,)
                await asyncio.wait_for(page.evaluate(spoof_js), timeout=3)
            except Exception:
                pass
            start = time.time()
            while time.time() - start < timeout:
                try:
                    token = await asyncio.wait_for(page.evaluate("hcaptcha.getResponse()"), timeout=2)
                    if token and _is_token_like(token):
                        elapsed = time.time() - start
                        # MINTOtcha依存を削除 - 難読化されたコードを削除
                        return token
                except Exception:
                    pass
                await asyncio.sleep(1)
            return None
        except Exception as e:
            print(f"  [EXT] ✗ Error: {e}")
            return None
        finally:
            self._solve_count += 1
            if page:
                try:
                    page.remove_handlers(td.cdp.fetch.RequestPaused, request_handler)
                    await page.send(td.cdp.fetch.disable())
                except Exception:
                    pass
                
            await self._stop_browser()
            self.semaphore.release()
    def solve(self, sitekey, url, rqdata="", user_agent="", timeout=TASK_TIMEOUT, proxy=None):
        
        self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._solve_async(sitekey, url, rqdata, user_agent, timeout, proxy=proxy),
            self._loop,
        )
        try:
            return future.result(timeout=timeout + 10)
        except Exception:
            return None
    def is_ready(self):
        return self._initialized and self.browser is not None

    def stop(self):
        if self.browser:
            try:
                future = asyncio.run_coroutine_threadsafe(self.browser.stop(), self._loop)
                future.result(timeout=5)
            except Exception:
                pass

_browsers = {}
def get_browser():
    import threading
    tid = threading.get_ident()
    if tid not in _browsers:
        _browsers[tid] = ExtensionBrowser()
    return _browsers[tid]
