"""Backdoor / hidden-exfiltration scan.

Static assertions over the *production* source (server/, client/, worker/,
hermes-plugin/) that there is:
  * no dynamic code-execution sink (eval/exec/os.system/shell=True/pickle/…),
  * no client-side JS code-exec sink (eval/new Function/document.write),
  * no outbound network host outside a reviewed allow-list.

These lock the codebase against a future commit quietly introducing a backdoor.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PROD_DIRS = ["server", "client", "worker", "hermes-plugin"]


def _prod_files(*suffixes):
    out = []
    for d in PROD_DIRS:
        for p in (REPO_ROOT / d).rglob("*"):
            if p.is_file() and p.suffix in suffixes and "venv" not in p.parts:
                out.append(p)
    return out


PY_FILES = _prod_files(".py")
HTML_FILES = _prod_files(".html")

DANGEROUS_PY = [
    r"\beval\(",
    r"\bexec\(",
    r"os\.system\(",
    r"shell\s*=\s*True",
    r"pickle\.(loads|load)\(",
    r"marshal\.loads\(",
    r"\b__import__\(",
    r"subprocess\.call\(\s*[\"'][^\"']*\s",   # string-with-space -> shell-style call
]

DANGEROUS_JS = [
    r"\beval\(",
    r"new\s+Function\(",
    r"document\.write\(",
    r"\.innerHTML\s*=\s*[^;]*\beval",
]


@pytest.mark.parametrize("pat", DANGEROUS_PY)
def test_no_dangerous_python_sinks(pat):
    rx = re.compile(pat)
    hits = []
    for f in PY_FILES:
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if rx.search(line):
                hits.append(f"{f.relative_to(REPO_ROOT)}:{i}: {line.strip()}")
    assert not hits, "Dangerous sink introduced:\n" + "\n".join(hits)


@pytest.mark.parametrize("pat", DANGEROUS_JS)
def test_no_dangerous_js_sinks(pat):
    rx = re.compile(pat)
    hits = []
    for f in HTML_FILES:
        for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if rx.search(line):
                hits.append(f"{f.relative_to(REPO_ROOT)}:{i}: {line.strip()}")
    assert not hits, "Dangerous JS sink introduced:\n" + "\n".join(hits)


def test_subprocess_uses_argument_list_not_shell():
    """The only subprocess call (worker gpu stats) must pass an argv list."""
    src = (REPO_ROOT / "worker" / "worker_stats.py").read_text(encoding="utf-8")
    assert "subprocess.check_output(" in src
    assert "shell=True" not in src
    # invoked with a list literal
    assert re.search(r"subprocess\.check_output\(\s*\[", src)


# --------------------------------------------------------------------------- #
# Outbound-host allow-list                                                     #
# --------------------------------------------------------------------------- #
HOST_ALLOW = {
    "127.0.0.1", "0.0.0.0", "localhost",
    "jarvis.local", "jarvis", "this-machine",
    "api.elevenlabs.io",
    "www.youtube.com", "youtu.be", "youtube.com",
    "fonts.googleapis.com", "fonts.gstatic.com",
    "www.w3.org",              # SVG/XML namespace URIs, not fetched
}
URL_RE = re.compile(r"https?://([^/\"'`<>\s)]+)")


def _host_ok(host: str) -> bool:
    host = host.split(":")[0].strip().lower()
    if host in HOST_ALLOW:
        return True
    if host.startswith(("192.168.", "10.", "127.")):
        return True
    # IANA-reserved documentation placeholders (never real destinations)
    if host == "example.com" or host.endswith((".example.com", ".example.org", ".example.net")):
        return True
    # build-time / template placeholders, not literal destinations
    if any(c in host for c in "{}$") or host.isupper() or "your_" in host:
        return True
    return False


def test_no_unexpected_outbound_hosts():
    offenders = []
    for f in _prod_files(".py", ".html", ".sh", ".bat", ".yaml"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        for host in URL_RE.findall(text):
            if not _host_ok(host):
                offenders.append(f"{f.relative_to(REPO_ROOT)}: {host}")
    assert not offenders, "Unreviewed outbound host(s):\n" + "\n".join(sorted(set(offenders)))
