# Free deployment, step by step

Everything below is free: Kaggle (build the bundle), Hugging Face (backend Space on free CPU + a dataset repo for the bundle),
GitHub (code + GitHub Pages for the frontend). About 30–45 minutes the first time, most of it waiting for builds.

```
Kaggle notebook v9 ── section 17 ──► HF dataset  <you>/bd-food-rag-bundle
GitHub repo (this) ── Action ──────► HF Space    <you>/bd-food-rag   (FastAPI + web app, CPU)
                  └── Action ──────► GitHub Pages https://<github-user>.github.io/<repo>/  (same web app, calls the Space)
```

## 1. Hugging Face: two tokens

1. Create an account at huggingface.co.
2. *Settings → Access Tokens*: create a **write** token (for Kaggle and GitHub) and, if you will keep the bundle private, a **read** token (for the Space).

## 2. Kaggle: export the bundle

1. Open your notebook (v9) on Kaggle. *Add-ons → Secrets*: add `HF_TOKEN` = your **write** token, and tick it for this notebook.
2. In section 17 set `HF_BUNDLE_REPO = "<your-hf-name>/bd-food-rag-bundle"`.
3. Keep `DOMAIN = "bd"` in section 1 (or another domain, for a second app). Attaching your previous run's output (Add input → Notebook output) makes this much faster.
4. *Run All*. The end of section 17 prints the bundle size and `uploaded to https://huggingface.co/datasets/...`.

No token? The bundle is still written to `/kaggle/working/deploy_bundle/`: download it from the notebook's Output tab and upload the
folder's contents on huggingface.co (*New dataset → Files → Add file → Upload*).

## 3. Hugging Face: create the Space

1. *New Space*: name `bd-food-rag`, SDK **Docker** (blank template), hardware **CPU basic (free)**, public.
2. *Settings → Variables and secrets*:
   * variable `SHRAG_BUNDLE_REPO` = `<your-hf-name>/bd-food-rag-bundle`
   * secret `HF_TOKEN` = your **read** token (only needed if the dataset is private)
   * optional: `SHRAG_USE_LLM` = `1` and `SHRAG_GEN_MODEL` = `Qwen/Qwen2.5-0.5B-Instruct` to paraphrase answers with a small LLM
     (slow on free CPU, about 5–15 s per answer). Without it, answers are the verified knowledge-base sentences.
   * optional: `SHRAG_NO_IMAGE_MODELS` = `1` for a text-only app that starts faster.

## 4. GitHub: push the code (it then syncs to the Space)

```bash
git lfs install                      # thumbnails and pickles of demo_bundle are stored with Git LFS
git init -b main && git add . && git commit -m "Bangladeshi food self-healing RAG app"
git remote add origin https://github.com/<github-user>/bd-food-rag.git
git push -u origin main
```

In the GitHub repo: *Settings → Secrets and variables → Actions*:
* secret `HF_TOKEN` = your HF **write** token
* variable `HF_SPACE` = `<your-hf-name>/bd-food-rag`

The **Sync to Hugging Face Space** action runs on every push to `main` (re-run it from the *Actions* tab the first time if the secret was added
after the push). The Space builds the Docker image (about 10 min the first time), then downloads the models on start-up (about 6 GB,
another 3–6 min). Watch the Space's *Logs* tab.

Check it:
* `https://<your-hf-name>-bd-food-rag.hf.space/api/health` → `{"status": "ok"}`
* `https://<your-hf-name>-bd-food-rag.hf.space/api/parity` → `"decision_mismatches": 0` means the server makes the same decisions as the notebook
* `https://<your-hf-name>-bd-food-rag.hf.space/` → the web app

## 5. GitHub Pages (optional second front door)

The Space already serves the web app. To also publish it on GitHub Pages:
1. *Settings → Pages → Build and deployment → Source*: **GitHub Actions**.
2. *Settings → Secrets and variables → Actions → Variables*: `SPACE_URL` = `https://<your-hf-name>-bd-food-rag.hf.space`
3. Re-run the **Frontend on GitHub Pages** action. Your site: `https://<github-user>.github.io/bd-food-rag/`

## Updating the app

* **New results / new KB** (you re-ran the notebook): run section 17 again, then *Restart* the Space (Settings → Restart). No code change.
* **Changed notebook code**: regenerate the backend core from the new notebook, commit and push:
  `python tools/extract_core.py path/to/notebook.ipynb backend/shrag_core.py`
* **Another domain** (Indian, Food-101): run the notebook with that `DOMAIN`, upload to a second dataset repo, and create a second Space with that `SHRAG_BUNDLE_REPO`.

## Run it on your own computer or in Colab

```bash
pip install -r backend/requirements.txt
SHRAG_BUNDLE=path/to/deploy_bundle uvicorn app:app --app-dir backend --port 7860     # open http://localhost:7860
# or, with no installs at all, the synthetic test bundle and the standard-library server:
python backend/devserver.py --bundle demo_bundle --port 8000
```

## Limits of the free tier (worth saying in your report)

* Free Spaces **sleep after about 48 h without visitors**; the first request then waits for the restart (a few minutes).
* CPU only: text answers take about 1–3 s, photos about 2–6 s. The 4-bit generator and the judges from the notebook need a GPU, so the
  app answers extractively by default (the same verified sentences the notebook falls back to).
* The free Space has 16 GB RAM; the default models use about 7 GB.
