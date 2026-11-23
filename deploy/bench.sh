#!/usr/bin/env bash
# Measures real generation speed of the configured model and memory use on this VPS.
set -euo pipefail
cd "$(dirname "$0")"
DC="docker compose"; docker compose version >/dev/null 2>&1 || DC="docker-compose"
$DC exec -T api python - <<'PY'
import json, time, urllib.request, os
url = os.environ.get("OLLAMA_URL", "http://ollama:11434") + "/api/chat"
model = os.environ.get("LLM_MODEL", "qwen2.5:0.5b")
opts = {"num_ctx": int(os.environ.get("LLM_NUM_CTX", 2048)), "num_predict": int(os.environ.get("LLM_NUM_PREDICT", 220)),
        "temperature": 0.7}
system = ("Ты — рассказчик ролевой истории «Маяк на Стеклянном берегу» и говоришь за персонажей: Ива, Харитон. "
          "Отвечай по-русски, 1–4 строки, каждая начинается с имени и двоеточия. Действия — в *звёздочках*.\n") * 6
msgs = [{"role": "system", "content": system},
        {"role": "user", "content": "Ян: *сажусь рядом с Ивой и беру её за руку* Ты чего притихла?\n\nОтветь за: Рассказчик, Ива."}]
for label in ("cold/prompt", "warm (cached prefix)"):
    t0 = time.time()
    req = urllib.request.Request(url, data=json.dumps({"model": model, "messages": msgs, "stream": False, "options": opts,
                                                      "keep_alive": -1}).encode(), headers={"Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=900))
    pe, pd, ec, ed = d.get("prompt_eval_count", 0), d.get("prompt_eval_duration", 1), d.get("eval_count", 0), d.get("eval_duration", 1)
    print(f"[{label}] model={model} total={time.time()-t0:.1f}s prompt={pe} tok @ {pe/(pd/1e9):.1f} tok/s, "
          f"output={ec} tok @ {ec/(ed/1e9):.1f} tok/s")
print("sample:", d["message"]["content"][:300].replace("\n", " | "))
PY
echo
echo "--- memory ---"
free -m
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}'
echo
echo "--- disk ---"
df -h / | tail -1
du -sh data/* 2>/dev/null || true
