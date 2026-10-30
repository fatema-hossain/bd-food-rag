"""Serving layer: loads a deploy bundle (exported by section 17 of the notebook) into the notebook's own functions.

The decision logic is NOT re-implemented here: `shrag_core` is generated from the notebook by tools/extract_core.py, and this module
only (1) restores the state the notebook built (KB, tuned thresholds, nutrition models, gallery embeddings, trained heads),
(2) loads the pretrained models on CPU, and (3) turns results into JSON.
"""
import collections, io, json, os, pickle, tempfile, threading, time, uuid

import numpy as np
import pandas as pd

import shrag_core as C

DATA_KEYS = ["DOMAIN", "DOMAIN_LABEL", "DOCS", "ALIAS2CANON", "ALIAS_FOLD", "ALIAS_LIST", "ALIAS_KEY_NW", "ALIAS_KEY_LIST", "FOODBD_MAP",
             "NUTR100", "HEALTH", "DOC_IDS", "DOC_POS", "DOC_TEXT", "INDEX_TEXT", "KB_KEY", "NAMES", "NC", "LOOKUP_S", "Q_PRES", "ridge_p",
             "G_EMB", "G_LAB", "G_PATHS", "IMG_CLASSES", "PROBE", "W_FUSE", "W_HEAL", "IMG_HEAL", "IMG_CAL", "IMG_TAU", "CAT_TAU", "IMG_SOURCE",
             "_rA", "PLATE_DET", "DET_CLASSES", "DET_THR", "ROUTER", "ROUTER_T", "PLATE", "_e2e", "_Qimg", "PLATE_COND", "_cclf"]


def _jsonable(x):
    if isinstance(x, dict): return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set, frozenset)): return [_jsonable(v) for v in x]
    if isinstance(x, np.generic): return x.item()
    if isinstance(x, np.ndarray): return x.tolist()
    if isinstance(x, float) and (x != x or x in (float("inf"), float("-inf"))): return None
    return x


class Service:
    def __init__(self, bundle_dir, use_llm=None, load_models=True):
        t0 = time.time(); self.bundle = os.path.abspath(bundle_dir); self.lock = threading.Lock()
        with open(os.path.join(self.bundle, "state.pkl"), "rb") as f: st = pickle.load(f)
        self.state_meta = {"results": st.get("results"), "model_status_at_export": st.get("MODEL_STATUS"), "smoke_bundle": st.get("SMOKE")}
        # --- restore notebook state into the generated core ---
        C.SMOKE = bool(st.get("SMOKE")) or not load_models          # a SMOKE bundle (or no models) -> the notebook's own fallbacks
        C.CFG.update(st["CFG"])
        C.CFG["USE_LLM"] = (os.environ.get("SHRAG_USE_LLM", "0") == "1") if use_llm is None else use_llm
        if os.environ.get("SHRAG_GEN_MODEL"): C.CFG["GEN_MODEL"] = os.environ["SHRAG_GEN_MODEL"]       # CPU: e.g. Qwen/Qwen2.5-0.5B-Instruct
        for k in DATA_KEYS:
            if k in st: setattr(C, k, st[k])
        C.ALIASES = collections.defaultdict(set, {k: set(v) for k, v in st["ALIASES"].items()})
        C.ALIAS_KEYS = collections.defaultdict(set, {k: set(v) for k, v in st["ALIAS_KEYS"].items()})
        C.DOC_FACTS = collections.defaultdict(list, {k: list(v) for k, v in st["DOC_FACTS"].items()})
        p = st["plates"]; C.plates = pd.DataFrame({"items": [frozenset(x) for x in p["items"]], "split": p["split"], **{c: p[c] for c in C.NUTR}})
        C.FULL.update(st["FULL"]); C.THR.update(st["FULL"].get("thr", {}))
        C.P_PATHS, C.P_LAB, C.P_EMB = C.G_PATHS, C.G_LAB, C.G_EMB
        C.INST = pd.DataFrame(columns=["poly"]); C.OOD = "__ood__"
        heads = st.get("_heads")
        C._det_proba = (lambda E: np.stack([h.predict_proba(E)[:, 1] for h in heads], 1)) if heads else None
        # caches exported with the bundle (doc embeddings, evaluator pair scores) are read through the notebook's cache_file()
        C.CACHE = os.path.join(os.environ.get("SHRAG_WORK", tempfile.gettempdir()), "shrag_cache"); os.makedirs(C.CACHE, exist_ok=True)
        C.INPUT_CACHES = [os.path.join(self.bundle, "cache")]
        for cache in ("_LINK_CACHE", "FEATS", "_VERIFY", "_GEN_CACHE", "_IMG", "_LABEL_MAP", "_LLM", "_WIKI"):
            if hasattr(C, cache): getattr(C, cache).clear()
        # --- models (CPU); identical classes to the notebook ---
        C.ENC = C.DenseEncoder(C.CFG["EMBED_MODEL"], "embedder:" + C.CFG["EMBED_MODEL"])
        has_st = C.HAS_ST; C.HAS_ST = False                       # the v1 baseline encoder is only used by baselines -> TF-IDF stand-in
        base = C.DenseEncoder(C.CFG["BASELINE_EMBED"], "baseline-embedder (not used by FULL)"); C.HAS_ST = has_st
        C.RET = C.HybridRetriever(C.ENC, base)
        C.GRADER = C.RetrievalEvaluator(); C.GRADER.load()
        C.NLI = C.NLIChecker()
        C.CLF, C.CLIP = None, None
        if not C.SMOKE and C.HAS_TF and C.HAS_TORCH and os.environ.get("SHRAG_NO_IMAGE_MODELS") != "1":
            from transformers import pipeline, CLIPModel, CLIPProcessor
            if C.CFG.get("CLF_MODEL"):
                C.CLF = C.try_load("image-classifier:" + C.CFG["CLF_MODEL"], lambda: pipeline("image-classification", model=C.CFG["CLF_MODEL"], top_k=5, device=-1))
            C.CLIP = C.try_load("clip:" + C.CFG["CLIP_MODEL"], lambda: (CLIPModel.from_pretrained(C.CFG["CLIP_MODEL"]).eval(), CLIPProcessor.from_pretrained(C.CFG["CLIP_MODEL"])))
        C.IMAGE_HOOK["search"] = C.image_search
        self.load_s = round(time.time() - t0, 1)

    # ---------------- helpers ----------------
    def _pic(self, path_label):
        p, l = path_label[0], path_label[1]
        return {"url": "/bundle/" + p if not str(p).startswith(("http", "/")) else p, "dish": str(l),
                "name": C.DOCS.get(str(l), {}).get("name", str(l))}

    def _dish(self, c):
        d = C.DOCS.get(c, {})
        return {"id": c, "name": d.get("name", c), "bn": d.get("bn", ""), "category": d.get("category", "")}

    def _text_result(self, res):
        out = {"answer": res["answer"], "intent": res.get("intent"), "abstained": bool(res.get("abstained")), "kind": res.get("kind"),
               "entities": [self._dish(c) for c in res.get("entities", [])], "trace": list(res.get("trace", [])),
               "latency_ms": round(float(res.get("latency_ms", 0.0)), 1), "pictures": [], "nutrition": None, "diet": None}
        imgs = res.get("images")
        if imgs and imgs.get("pictures"): out["pictures"] = [self._pic(x) for x in imgs["pictures"]]
        n = res.get("nutrition")
        if n: out["nutrition"] = {"tier": n["tier"], "n_plates": n["n"], "confidence": n["conf"],
                                  "per_plate": {C.LABEL.get(k, k): [round(float(v[0]), 1), round(float(v[1]), 1), round(float(v[2]), 1)] for k, v in n["stats"].items() if k in C.NUTR}}
        if res.get("health"): out["diet"] = [{"dish": c, "condition": C.COND_NAME.get(k, k), "tag": v} for (c, k), v in res["health"].items()]
        g = res.get("gen")
        if g: out["generation"] = {"stage": g.get("stage"), "generator": g.get("generator"), "evidence": g.get("evidence")}
        return _jsonable(out)

    # ---------------- API ----------------
    def ask(self, question):
        question = (question or "").strip()[:500]
        if not question: return {"error": "empty question"}
        with self.lock:
            return self._text_result(C.answer_query(question, use_llm=C.CFG["USE_LLM"]))

    def ask_image(self, image_bytes, question=None):
        from PIL import Image
        im = Image.open(io.BytesIO(image_bytes)).convert("RGB"); im.thumbnail((1024, 1024))
        tmp = os.path.join(tempfile.gettempdir(), f"upload_{uuid.uuid4().hex}.jpg"); im.save(tmp, quality=90)
        t0 = time.perf_counter()
        try:
            with self.lock:
                rep = C.multimodal_answer((question or "").strip()[:500] or None, image=tmp)
                C._IMG.pop(tmp, None)
        finally:
            try: os.remove(tmp)
            except OSError: pass
        text = rep.get("text") or {}
        out = self._text_result(text) if "query" in text else {"answer": text.get("answer", ""), "entities": [], "trace": [], "pictures": [],
                                                              "nutrition": None, "diet": None, "abstained": True}
        out["trace"] = list(rep.get("trace", []))
        out["image_candidates"] = [{"dish": c, "name": C.DOCS.get(c, {}).get("name", c), "score": s} for c, s in rep.get("image_candidates", [])]
        out["plate_items"] = rep.get("plate_items"); out["plate_prob"] = rep.get("plate_prob")
        if rep.get("plate_estimate"):
            out["plate_estimate"] = {C.LABEL.get(k, k): [round(float(v[0]), 1), round(float(v[1]), 1), round(float(v[2]), 1)]
                                     for k, v in rep["plate_estimate"].items() if k in C.NUTR}
        out["similar"] = [self._pic(x) for x in rep.get("similar", [])][:6]
        out["latency_ms"] = round(1000 * (time.perf_counter() - t0), 1)
        return _jsonable(out)

    def info(self):
        return _jsonable({"domain": C.DOMAIN, "domain_label": C.DOMAIN_LABEL, "dishes": len(C.DOCS), "aliases": len(C.ALIAS2CANON),
                          "gallery_photos": len(C.G_PATHS), "photo_dishes": len(set(map(str, C.G_LAB))), "use_llm": C.CFG["USE_LLM"],
                          "models": C.MODEL_STATUS, "load_seconds": self.load_s, "image_tau": C.IMG_TAU, "thresholds": C.FULL.get("thr"),
                          "benchmark": self.state_meta["results"], "smoke_bundle": self.state_meta["smoke_bundle"]})

    def parity(self, limit=None):
        """Re-run the notebook's parity questions; decisions must match the notebook (same functions, same thresholds)."""
        path = os.path.join(self.bundle, "parity.json")
        if not os.path.exists(path): return {"checked": 0}
        rows = json.load(open(path))[:limit]; bad = []
        with self.lock:
            for r in rows:
                res = C.answer_query(r["q"], use_llm=False)
                if sorted(res["entities"]) != sorted(r["entities"]) or bool(res["abstained"]) != r["abstained"]:
                    bad.append({"q": r["q"], "notebook": r["entities"], "server": res["entities"]})
        return {"checked": len(rows), "decision_mismatches": len(bad), "examples": bad[:5]}
