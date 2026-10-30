---
title: Bangladeshi Food Self-Healing RAG
emoji: 🍛
colorFrom: green
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Ask about Bangladeshi dishes in Bangla, Banglish or English
---

# খাবার জিজ্ঞাসা — self-healing RAG for Bangladeshi food

Web app for the Kaggle research notebook *Self-Healing Multimodal RAG for Bangladeshi Food*. Ask in বাংলা, Banglish or English,
or send a food photo. The backend runs **the same functions as the notebook** (generated from it), with the thresholds that were
tuned on the notebook's dev split, so the deployed app behaves like the benchmarked FULL system: it repairs spellings, checks that
the evidence is about the dish, answers only from data, and declines when it cannot be sure.

```
Kaggle research notebook ── section 17 ──► HF dataset (bundle + server.json)
Kaggle "serve_on_kaggle" notebook (GPU) ── FastAPI ── Cloudflare tunnel ──► public https address
GitHub repo (this) ── Actions ──► GitHub Pages web app (finds the server address in server.json)
```

Hugging Face Docker Spaces need PRO for new accounts since July 2026, so the free route serves the backend from Kaggle (see DEPLOY.md).

* `backend/shrag_core.py` – generated from the notebook by `tools/extract_core.py` (never edit by hand)
* `backend/service.py` – loads the bundle into those functions, loads the models on CPU
* `backend/app.py` – FastAPI routes; `backend/devserver.py` – the same routes with no dependencies (local testing)
* `frontend/` – static web app (works on the Space itself and on GitHub Pages)
* `demo_bundle/` – a tiny synthetic bundle so the app starts before you export a real one
* `notebook/` – the research notebook (v10) and `serve_on_kaggle.ipynb` (runs the backend on Kaggle)

See **DEPLOY.md** for the step-by-step free deployment.
