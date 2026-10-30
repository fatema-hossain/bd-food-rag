const API = (window.SHRAG_API || "").replace(/\/$/, "");
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const EXAMPLES = {
  bd: ["kacchi biriyani ki?", "ইলিশ মাছের ক্যালরি কত?", "khichuri ar daal er calorie koto", "show me pictures of ruti",
       "is khichuri ok for diabetes?", "tell me about shorshe ilsh", "how to make begun bhaji?", "what is sushi?"],
  other: ["tell me about the first dish", "how many calories in it?", "what is sushi?"],
};

// healing-trace codes -> plain words; kind: fix (something was repaired), stop (declined / refused), check (verified, nothing changed)
const STEPS = [
  [/^QUERY_REPAIR (fuzzy|phonetic):(.+?)->(.+)/, (m) => [`Fixed the spelling: “${m[2]}” → “${m[3]}”`, "fix"]],
  [/^LINK_REJECTED (?:fuzzy|phonetic):(.+?)->(\S+)/, (m) => [`Rejected a doubtful match: “${m[1]}” is probably not “${m[2]}”`, "check"]],
  [/^LINK_ACCEPTED/, () => ["Confirmed the repaired name against the knowledge base", "fix"]],
  [/^EVALUATOR CORRECT/, () => ["Checked the evidence: it is about this dish", "check"]],
  [/^EVALUATOR AMBIGUOUS/, () => ["Evidence was unclear, so it looked further", "check"]],
  [/^EVALUATOR INCORRECT/, () => ["The closest knowledge-base entry did not fit the question", "check"]],
  [/^REWRITE#\d+ '(.+?)'/, (m) => [`Rewrote the question as “${m[1]}” and searched again`, "fix"]],
  [/^ENTITY_GUARD/, () => ["Kept the evidence to the dish you named", "fix"]],
  [/^UNSUPPORTED_CLAIMS (\d+)/, (m) => [`Removed ${m[1]} sentence(s) the evidence does not support`, "fix"]],
  [/^REGENERATE/, () => ["Rewrote the answer more strictly", "fix"]],
  [/^EXTRACTIVE_FALLBACK/, () => ["Answered with knowledge-base text word for word", "fix"]],
  [/^RECIPE_QUESTION/, () => ["Recipe question: answered only with stored ingredients and method", "check"]],
  [/^DIET_QUESTION/, () => ["Diet question: suitability is taken only from FoodNetBD tags", "check"]],
  [/^DIET_TAG (\S+)\/(\S+)=(\w+)/, (m) => [`FoodNetBD tag found: ${m[3]}`, "check"]],
  [/^NO_DIET_TAG/, () => ["No FoodNetBD tag for this, so no health claim is made", "stop"]],
  [/^PROXY_MAPPING (.+?) ~ (.+)/, (m) => [`No separate FoodBD class, so “${m[2]}” plates stand in for ${m[1]}`, "check"]],
  [/^FOODNETBD_PER100G/, () => ["Added per-100 g values from FoodNetBD", "check"]],
  [/^NO_NUTRITION_DATA/, () => ["No measured nutrition data, so no numbers are given", "stop"]],
  [/^WIDE_RANGE/, () => ["Plates vary a lot, so confidence was lowered", "check"]],
  [/^PICTURE_LABEL_MISMATCH (\d+)\/(\d+)/, (m) => [`Filtered out ${m[1]} of ${m[2]} pictures that showed a different dish`, "fix"]],
  [/^ONLY_(\d+)_VERIFIED/, (m) => [`Only ${m[1]} verified picture(s) exist, none were padded in`, "check"]],
  [/^RECOGNISERS_DISAGREE/, () => ["The two image models disagreed, so similar labelled photos were consulted", "fix"]],
  [/^HEALED -> (.+?) \(/, (m) => [`After the extra vote: ${m[1]}`, "fix"]],
  [/^IMAGE_UNCERTAIN/, () => ["Not confident enough to name the dish", "stop"]],
  [/^CATEGORY_BACKOFF '(.+?)'/, (m) => [`Named the kind of dish (${m[1]}) instead of guessing the exact one`, "fix"]],
  [/^MEAL_PLATE/, () => ["Looks like a full meal plate: listed every detected dish", "fix"]],
  [/^PLATE_PHOTO/, () => ["Estimated the whole plate's nutrition from the photo", "check"]],
  [/^Question had no dish -> using image prediction '(.+?)'/, (m) => [`Used the photo to identify ${m[1]}`, "check"]],
  [/^ABSTAIN/, () => ["Declined: nothing reliable to answer from", "stop"]],
];
function humanize(trace) {
  const out = [];
  for (const t of trace) {
    for (const [re, f] of STEPS) { const m = t.match(re); if (m) { out.push(f(m)); break; } }
  }
  return out;
}

async function api(path, opts = {}) {
  const r = await fetch(API + path, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body?.detail?.status === "loading" ? "The models are still loading. Try again in a minute." : (body.error || `Server error ${r.status}`));
  return body;
}

const statusEl = $("#status");
async function waitReady() {
  for (let i = 0; i < 200; i++) {
    try {
      const h = await api("/api/health");
      if (h.status === "ok") break;
      if (h.status === "error") { statusEl.textContent = "Backend failed to start"; statusEl.classList.add("err"); return; }
      statusEl.textContent = "Loading models…";
    } catch { statusEl.textContent = "Cannot reach the backend"; statusEl.classList.add("err"); }
    await new Promise((r) => setTimeout(r, 3000));
  }
  try {
    const info = await api("/api/info");
    statusEl.classList.remove("err");
    statusEl.textContent = `${info.dishes} dishes, ${info.gallery_photos} photos`;
    renderExamples(info.domain === "bd" ? EXAMPLES.bd : EXAMPLES.other);
    renderAbout(info);
  } catch (e) { statusEl.textContent = e.message; statusEl.classList.add("err"); }
}

function renderExamples(list) {
  const box = $("#examples"); box.innerHTML = "";
  for (const q of list) {
    const b = document.createElement("button"); b.type = "button"; b.textContent = q;
    b.onclick = () => { $("#q").value = q; $("#ask").requestSubmit(); };
    box.appendChild(b);
  }
}

function renderAbout(info) {
  const rows = (info.benchmark?.text || []).filter((r) => /^(B2|FULL v)/.test(r.system));
  $("#about").innerHTML = `
    <p>The question goes through a self-healing pipeline: it links the dish name (fixing spelling, Banglish and Bangla variants),
    checks that the retrieved evidence is really about that dish, answers only from that evidence, and declines when the checks fail.
    Thresholds were tuned on a held-out dev set in the Kaggle notebook and frozen.</p>
    ${rows.length ? `<table><tr><th>system (test set, ${info.benchmark.n_test} questions)</th><th>accuracy</th><th>wrong-dish rate</th><th>decline F1</th></tr>
      ${rows.map((r) => `<tr><td>${esc(r.system)}</td><td>${(+r.accuracy).toFixed(3)}</td><td>${(+r["halluc."]).toFixed(3)}</td><td>${(+r["abstain F1"]).toFixed(3)}</td></tr>`).join("")}</table>` : ""}
    ${info.smoke_bundle ? "<p><strong>Note:</strong> this server runs a test bundle built from synthetic data.</p>" : ""}`;
}
$("#about-link").onclick = (e) => { e.preventDefault(); const a = $("#about"); a.hidden = !a.hidden; };

// photo picking
let photo = null;
$("#photo").onchange = (e) => {
  photo = e.target.files[0] || null;
  const pv = $("#preview");
  if (photo) { pv.src = URL.createObjectURL(photo); pv.hidden = false; $("#clear-photo").hidden = false; $("#photo-label").textContent = "Change photo"; }
};
$("#clear-photo").onclick = () => {
  photo = null; $("#photo").value = ""; $("#preview").hidden = true; $("#clear-photo").hidden = true; $("#photo-label").textContent = "Add a photo";
};

function paragraphs(text) { return String(text || "").split("\n").filter(Boolean).map((p) => `<p>${esc(p)}</p>`).join(""); }

function renderAnswer(card, q, imgUrl, r) {
  card.classList.remove("pending"); card.classList.add("fresh");
  if (r.abstained && !(r.plate_items || []).length) card.classList.add("declined");
  $(".asked", card).innerHTML = (imgUrl ? `<img src="${imgUrl}" alt="your photo">` : "") + esc(q || (imgUrl ? "Photo" : ""));
  const d = (r.entities || [])[0];
  $(".dish", card).innerHTML = d ? `${esc(r.entities.map((e) => e.name).join(" + "))}${d.bn && r.entities.length === 1 ? `<span class="bn">${esc(d.bn)}</span>` : ""}` : "";
  if (!d) $(".dish", card).remove();
  let text = String(r.answer || "");
  if (d && r.entities.length === 1) {               // the heading already names the dish: drop the repeated "Name (বাংলা). " opening
    for (const lead of [`${d.name} (${d.bn}). `, `${d.name}. `]) if (text.startsWith(lead)) { text = text.slice(lead.length); break; }
  }
  $(".text", card).innerHTML = paragraphs(text);
  const ex = $(".extras", card); let html = "";
  if (r.nutrition?.per_plate) {
    html += `<table class="nutri"><caption>Per plate, from ${r.nutrition.n_plates || "model over"} FoodBD plates (confidence: ${esc(r.nutrition.confidence)})</caption>
      ${Object.entries(r.nutrition.per_plate).map(([k, v]) => `<tr><th>${esc(k)}</th><td class="num">${Math.round(v[0])}</td><td class="range">${Math.round(v[1])}–${Math.round(v[2])}</td></tr>`).join("")}</table>`;
  }
  if (r.plate_estimate) {
    html += `<table class="nutri"><caption>Whole-plate estimate from the photo (80% range)</caption>
      ${Object.entries(r.plate_estimate).map(([k, v]) => `<tr><th>${esc(k)}</th><td class="num">${Math.round(v[0])}</td><td class="range">${Math.round(v[1])}–${Math.round(v[2])}</td></tr>`).join("")}</table>`;
  }
  if (r.diet?.length) html += `<div class="diet">${r.diet.map((t) => `<span class="${esc(t.tag)}">${esc(t.condition)}: ${esc(t.tag)}</span>`).join("")}</div>`;
  const pics = (r.pictures?.length ? r.pictures : r.similar) || [];
  if (pics.length) {
    html += `<div class="pics" aria-label="${r.pictures?.length ? "Verified pictures" : "Most similar labelled pictures"}">${pics.map((p) =>
      `<figure><img loading="lazy" src="${API + esc(p.url)}" alt="${esc(p.name)}"><figcaption>${esc(p.name)}</figcaption></figure>`).join("")}</div>`;
  }
  if (r.image_candidates?.length && r.abstained) html += `<p class="cands">Closest matches: ${r.image_candidates.map((c) => `${esc(c.name)} (${(+c.score).toFixed(2)})`).join(", ")}</p>`;
  ex.innerHTML = html;
  const steps = humanize(r.trace || []);
  $(".stitches", card).innerHTML = steps.length ? steps.map(([t, k]) => `<li class="${k}">${esc(t)}</li>`).join("")
    : `<li class="quiet">Nothing needed repairing</li>`;
  $(".stitches", card).insertAdjacentHTML("beforeend", `<li class="quiet">${Math.round(r.latency_ms || 0)} ms</li>`);
  const raw = $(".raw", card); raw.textContent = (r.trace || []).join("\n") || "(empty)";
  $(".raw-toggle", card).onclick = (e) => { raw.hidden = !raw.hidden; e.target.textContent = raw.hidden ? "Show raw trace" : "Hide raw trace"; };
}

$("#ask").onsubmit = async (e) => {
  e.preventDefault();
  const q = $("#q").value.trim();
  if (!q && !photo) { $("#q").focus(); return; }
  const card = $("#answer-tpl").content.firstElementChild.cloneNode(true);
  card.classList.add("pending"); $(".text", card).innerHTML = "<p>Checking…</p>";
  $(".asked", card).textContent = q; $("#answers").prepend(card);
  const send = $("#send"); send.disabled = true;
  const imgUrl = photo ? URL.createObjectURL(photo) : null;
  try {
    let r;
    if (photo) {
      const fd = new FormData(); fd.append("image", photo); fd.append("question", q);
      r = await api("/api/ask_image", { method: "POST", body: fd });
    } else {
      r = await api("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }) });
    }
    if (r.error) throw new Error(r.error);
    renderAnswer(card, q, imgUrl, r);
  } catch (err) {
    card.classList.remove("pending"); card.classList.add("declined");
    $(".text", card).innerHTML = `<p>${esc(err.message)}</p>`; $(".thread", card).remove(); $(".dish", card)?.remove();
  } finally { send.disabled = false; }
};
$("#q").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#ask").requestSubmit(); } });

waitReady();
