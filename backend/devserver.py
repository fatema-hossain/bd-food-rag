"""Zero-dependency dev server (Python standard library only) with the same routes as app.py.

    python backend/devserver.py --bundle bundle --port 8000      ->  open http://localhost:8000
Useful for trying the app on a laptop / in Colab without FastAPI; production uses app.py (FastAPI + uvicorn).
"""
import argparse, json, mimetypes, os, sys
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from service import Service  # noqa: E402


def make_handler(svc, bundle, frontend):
    class H(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json"):
            data = json.dumps(body, ensure_ascii=False).encode() if ctype == "application/json" else body
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Access-Control-Allow-Headers", "*"); self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self): self._send(204, b"", "text/plain")

        def _file(self, root, rel):
            p = os.path.realpath(os.path.join(root, rel))
            if not p.startswith(os.path.realpath(root)) or not os.path.isfile(p): return self._send(404, {"error": "not found"})
            self._send(200, open(p, "rb").read(), mimetypes.guess_type(p)[0] or "application/octet-stream")

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/api/health": return self._send(200, {"status": "ok", "error": None})
            if path == "/api/info": return self._send(200, svc.info())
            if path == "/api/parity": return self._send(200, svc.parity())
            if path.startswith("/bundle/"): return self._file(bundle, path[len("/bundle/"):])
            return self._file(frontend, "index.html" if path in ("/", "") else path.lstrip("/").replace("static/", "", 1))

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0)); raw = self.rfile.read(n)
            if self.path == "/api/ask":
                try: q = json.loads(raw or b"{}").get("question", "")
                except json.JSONDecodeError: return self._send(400, {"error": "bad json"})
                return self._send(200, svc.ask(q))
            if self.path == "/api/ask_image":
                msg = BytesParser(policy=email_policy).parsebytes(b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + raw)
                img, q = None, ""
                for part in msg.iter_parts():
                    name = part.get_param("name", header="content-disposition")
                    if name == "image": img = part.get_payload(decode=True)
                    elif name == "question": q = part.get_content()
                if not img: return self._send(400, {"error": "no image"})
                try: return self._send(200, svc.ask_image(img, q))
                except Exception as e: return self._send(400, {"error": f"could not read the image: {type(e).__name__}"})
            self._send(404, {"error": "not found"})

        def log_message(self, fmt, *a): sys.stderr.write("[dev] " + fmt % a + "\n")
    return H


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default=os.path.join(HERE, "..", "bundle")); ap.add_argument("--frontend", default=os.path.join(HERE, "..", "frontend"))
    ap.add_argument("--port", type=int, default=8000); ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    svc = Service(a.bundle)
    print(f"loaded bundle in {svc.load_s}s -> http://{a.host}:{a.port}")
    ThreadingHTTPServer((a.host, a.port), make_handler(svc, os.path.abspath(a.bundle), os.path.abspath(a.frontend))).serve_forever()
