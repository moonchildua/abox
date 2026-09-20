# Embedding model comparison

Standalone retrieval test for Lab 3. Three local models, one corpus, one
question set, one script. Nothing here touches the rest of the repo.

| File | What it is |
|---|---|
| `corpus.json` | 45 short DevOps passages (Kubernetes, Flux, Terraform, NGINX, AWS, retrieval). Each has `id`, `title`, `text`. |
| `questions.json` | 22 questions with the `relevant` corpus ids. Kinds: `exact` term lookup, `concept`, `config` how-to, `uk` Ukrainian query against English text. |
| `eval.py` | Embeds both files through each model's `/v1/embeddings`, applies the model's prefix convention, truncates to each dimension, scores with cosine. Python 3 only, no packages. |

## 1. Start the models

Each model is its own `llama serve` on its own port. Run the ones you want in
separate terminals. First start downloads the GGUF into `LLAMA_CACHE`.

```bash
# nomic-embed-text-v1.5 — 137M, mean pooling (from GGUF metadata)
llama serve -hf nomic-ai/nomic-embed-text-v1.5-GGUF:Q8_0 --embedding --port 8080

# EmbeddingGemma-300M — 300M, mean pooling. Gemma licence: accept it on
# huggingface.co/google/embeddinggemma-300m once; the ggml-org GGUF is ungated.
llama serve -hf ggml-org/embeddinggemma-300M-GGUF:Q8_0 --embedding --port 8081

# Qwen3-Embedding-0.6B — 0.6B, LAST-token pooling is required by the model card
llama serve -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --embedding --pooling last -ub 8192 --port 8082
```

Check a server answers before running the script:

```bash
curl -s localhost:8080/health
curl -s localhost:8080/v1/embeddings -H 'Content-Type: application/json' \
  -d '{"input":"search_query: hello"}' | python3 -c 'import sys,json; print(len(json.load(sys.stdin)["data"][0]["embedding"]))'
```

The second command prints the vector length (768 for nomic, 768 for Gemma, 1024 for Qwen3).

## 2. Run the comparison

```bash
python3 eval.py                 # every model whose server is up
python3 eval.py --model nomic   # one model
python3 eval.py --dims 768,256  # custom dimension list; 0 = full
python3 eval.py --json out.json # keep the raw numbers
python3 eval.py --misses        # also list every question the model got wrong
```

Output is a Markdown table ready to paste into the ADR, plus Hit@3 per question
kind at full dimension. With `--misses`, each model and dimension is followed by
the questions whose relevant chunk was not in the top 3: the question, the rank
the relevant chunk actually got, and the chunk ids the model placed above it.
That is the evidence behind a Hit@3 number; read it before explaining a miss.

## 3. Reading the numbers

- **Hit@3** — share of questions whose correct chunk is in the top 3. The number an agent with a small context window cares about.
- **MRR** — mean reciprocal rank of the first correct chunk. Distinguishes "rank 1" from "rank 3".
- **Hit@10** — whether a reranker could still rescue the miss.
- **ms/doc, ms/query** — wall-clock embedding latency through the HTTP API, on this machine, single client. Compare between models, not against published numbers.

With 22 questions one question is worth about 0.05 of Hit@3. Differences smaller than that are noise; extend `questions.json` before drawing fine conclusions.

## 4. Conditions that must hold

- Same corpus and questions for every model. Do not tune the questions for a model.
- Each model gets its own prefix convention, configured in `MODELS` inside `eval.py`. A wrong prefix silently lowers that model's score.
- Pooling is a server flag, not a client setting. Qwen3 without `--pooling last` produces valid-looking but wrong vectors.
- Dimensions are compared model-against-model at the same size. Truncation is prefix-truncate then L2-normalise, which is what a Matryoshka-trained model expects.

## 5. Adding a model or changing the data

- New model: add an entry to `MODELS` in `eval.py` (label, URL, query and doc format strings) and start its server. That is all.
- New passages or questions: edit the JSON. Every `relevant` id must exist in `corpus.json`; the script does not validate this.
