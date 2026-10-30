"""Writes notebook/serve_on_kaggle.ipynb: runs the backend in a Kaggle session (GPU) behind a free Cloudflare tunnel.
usage: python tools/make_serve_notebook.py
"""
import json, os

MD, CODE = "markdown", "code"
cells = [
(MD, """# Serve the Bangladeshi-food app from Kaggle (free)

Hugging Face now charges for Docker Spaces, so the answer server runs **here**, on Kaggle's free GPU, and is reached through a free
**Cloudflare quick tunnel** (a public `https://….trycloudflare.com` address, no account needed). The web page on GitHub Pages finds the
current address by itself: this notebook writes it to `server.json` in your Hugging Face bundle dataset.

**Before the first run**
1. *Settings* (right panel): **Accelerator GPU T4** (x1 is enough), **Internet On**.
2. *Add-ons → Secrets*: `HF_TOKEN` = your Hugging Face **write** token (ticked for this notebook).
3. Edit the first code cell (your GitHub repo and bundle dataset).

**To keep it online for hours with the browser closed:** *Save Version → Save & Run All (Commit)*. A committed run lasts up to 12 h
(`SERVE_HOURS`). While it is running, the app is live; when it ends, the page says the server is offline. For a quick test, just run the
cells interactively (the session stays alive while the tab is open).

Please use this for demos and evaluation sessions, not as permanent 24/7 hosting: Kaggle notebooks are meant for ML work.
"""),
(CODE, """APP_REPO     = "https://github.com/<your-github-username>/bd-food-rag"   # your public GitHub repo with this app
BUNDLE_REPO  = "Fatema042/bd-food-rag-bundle"     # HF dataset written by section 17 of the research notebook
LOCAL_BUNDLE = None      # or a folder, e.g. "/kaggle/input/<research-notebook-output>/deploy_bundle" (then BUNDLE_REPO is not needed)
PAGES_URL    = "https://<your-github-username>.github.io/bd-food-rag/"
SERVE_HOURS  = 11.5      # Kaggle stops a session after 12 h
USE_LLM      = True      # on the GPU the 4-bit Qwen generator paraphrases answers (verified, as in the notebook); False = extractive
PUBLISH_URL  = True      # write the tunnel address to <BUNDLE_REPO>/server.json so the web page finds it
"""),
(CODE, """import os, sys, subprocess, time, re, json, glob, urllib.request
try:
    from kaggle_secrets import UserSecretsClient
    os.environ.setdefault("HF_TOKEN", UserSecretsClient().get_secret("HF_TOKEN"))
except Exception as e:
    print("no HF_TOKEN secret (fine for a public bundle, but the page will not auto-discover the address):", type(e).__name__)
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "fastapi", "uvicorn", "python-multipart", "rapidfuzz"], check=False)

APP = "/kaggle/working/app"
if not os.path.exists(f"{APP}/backend/app.py"):
    local = glob.glob("/kaggle/input/**/backend/app.py", recursive=True)          # the repo can also be attached as a dataset
    if local: APP = os.path.dirname(os.path.dirname(local[0]))
    else: subprocess.run(["git", "clone", "--depth", "1", APP_REPO, APP], check=True, env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"})
print("app code:", APP)
"""),
(CODE, """env = {**os.environ, "SHRAG_WORK": "/kaggle/working/shrag_serve", "SHRAG_USE_LLM": "1" if USE_LLM else "0"}
if LOCAL_BUNDLE: env["SHRAG_BUNDLE"] = LOCAL_BUNDLE
elif BUNDLE_REPO: env["SHRAG_BUNDLE_REPO"] = BUNDLE_REPO
log = open("/kaggle/working/server.log", "w")
server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--app-dir", f"{APP}/backend", "--host", "127.0.0.1", "--port", "7860"],
                          env=env, stdout=log, stderr=subprocess.STDOUT)

def health():
    try: return json.load(urllib.request.urlopen("http://127.0.0.1:7860/api/health", timeout=5))
    except Exception as e: return {"status": "starting", "error": type(e).__name__}

t0 = time.time()
while time.time() - t0 < 1800:
    h = health()
    if h.get("status") in ("ok", "error"): break
    time.sleep(10)
print(f"server: {h} after {time.time() - t0:.0f}s")
if h.get("status") != "ok": print(open("/kaggle/working/server.log").read()[-3000:])
else:
    print("parity with the research notebook:", json.load(urllib.request.urlopen("http://127.0.0.1:7860/api/parity?limit=80", timeout=600)))
"""),
(CODE, """CF = "/kaggle/working/cloudflared"
if not os.path.exists(CF):
    urllib.request.urlretrieve("https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64", CF); os.chmod(CF, 0o755)
tlog = open("/kaggle/working/tunnel.log", "w")
tunnel = subprocess.Popen([CF, "tunnel", "--url", "http://127.0.0.1:7860", "--no-autoupdate"], stdout=tlog, stderr=subprocess.STDOUT)
URL = None
for _ in range(60):
    m = re.search(r"https://[a-z0-9-]+\\.trycloudflare\\.com", open("/kaggle/working/tunnel.log").read())
    if m: URL = m.group(0); break
    time.sleep(2)
print("public server address:", URL)
print("open the app:         ", f"{PAGES_URL}?api={URL}")
print("or directly:          ", URL)
if URL and PUBLISH_URL and BUNDLE_REPO and os.environ.get("HF_TOKEN"):
    from huggingface_hub import HfApi
    info = {"url": URL, "started": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "until": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(time.time() + SERVE_HOURS * 3600))}
    open("/kaggle/working/server.json", "w").write(json.dumps(info))
    HfApi(token=os.environ["HF_TOKEN"]).upload_file(path_or_fileobj="/kaggle/working/server.json", path_in_repo="server.json",
                                                    repo_id=BUNDLE_REPO, repo_type="dataset", commit_message="current server address")
    print("published to", f"https://huggingface.co/datasets/{BUNDLE_REPO}/blob/main/server.json", "-> the GitHub Pages link finds it by itself")
"""),
(CODE, """# keep the session (and the app) alive; prints a heartbeat every 10 minutes
end = time.time() + SERVE_HOURS * 3600
while time.time() < end and server.poll() is None and tunnel.poll() is None:
    time.sleep(600)
    print(time.strftime("%H:%M"), health().get("status"), "| hours left", round((end - time.time()) / 3600, 1), flush=True)
print("stopped:", "server exited" if server.poll() is not None else ("tunnel exited" if tunnel.poll() is not None else "time limit"))
"""),
]

nb = {"cells": [{"cell_type": t, "metadata": {}, "source": s.splitlines(True), **({"outputs": [], "execution_count": None} if t == CODE else {})}
                for t, s in cells],
      "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 5}
for i, c in enumerate(nb["cells"]): c["id"] = f"serve-{i:02d}"
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "notebook", "serve_on_kaggle.ipynb")
json.dump(nb, open(out, "w"), indent=1)
print("wrote", os.path.abspath(out))
