#!/usr/bin/env python3
"""Tiny stats agent for the RTX 5090 render worker (192.168.50.91).

Serves JSON at http://0.0.0.0:8767/stats for the Jarvis HUD machines panel.

Setup on the worker (once):
    pip install psutil
    python worker_stats.py
(Optionally register as a scheduled task / startup item.)

Requires nvidia-smi on PATH for GPU stats (ships with NVIDIA drivers).
"""
import json
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    import psutil
except ImportError:
    psutil = None

PORT = 8767


def gpu_stats() -> dict:
    try:
        out = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            timeout=4, text=True,
        ).strip().splitlines()[0]
        util, used, total, temp = [x.strip() for x in out.split(",")]
        return {
            "gpu_util": float(util),
            "vram_used": round(float(used) / 1024, 1),
            "vram_total": round(float(total) / 1024, 1),
            "gpu_temp": int(float(temp)),
        }
    except Exception:
        return {}


def stats() -> dict:
    s = {"name": os.environ.get("JARVIS_WORKER_NAME", "GPU WORKER"), "online": True}
    if psutil:
        s["cpu"] = psutil.cpu_percent(interval=0.2)
        s["mem"] = psutil.virtual_memory().percent
    s.update(gpu_stats())
    return s


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/stats":
            self.send_response(404); self.end_headers(); return
        body = json.dumps(stats()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # quiet
        pass


if __name__ == "__main__":
    print(f"Jarvis worker stats agent on http://0.0.0.0:{PORT}/stats")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
