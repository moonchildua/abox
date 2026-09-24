# ADR-001: Agentic retrieval over Qdrant -- official MCP server vs. the in-house one

- Status: Proposed (results pending, see "Results")
- Date: 2026-09-24
- Branch: `feat/llmd-embeddings`, cluster bootstrapped from the `releases-llmd-embeddings` artifact

## Context

The lab task: deploy from the `feat/llmd-embeddings` release, add the official
Qdrant MCP server ([qdrant/mcp-server-qdrant](https://github.com/qdrant/mcp-server-qdrant))
next to the in-house `qdrant-mcp`, give `retrieval-agent` its tools and a
system prompt for them, index the same data (Kubernetes manifests) through
both servers, and compare the quality of agentic retrieval.

Starting point in the cluster:

- `retrieval-agent` ingests manifests into Neo4j (graph) and Qdrant (prose)
  and answers questions from those stores.
- Its vector tools come from `qdrant-mcp`, which embeds through the llama.cpp
  `/v1/embeddings` route with `nomic-embed-text-v1.5` (768 dims) into the
  collection `abox-nomic`.
- The official server embeds in-process with fastembed; its default model is
  `sentence-transformers/all-MiniLM-L6-v2` (384 dims).

The question this ADR answers: which of the two tool sets `retrieval-agent`
should use, decided on measured retrieval quality over the same corpus.

## Decision

Run both MCP servers side by side and compare them on the same corpus with the
same agent and the same model.

| | `qdrant-mcp` (in-house) | `qdrant-mcp-official` |
|---|---|---|
| Source | `mcp/qdrant-mcp/`, Go, `ghcr.io/den-vasyliev/abox/qdrant-mcp:0.4.0` | PyPI `mcp-server-qdrant==0.8.1`, image built from `lab4/Dockerfile` |
| Tools | `vector_store`, `vector_find` | `qdrant-store`, `qdrant-find` |
| Embedding | `nomic-embed-text-v1.5` via llama.cpp `/v1/embeddings` | `all-MiniLM-L6-v2` in-process via fastembed |
| Dimensions | 768 | 384 |
| Collection | `abox-nomic` | `abox-minilm` |
| Transport | stdio, adapted by kmcp | stdio, adapted by kmcp |
| Memory limit | 256Mi | 2Gi |

Details that shape the comparison:

1. **Separate collections are mandatory.** 384 and 768 dims cannot share a
   collection, and even at equal width vectors from different models do not
   transfer. Switching the agent's tool set is a re-embed, never a copy.
2. **The official server ships as a locally built image.** Upstream publishes
   no image, only a Dockerfile. `lab4/Dockerfile` pins the package version and
   downloads the MiniLM weights at build time into `/models`, so a pod starts
   without reaching HuggingFace. The image is loaded into the kind nodes with
   `kind load docker-image`; a Codespace restart wipes it and it has to be
   rebuilt.
3. **Nothing in `lab4/` ships.** The cluster reconciles the OCI artifact CI
   publishes, so the MCPServer and the Agent changes here are applied by hand.
   Both agents are taken out of Flux reconciliation so it does not revert the
   hand edits (model, tools, prompt):

   ```bash
   kubectl annotate agent k8s-agent -n kagent kustomize.toolkit.fluxcd.io/reconcile=disabled --overwrite
   kubectl -n kagent annotate agent retrieval-agent kustomize.toolkit.fluxcd.io/reconcile=disabled --overwrite
   ```

   Removing the annotation hands the objects back to Flux, which restores the
   shipped spec on the next reconcile.
4. **One model for both agents.** `retrieval-agent` and `k8s-agent` use the
   ModelConfig `gemini-gemini-3-1-flash-lite`. A small, fast model was chosen
   deliberately: differences in answers should come from the retrieval tools,
   not from the model's own knowledge.
5. **Same corpus, two indexes.** The cluster's Kubernetes manifests are ingested
   once through each tool set, into its own collection, by the same agent
   prompt.

## Progress

| # | Task | Status | Where |
|---|---|---|---|
| 1 | Deploy from the `feat/llmd-embeddings` release | done | cluster reconciles `releases-llmd-embeddings` |
| 2 | Add the official Qdrant MCP server | done | `lab4/qdrant-mcp-official.yaml`, `lab4/Dockerfile`; kagent lists `qdrant-find`, `qdrant-store` under `kagent/qdrant-mcp-official`; a store/find round-trip created `abox-minilm` (384 dims, Cosine) |
| 3 | Set the model for `retrieval-agent` and `k8s-agent` | done | both use ModelConfig `gemini-gemini-3-1-flash-lite`; both annotated `reconcile=disabled` so Flux keeps the change |
| 4 | Give `retrieval-agent` the official server's tools | done | `lab4/retrieval-agent-mcp-official.yaml`: `qdrant-store`, `qdrant-find` from `qdrant-mcp-official` added next to the in-house set; agent generation 5, Ready |
| 5 | System prompt for the official tools | pending | same file, `systemMessage` |
| 6 | Index the manifests with `all-MiniLM-L6-v2` | pending | -> `abox-minilm` |
| 7 | Index the same manifests with the in-house tool set | pending | -> `abox-nomic` |
| 8 | Compare, score, record here | pending | "Results" below |

### Dry run (before step 4)

Before the official tools were added, `retrieval-agent` was asked to ingest
"all Agents in namespace kagent, with system prompt and metadata, into
vectors and graph". Result:

- Qdrant `abox-nomic`: 2 points, not 7. One is a summary list of all agents
  in one document, the other is `k8s-agent` on its own with its prompt.
- Neo4j: 7 `Agent` nodes with correct `kagent/<name>` keys, 1 `ModelConfig`,
  1 `RemoteMCPServer`, but only 2 edges (`USES_MODEL`, `USES_TOOL`), both
  from `k8s-agent`. The other six agents are nodes without relationships.

The agent asked `k8s-agent` for a list instead of per-object YAML, so only
one object was ingested in depth. Two rules for the real runs follow from
this: the ingest request names the objects explicitly and asks for one
vector document per object, and both stores are emptied before each run
(`abox-*` collection deleted, Neo4j cleared with `MATCH (n) DETACH DELETE n`).

## Comparison method

To be run in steps 6-8 of the lab.

- Corpus: the declared objects `retrieval-agent` already ingests (kagent Agent,
  ModelConfig, MCPServer, RemoteMCPServer, HelmRelease, Gateway, HTTPRoute).
- Index A: `retrieval-agent` with `vector_store`/`vector_find` -> `abox-nomic`.
- Index B: `retrieval-agent` with `qdrant-store`/`qdrant-find` -> `abox-minilm`.
- The same fixed list of questions is asked against each index. Each answer is
  scored on: did the right object come back (hit@k), was the answer grounded
  in the retrieved text, and how many tool calls it took.
- Operational numbers recorded alongside: pod memory at rest and during
  ingest, time to first result after a pod restart, size of each collection.

## Consequences

- Two vector spaces coexist in Qdrant. Anything that reads `abox-*` must know
  which model produced it; the collection name encodes that.
- The official server keeps the model in the MCP pod. That removes the
  dependency on the llama.cpp route for retrieval, at the cost of a Python
  process with onnxruntime resident per replica.
- The in-house server keeps embedding on the shared inference path, so the
  vectors match what the gateway serves and the MCP pod stays at tens of MiB.
- Tool names differ, so the agent's system prompt must name the tools of the
  set it is given. Step 5 rewrites the prompt for the official set.

## Results

_Pending. To be filled in step 8._

### Ingest

| | `abox-nomic` | `abox-minilm` |
|---|---|---|
| Objects ingested | | |
| Points in collection | | |
| Wall time | | |
| MCP pod peak memory | | |

### Retrieval

| Question | Expected object | A: nomic hit / grounded / calls | B: MiniLM hit / grounded / calls |
|---|---|---|---|
| | | | |

### Verdict

_Which tool set `retrieval-agent` should ship with, and why._
