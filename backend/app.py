"""FastAPI backend (Hugging Face Space, Docker). Same routes as devserver.py.

  GET  /api/health            -> {"status": "loading" | "ok" | "error"}
  GET  /api/info              -> KB size, models, tuned thresholds, benchmark tables from the Kaggle run
  POST /api/ask               -> {"question": "..."}                     text question
  POST /api/ask_image         -> multipart: image=<file>, question=<text>   photo (+ optional question)
  GET  /api/parity            -> re-checks the notebook's decisions on the exported parity questions
  GET  /bundle/...            -> gallery thumbnails;  GET / -> the web app (frontend/)
"""
import os, threading, traceback

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))


def resolve_bundle():
    """1) SHRAG_BUNDLE_REPO: a Hugging Face dataset repo written by section 17 of the notebook (downloaded at start-up);
    2) SHRAG_BUNDLE or ./bundle: a local folder; 3) ./demo_bundle: the small synthetic test bundle shipped with the repo."""
    repo = os.environ.get("SHRAG_BUNDLE_REPO")
    if repo:
        from huggingface_hub import snapshot_download
        return snapshot_download(repo_id=repo, repo_type="dataset", token=os.environ.get("HF_TOKEN") or None,
                                 local_dir=os.path.join(os.environ.get("SHRAG_WORK", "/tmp/shrag"), "bundle"))
    for p in (os.environ.get("SHRAG_BUNDLE"), os.path.join(ROOT, "bundle"), os.path.join(ROOT, "demo_bundle")):
        if p and os.path.exists(os.path.join(p, "state.pkl")): return p
    raise FileNotFoundError("no deploy bundle: set SHRAG_BUNDLE_REPO (HF dataset) or put the notebook's deploy_bundle/ in ./bundle")


def ensure_versions(bundle):
    """Pickled scikit-learn heads load reliably only with the scikit-learn version that wrote them (recorded by the notebook).
    Runs before any ML import, so a pip install here takes effect in this process."""
    import importlib.metadata as md, json, subprocess, sys
    p = os.path.join(bundle, "versions.json")
    if not os.path.exists(p): return
    want = json.load(open(p)).get("scikit-learn")
    try: have = md.version("scikit-learn")
    except md.PackageNotFoundError: have = None
    if want and have != want:
        print(f"installing scikit-learn=={want} to match the bundle (installed: {have})", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--quiet", f"scikit-learn=={want}"], check=False)
        import site; sys.path.insert(0, site.getusersitepackages())


BUNDLE = None
FRONTEND = os.environ.get("SHRAG_FRONTEND", os.path.join(ROOT, "frontend"))
MAX_UPLOAD = 8 * 2**20

app = FastAPI(title="Self-healing RAG for Bangladeshi food", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("SHRAG_CORS", "*").split(","), allow_methods=["*"], allow_headers=["*"])
STATE = {"svc": None, "status": "loading", "error": None}


def _load():
    global BUNDLE
    try:
        BUNDLE = resolve_bundle(); ensure_versions(BUNDLE)
        from service import Service
        STATE["svc"] = Service(BUNDLE); STATE["status"] = "ok"
    except Exception as e:                                    # keep the server up and report why
        STATE["status"], STATE["error"] = "error", f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}"

threading.Thread(target=_load, daemon=True).start()          # models load in the background; /api/health reports progress


def svc():
    if STATE["status"] != "ok": raise HTTPException(503, detail={"status": STATE["status"], "error": STATE["error"]})
    return STATE["svc"]


class Ask(BaseModel):
    question: str


@app.get("/api/health")
def health(): return {"status": STATE["status"], "error": STATE["error"]}

@app.get("/api/info")
def info(): return svc().info()

@app.post("/api/ask")
def ask(body: Ask): return svc().ask(body.question)

@app.post("/api/ask_image")
async def ask_image(image: UploadFile = File(...), question: str = Form("")):
    data = await image.read()
    if len(data) > MAX_UPLOAD: raise HTTPException(413, "image larger than 8 MB")
    try: return svc().ask_image(data, question)
    except HTTPException: raise
    except Exception as e: return JSONResponse({"error": f"could not read the image: {type(e).__name__}"}, status_code=400)

@app.get("/api/parity")
def parity(limit: int = 80): return svc().parity(limit)

@app.get("/bundle/{path:path}")
def bundle_file(path: str):
    if BUNDLE is None: raise HTTPException(503, "loading")
    p = os.path.realpath(os.path.join(BUNDLE, path))
    if not p.startswith(os.path.realpath(BUNDLE)) or not os.path.isfile(p): raise HTTPException(404)
    return FileResponse(p, headers={"Cache-Control": "public, max-age=86400"})
if os.path.isdir(FRONTEND):
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

    @app.get("/")
    def index(): return FileResponse(os.path.join(FRONTEND, "index.html"))

    @app.get("/{name}")
    def frontend_file(name: str):
        p = os.path.join(FRONTEND, os.path.basename(name))
        if os.path.isfile(p): return FileResponse(p)
        raise HTTPException(404)
