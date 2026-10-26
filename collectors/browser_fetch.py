#!/usr/bin/env python3
"""Fetch pages with a real Chrome, for feeds that refuse everything else.

Kansas puts its results behind a Cloudflare browser challenge. Every plain request to
ent.sos.ks.gov - with or without full browser headers - comes back as the same 703KB
"Just a moment..." page. Headless Chrome does not help: driven over DevTools with
JavaScript running and a 45-second wait, the challenge still never resolves, because
what it objects to is headless itself. A normal windowed Chrome clears it in about
four seconds and then serves county pages in 0.8s each.

So this is not a bypass of anything. It is the same browser a person would use, asked
to load the page and hand back the DOM once the challenge has cleared.

Two consequences worth stating plainly:

  * It needs a real windowed Chrome, so it runs on the laptop, not the cron VM - the
    same constraint me_results.py already lives with. The window opens off-screen.
  * It drives Chrome through --remote-debugging-port with its own throwaway profile,
    never the user's, so it has no access to anyone's sessions or cookies.

The WebSocket client is written out longhand because the cron host has no pip and the
standard library has no WebSocket client. It speaks only as much of the protocol as
DevTools needs: a masked text frame out, a text frame in.
"""
import base64, json, os, pathlib, re, shutil, socket, struct, subprocess, sys, time
import urllib.request

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome", "/usr/bin/chromium-browser", "/usr/bin/chromium",
]
CHALLENGE = ("Just a moment", "Checking your browser", "cf_chl", "Attention Required")


def chrome_path():
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    found = shutil.which("google-chrome") or shutil.which("chromium")
    if found:
        return found
    raise RuntimeError("no Chrome or Chromium found — this collector needs a real "
                       "browser and cannot run on a host without one")


class _WS:
    """The minimum WebSocket client DevTools needs."""

    def __init__(self, url, timeout=30):
        if not url.startswith("ws://"):
            raise RuntimeError(f"not a ws:// url: {url}")
        hostport, _, path = url[5:].partition("/")
        host, _, port = hostport.partition(":")
        self.sock = socket.create_connection((host, int(port)), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n".encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("DevTools closed the connection during handshake")
            buf += chunk
        if b" 101 " not in buf.split(b"\r\n")[0]:
            raise RuntimeError(f"DevTools refused the upgrade: {buf[:120]!r}")
        self.buf = buf.split(b"\r\n\r\n", 1)[1]

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("DevTools connection closed mid-frame")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, text):
        payload = text.encode()
        mask = os.urandom(4)
        head = bytearray([0x81])
        n = len(payload)
        if n < 126:
            head.append(0x80 | n)
        elif n < 65536:
            head.append(0x80 | 126)
            head += struct.pack(">H", n)
        else:
            head.append(0x80 | 127)
            head += struct.pack(">Q", n)
        head += mask
        head += bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(head))

    def recv(self):
        while True:
            b0, b1 = self._read(2)
            opcode, n = b0 & 0x0F, b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload = self._read(n)
            if opcode == 1:
                return payload.decode("utf-8", "replace")
            if opcode == 8:
                raise RuntimeError("DevTools closed the WebSocket")

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class Browser:
    """A windowed Chrome, driven over DevTools. Use as a context manager."""

    def __init__(self, port=9222, profile=None, quiet=True):
        self.port = port
        self.profile = pathlib.Path(
            profile or (pathlib.Path(os.environ.get("TMPDIR", "/tmp"))
                        / "election-night-chrome"))
        self.proc = None
        self.ws = None
        self.msg_id = 0
        self.quiet = quiet

    # -- lifecycle ---------------------------------------------------------
    def _devtools(self, path="/json", timeout=5):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}{path}", timeout=timeout) as r:
            return json.load(r)

    def _listening(self):
        try:
            self._devtools("/json/version", timeout=2)
            return True
        except Exception:
            return False

    def start(self):
        if not self._listening():
            self.profile.mkdir(parents=True, exist_ok=True)
            # Windowed, because headless is what the challenge rejects; parked far
            # off-screen so it never steals focus or covers anything.
            self.proc = subprocess.Popen(
                [chrome_path(), f"--remote-debugging-port={self.port}",
                 f"--user-data-dir={self.profile}", "--no-first-run",
                 "--no-default-browser-check", "--disable-background-networking",
                 "--window-position=2400,2400", "--window-size=1200,850",
                 "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(60):
                if self._listening():
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError("Chrome did not open a DevTools port in 30s")
        self._attach()
        return self

    def _attach(self):
        # A fresh Chrome may expose no page target at all, so make one.
        target = None
        for _ in range(20):
            pages = [t for t in self._devtools() if t.get("type") == "page"]
            if pages:
                target = pages[0]
                break
            try:
                urllib.request.urlopen(urllib.request.Request(
                    f"http://127.0.0.1:{self.port}/json/new?url=about:blank",
                    method="PUT"), timeout=10).read()
            except Exception:
                pass
            time.sleep(0.5)
        if not target:
            raise RuntimeError("Chrome exposed no page to drive")
        self.ws = _WS(target["webSocketDebuggerUrl"])
        self.cmd("Page.enable")
        self.cmd("Runtime.enable")

    def close(self):
        if self.ws:
            self.ws.close()
            self.ws = None
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()
        return False

    # -- driving -----------------------------------------------------------
    def cmd(self, method, **params):
        self.msg_id += 1
        mid = self.msg_id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        deadline = time.time() + 60
        while time.time() < deadline:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
        raise RuntimeError(f"{method}: no answer from Chrome in 60s")

    def _eval(self, expr):
        r = self.cmd("Runtime.evaluate", expression=expr, returnByValue=True)
        return r.get("result", {}).get("value")

    def fetch(self, url, ready=None, timeout=60, settle=0.7):
        """Load url and return its DOM once it is real content, not a challenge.

        `ready(html)` lets the caller say what "loaded" means for a given page; without
        it, anything that is not the challenge counts. Raises if the page never
        arrives, so a caller can never mistake a challenge page for data.
        """
        self.cmd("Page.navigate", url=url)
        deadline = time.time() + timeout
        last = ""
        while time.time() < deadline:
            time.sleep(settle)
            try:
                html = self._eval("document.documentElement.outerHTML") or ""
            except RuntimeError:
                continue
            last = html
            if any(c in html[:4000] for c in CHALLENGE):
                continue
            if len(html) < 2000:
                continue
            if ready and not ready(html):
                continue
            return html
        why = ("still the browser challenge" if any(c in last[:4000] for c in CHALLENGE)
               else f"never matched what the caller was waiting for ({len(last)} bytes)")
        raise RuntimeError(f"{url}: {why} after {timeout}s")


def main(argv):
    if len(argv) < 2:
        print(f"usage: {pathlib.Path(argv[0]).name} <url> [...]  "
              f"— prints each page's DOM length and title", file=sys.stderr)
        return 64
    with Browser() as b:
        for url in argv[1:]:
            t0 = time.time()
            html = b.fetch(url)
            title = re.search(r"<title>(.*?)</title>", html, re.S)
            print(f"{time.time()-t0:5.1f}s  {len(html):8,}B  "
                  f"{(title.group(1).strip() if title else '?')[:60]}  {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
