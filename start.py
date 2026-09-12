import os
import sys
import json
import re
import subprocess
import time
import threading
from collections import deque

from flask import Flask, render_template
import webview

# ──── Environment ────
if os.name == "nt":
    os.system("")  # Enable ANSI on Windows
    try:
        import ctypes
        myappid = 'minex.MINTO.tokengen.v4'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# Precompiled ANSI escape stripper for terminal output
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

# ──── Flask (minimal, just serves the template) ────
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'gui_templates'),
    static_folder=os.path.join(BASE_DIR, 'gui_static')
)

@app.route('/')
def index():
    return render_template('index.html')


class WindowController:

    __slots__ = ('_log_buf', '_log_lock', 'current_process', '_reader', '_status_lock', 'status', '_config_mtime')

    def __init__(self):
        self._log_buf = deque(maxlen=5000)  # Ring buffer – never grows unbounded
        self._log_lock = threading.Lock()
        self._status_lock = threading.Lock()
        self.status = {
            "progress": 0,
            "success": 0,
            "failed": 0,
            "pending": 0,
            "total": 0
        }
        self.current_process = None
        self._reader = None
        self._config_mtime = 0  # Config file last modification time

    # ──── Config I/O ────
    def load_config(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # Record last modification time
            try:
                self._config_mtime = os.path.getmtime(CONFIG_FILE)
            except Exception:
                pass
            return cfg
        except Exception as e:
            self._push(f"[!] Config load error: {e}\n")
            return {}

    def save_config(self, cfg_dict):
        try:
            # Load existing config
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    existing_cfg = json.load(f)
            except Exception:
                existing_cfg = {}
            
            # Deep merge new config (preserve nested keys)
            merged_cfg = self._deep_merge(existing_cfg, cfg_dict)
            
            # Write config file
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(merged_cfg, f, indent=4, ensure_ascii=False)
            
            # Verify file saved correctly
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                verify_cfg = json.load(f)
            
            # Verification successful
            if verify_cfg == merged_cfg:
                self._push("[✓] Config saved and verified.\n")
                return True
            else:
                self._push("[!] Config save verification failed.\n")
                return False
        except Exception as e:
            self._push(f"[!] Config save error: {e}\n")
            return False
    
    def _deep_merge(self, base_dict, update_dict):
        """Deep merge nested dictionaries"""
        result = base_dict.copy()
        for key, value in update_dict.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def _check_config_changed(self):
        """Check if config file changed (mtime-based)"""
        try:
            current_mtime = os.path.getmtime(CONFIG_FILE)
            if current_mtime != self._config_mtime:
                self._config_mtime = current_mtime
                return True
        except Exception:
            pass
        return False

    def save_theme(self, hex_color: str):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        cfg["theme_accent"] = hex_color
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)
            return True
        except Exception:
            return False

    # ──── Input/Output Files I/O ────
    def get_input_files(self):
        try:
            files = []
            for d in ["input", "output"]:
                target_dir = os.path.join(BASE_DIR, d)
                if os.path.isdir(target_dir):
                    items = os.listdir(target_dir)
                    for f in items:
                        if f.endswith('.txt'):
                            full_path = os.path.join(target_dir, f)
                            # Add only files (exclude directories)
                            if os.path.isfile(full_path):
                                files.append(f"{d}/{f}")
            return files
        except Exception as e:
            self._push(f"[ERROR] get_input_files: {e}\n")
            return []

    def read_input_file(self, filename: str):
        try:
            # Reconstruct absolute path
            path = os.path.abspath(os.path.join(BASE_DIR, filename))
            expected_in = os.path.abspath(os.path.join(BASE_DIR, "input"))
            expected_out = os.path.abspath(os.path.join(BASE_DIR, "output"))
            
            if not (path.startswith(expected_in) or path.startswith(expected_out)):
                return ""
                
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            return ""
        except Exception:
            return ""

    def save_input_file(self, filename: str, content: str):
        try:
            path = os.path.abspath(os.path.join(BASE_DIR, filename))
            expected_in = os.path.abspath(os.path.join(BASE_DIR, "input"))
            expected_out = os.path.abspath(os.path.join(BASE_DIR, "output"))
            
            if not (path.startswith(expected_in) or path.startswith(expected_out)):
                return False
                
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self._push(f"[✓] Saved data to {filename}\n")
            return True
        except Exception as e:
            self._push(f"[!] Error saving {filename}: {e}\n")
            return False

    # ──── Logging ────
    def _push(self, msg: str):
        with self._log_lock:
            self._log_buf.append(msg)

    def get_logs(self):
        with self._log_lock:
            if not self._log_buf:
                return None
            out = "".join(self._log_buf)
            self._log_buf.clear()
            return out

    # ──── Window Controls ────
    def close(self):
        self.stop_process()
        for w in webview.windows:
            w.destroy()

    def minimize(self):
        for w in webview.windows:
            w.minimize()

    def get_current_ip(self):
        """Get current IP address (for ignore list)"""
        try:
            import requests
            ip = requests.get("https://api.ipify.org", timeout=3).text.strip()
            return ip
        except Exception as e:
            return None

    # ──── Process Management ────
    _TARGETS = {
        "generator":     (lambda bd: ([sys.executable, "main.py"], bd)),
        "checker":       (lambda bd: ([sys.executable, "engine/checker.py"], bd)),
        "proxy_checker": (lambda bd: ([sys.executable, "engine/proxy_checker.py"], bd)),
        "humanizer":     (lambda bd: ([sys.executable, "engine/humanizer_standalone.py", "all"], bd)),
    }

    def start_process(self, target: str, data: str = None):
        if self.current_process and self.current_process.poll() is None:
            self._push("[!] A process is already running. Stop it first.\n")
            return

        with self._status_lock:
            self.status = {"progress": 0, "success": 0, "failed": 0, "pending": 0, "total": 0, "engine": target}

        resolver = self._TARGETS.get(target)
        if not resolver:
            self._push(f"[!] Unknown target: {target}\n")
            return

        cmd, cwd = resolver(BASE_DIR)
        
        try:
            kwargs = {}
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["GUI_MODE"] = "1"
            
            if target == "generator" and data:
                # Pass generator target count as environment variable
                env["GEN_TARGET"] = data
            elif target == "humanizer" and data:
                # Handle humanizer options: all, all_proxy
                if data == "all_proxy":
                    cmd.extend(["all", "--proxy"])
                elif data == "all":
                    cmd.append("all")
            
            if os.name == "nt":
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                kwargs["startupinfo"] = si

            self.current_process = subprocess.Popen(
                cmd, cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                bufsize=1,
                text=True,
                encoding='utf-8',
                errors='ignore',
                env=env,
                **kwargs
            )

            self._reader = threading.Thread(target=self._drain, daemon=True)
            self._reader.start()
        except Exception as e:
            self._push(f"[!] Launch failed ({target}): {e}\n")

    def _parse_status(self, text: str):
        with self._status_lock:
            if text.startswith("GUI_STAT:"):
                try:
                    parts = text.split("GUI_STAT:")[1].strip().split(",")
                    if len(parts) >= 7:
                        gen, ver, cap_solved, cap_fail, locked, valid, total = map(int, parts[:7])
                        self.status["success"] = gen
                        self.status["failed"] = valid + locked
                        self.status["total"] = total
                        self.status["ver"] = ver
                        self.status["cap_solved"] = cap_solved
                        self.status["cap_fail"] = cap_fail
                        if total > 0:
                            self.status["progress"] = int(((gen + valid + locked) / total) * 100)
                except Exception:
                    pass
                return

            # Look for progress pattern (e.g. 15% or [==  ] 15%)
            prog_match = re.search(r'(\d+)%', text)
            if prog_match:
                try:
                    self.status["progress"] = int(prog_match.group(1))
                except ValueError:
                    pass

            # Skip summary lines and setup logs
            if not ("Joined       :" in text or "Failed       :" in text or "Invalid      :" in text or "Captchas     :" in text or "Output saved to" in text or "X-Context-Properties loaded" in text):
                # Count success markers
                if "✓" in text or "OK" in text or "Success" in text or "working" in text.lower():
                    self.status["success"] += 1
                # Count failure markers
                elif "BLOCKED" in text:
                    self.status.setdefault("blocked", 0)
                    self.status["blocked"] += 1
                elif "✗" in text or "DEAD" in text or "Failed" in text or "Error" in text:
                    self.status["failed"] += 1
                
            # If total items log exists
            if self.status.get("engine") == "proxy_checker":
                tot_match = re.search(r'Proxies:\s*(\d+)', text, re.IGNORECASE)
            else:
                tot_match = re.search(r'(?:Tokens:|Checking)\s*(\d+)', text, re.IGNORECASE)
                
            if tot_match:
                try:
                    self.status["total"] = int(tot_match.group(1))
                except ValueError:
                    pass

    def _drain(self):
        proc = self.current_process
        if not proc:
            return
        try:
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                
                clean_text = _ANSI_RE.sub('', line)
                if clean_text.startswith("GUI_STAT:"):
                    self._parse_status(clean_text)
                    continue
                    
                raw_text = line.replace('\r', '') 
                self._push(raw_text)
                self._parse_status(clean_text)
        except Exception:
            pass
        finally:
            if proc:
                rc = proc.wait()
                self._push(f"\n[-] Exited with code {rc}.\n")
                self.current_process = None

    def get_status_updates(self):
        with self._status_lock:
            # calculate pending
            if self.status["total"] > 0:
                self.status["pending"] = max(0, self.status["total"] - (self.status["success"] + self.status["failed"]))
            res = self.status.copy()
            res["is_running"] = self.current_process is not None
            res["config_changed"] = self._check_config_changed()
            return res

    def stop_process(self):
        proc = self.current_process
        if proc and proc.poll() is None:
            self._push("[*] Killing process…\n")
            proc.kill()
            self.current_process = None


# ──── Entry Point ────
if __name__ == "__main__":
    controller = WindowController()

    threading.Thread(target=lambda: app.run(
        debug=False, port=5001, use_reloader=False
    ), daemon=True).start()

    time.sleep(0.8)

    webview.create_window(
        title="MINTO V2",
        url="http://127.0.0.1:5001",
        js_api=controller,
        width=1000, height=660,
        frameless=False,
    )

    webview.start(debug=False, gui="edgechromium")
