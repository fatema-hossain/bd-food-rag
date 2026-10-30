// Where the answer server lives.
// SHRAG_DISCOVERY: a small JSON file {"url": "https://….trycloudflare.com"} that the Kaggle serving notebook updates every time it
// starts, so this page finds the current server by itself. Change Fatema042/bd-food-rag-bundle if your dataset has another name.
// SHRAG_API: a fixed server address (leave empty). A link with ?api=<address> also works and is remembered on that device.
window.SHRAG_DISCOVERY = window.SHRAG_DISCOVERY ?? "https://huggingface.co/datasets/Fatema042/bd-food-rag-bundle/resolve/main/server.json";
window.SHRAG_API = window.SHRAG_API ?? "";
