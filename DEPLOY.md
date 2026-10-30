# Free deployment, step by step

**Since July 2026, Hugging Face requires PRO for new Docker / Gradio Spaces on free CPU; only Static Spaces stay free.** So the free setup is:

```
Kaggle research notebook (v10) ── section 17 ──► HF dataset  Fatema042/bd-food-rag-bundle   (KB, thresholds, trained heads, thumbnails)
                                                     │ downloaded at start-up        ▲ server.json = current server address
Kaggle notebook "serve_on_kaggle" (GPU, free) ── FastAPI backend ── Cloudflare quick tunnel ──► https://….trycloudflare.com
GitHub repo ── GitHub Actions ──► GitHub Pages  https://<github-user>.github.io/bd-food-rag/   (the web app; finds the server via server.json)
```

* **Frontend**: always online, free (GitHub Pages).
* **Backend**: online while the serving notebook runs (up to ~12 h per run on Kaggle, browser can be closed). Ideal for demos, evaluations and
  presentations. When it is not running, the page says the server is offline.
* Want it online 24/7 for free? See *Option B* at the end (Oracle Cloud Always Free VM; needs a card for identity check, no charges).

## 1. Hugging Face: token and bundle (already done if section 17 printed "uploaded to …")
1. huggingface.co → profile picture → *Settings → Access Tokens* → **Create new token**, type **Write**. Copy it (`hf_…`).
2. In the research notebook on Kaggle: *Add-ons → Secrets* → `HF_TOKEN` = the token (ticked).
3. Section 17: `HF_BUNDLE_REPO = "Fatema042/bd-food-rag-bundle"`, then *Run All*.
4. Keep that dataset **public** (default), so the web page can read `server.json`.

## 2. GitHub: put the code online
1. github.com → **+ → New repository** → name `bd-food-rag`, **Public**, no README / .gitignore / license.
2. Install Git (git-scm.com; on Windows it includes Git LFS). Unzip `shrag-app.zip`, open a terminal in the `shrag-app` folder
   (Windows: right-click → *Open Git Bash here*):
   ```bash
   git lfs install
   git remote add origin https://github.com/<your-github-username>/bd-food-rag.git
   git push -u origin main
   ```
   Log in with *Sign in with your browser* when asked.
3. Repo → **Settings → Pages** → *Build and deployment → Source*: **GitHub Actions**.
4. Repo → **Actions** → *Frontend on GitHub Pages* → **Run workflow**. After about a minute your site is at
   `https://<your-github-username>.github.io/bd-food-rag/` (it will say the server is offline until step 3 below).

(The workflow *Sync to Hugging Face Space* is skipped automatically; it is only for people with HF PRO.)

## 3. Kaggle: start the server
1. On Kaggle: **Create → New Notebook → File → Import Notebook** → upload `notebook/serve_on_kaggle.ipynb` from the zip.
2. Right panel: **Accelerator: GPU T4** (x1 is enough), **Internet: On**. *Add-ons → Secrets*: tick `HF_TOKEN`.
3. In the first code cell put your GitHub username in `APP_REPO` and `PAGES_URL` (`BUNDLE_REPO` is already `Fatema042/bd-food-rag-bundle`).
4. Quick test: run the cells one by one. The 3rd cell prints `server: {'status': 'ok'}` and the parity check
   (`decision_mismatches: 0` = same decisions as the research notebook); the 4th prints the public address and "published to … server.json".
   Open your GitHub Pages site: it connects by itself.
5. For a long session with the browser closed: **Save Version → Save & Run All (Commit)**. It serves for `SERVE_HOURS` (11.5 h).
   To stop early: *View Active Events* → stop the run.

Each start takes ~5–10 min (models download fresh in every Kaggle session). Start the server a little before you need it.

## Updating
* **New results** (you re-ran the research notebook + section 17): just restart the serving notebook.
* **Changed notebook code**: `python tools/extract_core.py <research-notebook>.ipynb backend/shrag_core.py`, commit, push; restart the serving notebook.
* **Frontend changes**: edit `frontend/`, commit, push; GitHub Pages redeploys.

## Option B: always online, still free (Oracle Cloud "Always Free")
Oracle gives an *Always Free* ARM VM (up to 4 cores, 24 GB RAM). Sign-up needs a card for identity verification (no charge on Always Free).
1. Create an *Ampere A1* instance (Ubuntu, 4 OCPU / 24 GB), open port 7860 in its security list.
2. On the VM: `sudo apt install -y docker.io git && git clone https://github.com/<you>/bd-food-rag && cd bd-food-rag`
3. `sudo docker build -t bdfood . && sudo docker run -d --restart=always -p 7860:7860 -e SHRAG_BUNDLE_REPO=Fatema042/bd-food-rag-bundle bdfood`
4. Put `http://<vm-ip>:7860` (or a domain with HTTPS, e.g. a free Cloudflare tunnel on the VM) in the GitHub repo variable `SPACE_URL`
   and re-run *Frontend on GitHub Pages*. CPU only: text answers ~1–3 s, photos ~2–6 s, LLM paraphrasing off.

## Option C: Hugging Face PRO (paid) or an older account
If you have PRO, create a **Docker** Space `Fatema042/bd-food-rag`, set its variable `SHRAG_BUNDLE_REPO`, add GitHub secret `HF_TOKEN` and
variable `HF_SPACE = Fatema042/bd-food-rag`; the *Sync to Hugging Face Space* workflow then deploys it.

## Run it on your own computer
```bash
pip install -r backend/requirements.txt
SHRAG_BUNDLE_REPO=Fatema042/bd-food-rag-bundle uvicorn app:app --app-dir backend --port 7860      # open http://localhost:7860
python backend/devserver.py --bundle demo_bundle --port 8000                                       # no installs, synthetic test bundle
```
