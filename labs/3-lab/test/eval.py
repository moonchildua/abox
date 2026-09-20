#!/usr/bin/env python3
"""Compare local embedding models on a small retrieval task.

Each model is a llama.cpp server exposing /v1/embeddings. The script embeds
corpus.json and questions.json with the model's own prefix convention,
truncates the vectors to each requested dimension (Matryoshka), re-normalises,
scores every question against every chunk with cosine similarity and prints
Hit@3, MRR, Hit@10 and embedding latency.

No third-party dependencies: urllib for HTTP, plain Python for the maths.

Usage:
    python3 eval.py                      # every model whose server answers
    python3 eval.py --model nomic        # one model
    python3 eval.py --dims 768,256       # override the dimension list
    python3 eval.py --json results.json  # also dump raw numbers
"""

import argparse
import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

# One entry per model. `query` and `doc` are format strings applied before
# embedding; {text} is the question or the chunk, {title} the chunk title.
# Pooling is a server-side flag (see README), not something the client sets.
MODELS = {
    "nomic": {
        "label": "nomic-embed-text-v1.5",
        "url": "http://127.0.0.1:8080",
        "query": "search_query: {text}",
        "doc": "search_document: {text}",
    },
    "gemma": {
        "label": "EmbeddingGemma-300M",
        "url": "http://127.0.0.1:8081",
        "query": "task: search result | query: {text}",
        "doc": "title: {title} | text: {text}",
    },
    "qwen3": {
        "label": "Qwen3-Embedding-0.6B",
        "url": "http://127.0.0.1:8082",
        "query": "Instruct: Given a question, retrieve passages that answer it\nQuery:{text}",
        "doc": "{text}",
    },
}

DEFAULT_DIMS = [0, 512, 256, 128]  # 0 means the model's full dimension
BATCH = 8


# --- HTTP -------------------------------------------------------------------

def server_alive(url):
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=3) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def embed(url, texts):
    """Return (vectors, seconds) for a list of strings via /v1/embeddings."""
    vectors, elapsed = [], 0.0
    for i in range(0, len(texts), BATCH):
        chunk = texts[i:i + BATCH]
        body = json.dumps({"input": chunk, "model": "local"}).encode()
        req = urllib.request.Request(
            f"{url}/v1/embeddings", data=body,
            headers={"Content-Type": "application/json"},
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.load(r)["data"]
        elapsed += time.perf_counter() - t0
        data.sort(key=lambda d: d["index"])
        vectors.extend(d["embedding"] for d in data)
    return vectors, elapsed


# --- maths ------------------------------------------------------------------

def normalise(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n else v


def truncate(v, dim):
    return normalise(v[:dim]) if dim and dim < len(v) else normalise(v)


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def rank(query_vec, doc_vecs):
    """Indices of docs sorted by descending similarity."""
    scores = [dot(query_vec, d) for d in doc_vecs]
    return sorted(range(len(doc_vecs)), key=lambda i: scores[i], reverse=True)


def score(questions, doc_ids, q_vecs, d_vecs):
    """Metrics plus the list of questions whose relevant chunk is not in the top 3.

    Each miss records the 1-based rank of the first relevant chunk (None when
    it is not in the ranking at all) and the ids the model ranked above it.
    """
    hit3 = hit10 = rr = 0.0
    misses = []
    for q, qv in zip(questions, q_vecs):
        order = [doc_ids[i] for i in rank(qv, d_vecs)]
        first = next((pos for pos, did in enumerate(order) if did in q["relevant"]), None)
        if first is None or first >= 3:
            misses.append({
                "id": q["id"], "kind": q["kind"], "question": q["question"],
                "relevant": q["relevant"],
                "rank": None if first is None else first + 1,
                "above": order[:first] if first is not None else order[:10],
            })
        if first is None:
            continue
        rr += 1.0 / (first + 1)
        hit3 += first < 3
        hit10 += first < 10
    n = len(questions)
    return {"hit@3": hit3 / n, "mrr": rr / n, "hit@10": hit10 / n, "misses": misses}


# --- main -------------------------------------------------------------------

def run_model(key, cfg, corpus, questions, dims):
    print(f"\n== {cfg['label']} ({cfg['url']})", file=sys.stderr)
    doc_texts = [cfg["doc"].format(text=c["text"], title=c["title"]) for c in corpus]
    q_texts = [cfg["query"].format(text=q["question"]) for q in questions]

    d_raw, d_sec = embed(cfg["url"], doc_texts)
    q_raw, q_sec = embed(cfg["url"], q_texts)
    full = len(d_raw[0])
    print(f"   full dim {full}, {len(doc_texts)} docs in {d_sec:.2f}s, "
          f"{len(q_texts)} queries in {q_sec:.2f}s", file=sys.stderr)

    doc_ids = [c["id"] for c in corpus]
    rows = []
    for dim in dims:
        if dim and dim > full:
            continue
        d_vecs = [truncate(v, dim) for v in d_raw]
        q_vecs = [truncate(v, dim) for v in q_raw]
        m = score(questions, doc_ids, q_vecs, d_vecs)
        rows.append({
            "model": cfg["label"], "dim": dim or full, **m,
            "ms_per_doc": 1000 * d_sec / len(doc_texts),
            "ms_per_query": 1000 * q_sec / len(q_texts),
        })
    # by_kind only needs the aggregate; drop the miss lists it would carry
    # per-kind breakdown at full dimension, useful for the ADR discussion
    kinds = {}
    for q, qv in zip(questions, [truncate(v, 0) for v in q_raw]):
        kinds.setdefault(q["kind"], []).append(q)
    by_kind = {k: score(qs, doc_ids,
                        [truncate(q_raw[questions.index(q)], 0) for q in qs],
                        [truncate(v, 0) for v in d_raw])["hit@3"]
               for k, qs in kinds.items()}
    return rows, by_kind


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", action="append", choices=MODELS, help="run only this model (repeatable)")
    ap.add_argument("--dims", default=",".join(map(str, DEFAULT_DIMS)))
    ap.add_argument("--json", type=Path, help="write raw results here")
    ap.add_argument("--misses", action="store_true",
                    help="after the tables, list every question whose relevant chunk is not in the top 3")
    args = ap.parse_args()

    corpus = json.loads((HERE / "corpus.json").read_text())
    questions = json.loads((HERE / "questions.json").read_text())
    dims = [int(x) for x in args.dims.split(",")]
    wanted = args.model or list(MODELS)

    all_rows, all_kinds = [], {}
    for key in wanted:
        cfg = MODELS[key]
        if not server_alive(cfg["url"]):
            print(f"\n== {cfg['label']}: no server at {cfg['url']}, skipped", file=sys.stderr)
            continue
        rows, by_kind = run_model(key, cfg, corpus, questions, dims)
        all_rows.extend(rows)
        all_kinds[cfg["label"]] = by_kind

    if not all_rows:
        sys.exit("no model answered; start at least one llama.cpp server (see README.md)")

    print("\n| Model | Dim | Hit@3 | MRR | Hit@10 | ms/doc | ms/query |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for r in all_rows:
        print(f"| {r['model']} | {r['dim']} | {r['hit@3']:.2f} | {r['mrr']:.2f} | "
              f"{r['hit@10']:.2f} | {r['ms_per_doc']:.0f} | {r['ms_per_query']:.0f} |")

    kinds = sorted({k for d in all_kinds.values() for k in d})
    print("\nHit@3 by question kind at full dimension:\n")
    print("| Model | " + " | ".join(kinds) + " |")
    print("|---|" + "---:|" * len(kinds))
    for label, d in all_kinds.items():
        print(f"| {label} | " + " | ".join(f"{d.get(k, 0):.2f}" for k in kinds) + " |")

    if args.misses:
        print("\nMisses (relevant chunk not in top 3):")
        for r in all_rows:
            print(f"\n{r['model']} @ {r['dim']}: {len(r['misses'])} miss(es)")
            for m in r["misses"]:
                where = f"rank {m['rank']}" if m["rank"] else "not in top 10"
                print(f"  {m['id']} [{m['kind']}] {m['question']}")
                print(f"    relevant {m['relevant']} -> {where}; ranked above: {m['above']}")

    if args.json:
        args.json.write_text(json.dumps({"rows": all_rows, "by_kind": all_kinds}, indent=2))
        print(f"\nraw results written to {args.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
