#!/usr/bin/env python3
"""
Servidor da GUI do midi-macros. Stdlib apenas, bind em 127.0.0.1.

Sobe sob demanda: inicia, abre o navegador e se encerra sozinho quando a aba
para de mandar heartbeat (fechou). Edita o mesmo config.json que o daemon lê.
"""
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.expanduser("~/.config/midi-macros")
GUI_DIR = os.path.join(BASE, "gui")
STATIC = os.path.join(GUI_DIR, "static")
CONFIG = os.path.join(BASE, "config.json")
SERVICE = "midi-macros.service"

# Reusa a MESMA execução de ação do daemon (fonte de verdade única).
_spec = importlib.util.spec_from_file_location("midimacros", os.path.join(BASE, "midi-macros.py"))
_mm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mm)
ENV = _mm.build_env()

_last_beat = time.time()
_started = time.time()

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}


def systemctl(*args):
    return subprocess.run(["systemctl", "--user", *args],
                          capture_output=True, text=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # silencioso

    # ---- helpers ----
    def _send(self, code, body=b"", ctype="application/json"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json")

    def _read_json(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def _serve_static(self, path):
        if path in ("/", ""):
            rel = "index.html"
        elif path.startswith("/static/"):
            rel = path[len("/static/"):]
        else:
            rel = path.lstrip("/")
        # impede path traversal
        safe = os.path.normpath(rel)
        full = os.path.join(STATIC, safe)
        if not os.path.abspath(full).startswith(os.path.abspath(STATIC)) or not os.path.isfile(full):
            return self._send(404, "not found", "text/plain")
        ext = os.path.splitext(full)[1]
        with open(full, "rb") as f:
            self._send(200, f.read(), CONTENT_TYPES.get(ext, "application/octet-stream"))

    # ---- GET ----
    def do_GET(self):
        p = self.path.split("?", 1)[0]
        if p == "/api/config":
            try:
                with open(CONFIG) as f:
                    return self._send(200, f.read(), "application/json")
            except Exception as e:
                return self._json(500, {"error": str(e)})
        if p == "/api/service":
            active = systemctl("is-active", SERVICE).stdout.strip()
            enabled = systemctl("is-enabled", SERVICE).stdout.strip()
            return self._json(200, {"active": active, "enabled": enabled})
        return self._serve_static(p)

    # ---- POST/PUT ----
    def do_PUT(self):
        return self.do_POST()

    def do_POST(self):
        global _last_beat
        p = self.path.split("?", 1)[0]
        try:
            if p == "/api/config":
                data = self._read_json()
                if "pads" not in data:
                    return self._json(400, {"error": "config sem 'pads'"})
                tmp = CONFIG + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                os.replace(tmp, CONFIG)
                return self._json(200, {"ok": True})

            if p == "/api/test":
                body = self._read_json()
                action = body.get("action")
                if not action:  # fallback: pela nota salva em disco
                    with open(CONFIG) as f:
                        cfg = json.load(f)
                    action = cfg.get("pads", {}).get(str(body.get("note", "")))
                if not action or not action.get("type"):
                    return self._json(404, {"error": "pad sem ação"})
                erro = _mm.run_action(action, ENV)
                if erro:
                    return self._json(400, {"error": erro})
                return self._json(200, {"ok": True, "ran": action.get("label", "")})

            if p == "/api/service":
                action = self._read_json().get("action")
                if action not in ("start", "stop", "restart"):
                    return self._json(400, {"error": "ação inválida"})
                r = systemctl(action, SERVICE)
                return self._json(200 if r.returncode == 0 else 500,
                                  {"ok": r.returncode == 0, "err": r.stderr.strip()})

            if p == "/api/heartbeat":
                _last_beat = time.time()
                return self._json(200, {"ok": True})

            if p == "/api/quit":
                threading.Thread(target=lambda: (time.sleep(0.3), os._exit(0)), daemon=True).start()
                return self._json(200, {"ok": True})

            return self._send(404, "not found", "text/plain")
        except Exception as e:
            return self._json(500, {"error": str(e)})


def _watchdog():
    # Encerra o servidor quando a aba fecha (heartbeat parou). Dá 25s de tolerância
    # inicial para o navegador abrir e começar a bater.
    while True:
        time.sleep(5)
        idle = time.time() - _last_beat
        grace = time.time() - _started
        if grace > 25 and idle > 18:
            os._exit(0)


def main():
    port = 8765
    httpd = None
    for _ in range(20):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            port += 1
    if httpd is None:
        print("não foi possível abrir uma porta", file=sys.stderr)
        sys.exit(1)

    url = f"http://127.0.0.1:{port}"
    print(f"[midi-macros-gui] {url}", flush=True)
    threading.Thread(target=_watchdog, daemon=True).start()
    threading.Thread(target=lambda: (time.sleep(0.6), webbrowser.open(url)), daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
