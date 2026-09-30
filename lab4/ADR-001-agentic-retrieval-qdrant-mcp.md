# ADR-001: Vector tool set for retrieval-agent: in-house qdrant-mcp over the official mcp-server-qdrant

- Status: Accepted 2026-09-27; reasoning revised 2026-09-30 after a re-analysis of the recorded runs (see "Findings"). The decision did not change.
- Date: 2026-09-24
- Branch: `feat/llmd-embeddings`, cluster bootstrapped from the `releases-llmd-embeddings` artifact
- Data: `qdrant-den.md` (run A), `qdrant-official.md` (run B), `table.md` (questions and answers side by side), `summary.md` (Ukrainian comparison), `logs.md` (chronology and commands)

## Context

`retrieval-agent` in kagent ingests cluster manifests into two stores: a Neo4j graph through `neo4j-mcp` and Qdrant vectors. Its vector tools come from the in-house `qdrant-mcp` (Go, `mcp/qdrant-mcp/`), which embeds through the llama.cpp `/v1/embeddings` route with `nomic-embed-text-v1.5` (768 dims) into the collection `abox-nomic`. `releases/mcp-servers.yaml` records that this server replaced the official `mcp-server-qdrant`, which embedded in-process with fastembed and was OOMKilled doing it.

The lab task: deploy from the `feat/llmd-embeddings` release, add the official Qdrant MCP server ([qdrant/mcp-server-qdrant](https://github.com/qdrant/mcp-server-qdrant)) next to the in-house one, give `retrieval-agent` its tools and a system prompt for them, index the same data through both servers, and compare the quality of agentic retrieval.

The question this ADR answers: **which of the two tool sets `retrieval-agent` should use.**

### Candidates

| | A: in-house `qdrant-mcp` 0.4.0 | B: `mcp-server-qdrant` 0.8.1 |
|---|---|---|
| Source | `mcp/qdrant-mcp/`, Go, `ghcr.io/den-vasyliev/abox/qdrant-mcp:0.4.0` | PyPI `mcp-server-qdrant==0.8.1`, image built from `lab4/Dockerfile` |
| Tools | `vector_store`, `vector_find` | `qdrant-store`, `qdrant-find` |
| Embedding | `nomic-embed-text-v1.5`, 768 dims, out of process via llama.cpp | `all-MiniLM-L6-v2`, 384 dims, in process via fastembed |
| Collection | `abox-nomic` | `abox-minilm` |
| Long text | chunks input over 7000 characters, embeds everything | embeds the first 128 tokens, silently drops the rest |
| Score in results | yes | no, order only |
| Image | published in GHCR | upstream publishes no image; built locally, wiped by a Codespace restart |
| Resources in manifest | requests 32Mi, limits 256Mi | requests 512Mi, limits 2Gi |
| External dependency | the llama.cpp route must be up | Qdrant only |
| Transport | stdio, adapted by kmcp | stdio, adapted by kmcp |

Environment: a 4-core / 15 GB Codespace hosting three kind nodes. Anything that adds hundreds of MiB per replica competes with llama.cpp, llm-d, Neo4j and kagent for the same memory.

## Progress

| # | Task | Status | Where |
|---|---|---|---|
| 1 | Deploy from the `feat/llmd-embeddings` release | done | cluster reconciles `releases-llmd-embeddings` |
| 2 | Add the official Qdrant MCP server | done | `lab4/qdrant-mcp-official.yaml`, `lab4/Dockerfile`; kagent lists `qdrant-find`, `qdrant-store`; a store/find round-trip created `abox-minilm` (384 dims, Cosine) |
| 3 | Set the model for both agents | done | `gemini-gemini-3-1-flash-lite` for `retrieval-agent` and `k8s-agent`; both annotated `reconcile=disabled` |
| 4 | Give `retrieval-agent` the official server's tools | done | `lab4/retrieval-agent-mcp-official.yaml`; the in-house `qdrant-mcp` block removed from tools for run B so one Qdrant server is present per run |
| 5 | System prompt for the official tools | done | same file; validated with a server-side dry run and against the upstream v0.8.1 source |
| 6 | Index the manifests with `all-MiniLM-L6-v2` | done | `abox-minilm`, 14 objects; 9 questions, run B |
| 7 | Index the same manifests with the in-house tool set | done | `abox-nomic`, 14 objects; 9 questions, run A |
| 8 | Compare, score, record | done | "Results" and "Findings" below |

## Dry run (before step 4)

Before the official tools were added, `retrieval-agent` was asked to ingest "all Agents in namespace kagent, with system prompt and metadata, into vectors and graph". Result: 2 points in `abox-nomic` instead of 7 (one summary list of all agents, one for `k8s-agent`); 7 `Agent` nodes in Neo4j but only 2 edges, both from `k8s-agent`. The agent asked `k8s-agent` for a list instead of per-object YAML. Two rules for the real runs follow: the ingest request names the object kinds explicitly and asks for one vector document per object, and both stores are emptied before each run (`abox-*` collection deleted, Neo4j cleared with `MATCH (n) DETACH DELETE n`).

## Comparison method

One agent, one model, one ingest request, 14 kagent objects (7 Agent, 2 ModelConfig, 3 MCPServer, 2 RemoteMCPServer), one collection per server. The request differs only in the tool name:

```
Ingest these objects, one at a time: every kagent.dev Agent, ModelConfig,
MCPServer and RemoteMCPServer in namespace kagent. For each object ask
k8s-agent for its full YAML, write it to the graph, then store one
<vector_store | qdrant-store> entry for it. When done, list every key you ingested.
```

The two system prompts (`lab4/retrieval-agent-mcp-llmcpp.yaml`, `lab4/retrieval-agent-mcp-official.yaml`) differ only in the tool names and one sentence about the official server's `<entry>` result format, verified with `diff`.

9 questions, each in a new chat session, never in the ingest session: 2 direct (D, keywords present in the description), 2 paraphrased (P, keywords absent), 2 detail-late-in-text (L), 2 hybrid vector + graph (H), 1 negative (N). Recorded per question: tool calls, rank of the expected object among 5 vector results, its score, the gap to the runner-up, a hand-assigned score (2 correct, 1 partial, 0 wrong), whether the answer was grounded in the stores, and whether anything was invented.

Scores for run B were computed with `lab4/score-minilm.py` inside the MCP pod, because `qdrant-find` returns order only; the order matched the server's. Absolute nomic and MiniLM scores are different scales and are not compared directly.

Answers recorded earlier were discarded: run B's first attempt covered 4 objects (MCP pod peak about 1246 MiB), and run A's first answers were asked in the ingest session, where the model had every manifest in context.

## Results

The Codespace was restarted between runs (2026-09-27), so run A ingests into empty stores and the official image, the Gemini ModelConfig and the agent edits were re-applied by hand.

### Ingest

| | A: `abox-nomic` | B: `abox-minilm` |
|---|---|---|
| Objects | 14 | 14, same set |
| Points | 14, one per object, no chunking | 14, one per object, no duplicates |
| Graph | 14 nodes; 7 `USES_MODEL`, 10 `USES_TOOL` | 14 nodes; 7 `USES_MODEL` (1 wrong), 6 `USES_TOOL` (4 missing) |
| Wall time | not recorded | about 1 min 45 s (14:11:42-14:13:27 UTC, from the session API) |
| MCP pod peak memory | 42 MiB over the pod's lifetime, ingest and questions included | 517 MiB after ingest; 276 MiB before |
| `key` in metadata | no, although the prompt asks for it | yes |
| Description style | field lists ("Configuration: Declarative. Model: ... Tools: ...") | prose |

The two corpora are not identical. Descriptions are written by the agent's LLM on each ingest, and they came out different:

| Detail | A | B |
|---|---|---|
| kagent-tool-server: Cilium, Istio, Prometheus | present | absent, only "Kubernetes, Helm, and operational tools" |
| kagent-tool-server: URL | absent | absent |
| default-model-config: secret `kagent-openai` | present | absent |
| default-model-config: key `OPENAI_API_KEY` | absent | absent |
| neo4j-mcp: image and bolt URI | present | absent |
| k8s-agent: "Kubernetes expert" | absent ("troubleshooting" only) | present |

In run B, `k8s-agent` returned a prose summary instead of YAML for `retrieval-agent`; the agent then wrote a wrong `USES_MODEL` edge to `default-model-config` and none of its 3 `USES_TOOL` edges, and the `observability-agent -> promql-agent` edge is also missing. P2, H2, L1 and L2 depend on details that run B's descriptions lack.

### Retrieval

Rank is the position of the expected object among the 5 vector results; gap is score of rank 1 minus rank 2 (negative when the expected object is not first); score is 2 correct, 1 partial, 0 wrong. Full answers and tool lists are in `table.md`.

| # | Type | Question | Expected | A: rank / gap / score / grounded / calls | B: rank / gap / score / grounded / calls |
|---|---|---|---|---|---|
| D1 | direct | Which MCP server connects to Neo4j? | neo4j-mcp | 1 / 0.13 / 2 / yes / 2 | 1 / 0.28 / 2 / yes / 1 |
| D2 | direct | Which model config uses OpenAI gpt-4.1-mini? | default-model-config | graph only / n/a / 2 / yes / 2 | 1 / 0.28 / 2 / yes / 1 |
| P1 | paraphrased | My pod keeps crashing, which agent can troubleshoot it? | k8s-agent | 1 / 0.03 / 2 / yes / 4 | 1 / 0.045 / 2 / yes / 1 |
| P2 | paraphrased | Which component hands out service-mesh and network-policy tooling? | kagent-tool-server | 2 / -0.006 / 2 / yes / 2 | 1 / 0.002 / 2 / partial: no service mesh in the text / 2 |
| L1 | detail late | Which Kubernetes secret and key hold the API key for the default model config? | kagent-openai, OPENAI_API_KEY | 1 / 0.12 / 2 / partial: key from a live read / 4 | 1 / 0.25 / 2 / no: secret and key from a live read / 2 |
| L2 | detail late | At which HTTP endpoint is the kagent tool server reachable? | http://kagent-tools.kagent:8084/mcp | 1 / 0.06 / 2 / no: URL from a live read / 3 | 1 / 0.09 / 2 / no: URL from a live read / 2 |
| H1 | hybrid | Which tool server does the Kubernetes expert agent use, and what does it expose? | kagent-tool-server; Kubernetes, Cilium, Istio, Helm, Kubescape, Prometheus | 1 / 0.06 / 2 / yes / 3 | 1 / 0.02 / 1 / yes, text lists only Kubernetes and Helm / 2 |
| H2 | hybrid | Which agents depend on the tool server that provides Helm and Prometheus tooling? | 5 agents | 2 / -0.03 / 2 / yes / 3 | 3 / -0.04 / 2 / partial: no Prometheus in the text / 2 |
| N1 | negative | Which agent uses Anthropic Claude? | none | n/a / 2 / yes / 4 | n/a / 2 / yes / 3 |

| | A | B |
|---|---|---|
| Score, sum over 9 questions | 18 / 18 | 17 / 18 |
| Expected object at rank 1, questions that used vector search | 5 / 7 | 7 / 8 |
| Answer fully grounded in the stores | 7 / 9 | 5 / 9 |
| Delegated to `k8s-agent` | P1, L1, L2 | L1, L2 |
| `get-schema` before answering | every question | never |
| Tool calls, all questions | 27 | 16 |
| MCP pod peak memory | 42 MiB | 517 MiB |

## Findings

### 1. Answer quality is a tie

The one point B lost (H1) and both of its answers without support in the text (P2, H2) trace to a single cause: its ingest descriptions omit Cilium, Istio, Prometheus and the model config's secret. Those descriptions were written by the agent's LLM, not by the embedding model. In run A the same object, kagent-tool-server, was described in full and answered H1 completely. **17 against 18 is a corpus difference, not a server difference.**

### 2. By rank MiniLM is slightly ahead; the corpora differ, so this is not a model result

Order-based metrics, which do not depend on the score scale, favour B slightly: expected object at rank 1 in 7 of 8 questions against 5 of 7, MRR 0.92 against 0.86. Both of A's misses (P2, H2) are behind helm-agent. Run A's descriptions are field lists, and every agent carries the line "Tools: kagent-tool-server (RemoteMCPServer)", so an agent's document that mentions both Helm and the tool server's name outranks the tool server's own document, where a list of seven tools dilutes each one. Run B's prose descriptions do not have this line. The rank difference therefore follows the descriptions, which differ between runs, and cannot be attributed to the embedding model.

The earlier version of this ADR claimed MiniLM separates direct questions better, based on raw gaps of 0.25-0.28 against 0.12-0.13 for nomic. But nomic compresses all cosine scores into a 0.5-0.8 band while MiniLM spreads them over 0.25-0.65, so a raw nomic gap is always smaller. Dividing the gap by the spread of the top 5 (rank 1 minus rank 5) gives:

| # | A: gap / spread / share | B: gap / spread / share |
|---|---|---|
| D1 | 0.133 / 0.156 / **0.85** | 0.282 / 0.366 / **0.77** |
| D2 | graph, n/a | 0.279 / 0.403 / 0.69 |
| P1 | 0.031 / 0.061 / **0.51** | 0.045 / 0.093 / **0.48** |
| P2 | -0.006 (rank 2) | 0.002 / 0.025 / 0.08 |
| L1 | 0.116 / 0.129 / **0.90** | 0.248 / 0.274 / **0.91** |
| L2 | 0.058 / 0.101 / 0.57 | 0.087 / 0.113 / 0.77 |
| H1 | 0.056 / 0.096 / 0.58 | 0.019 / 0.171 / 0.11 |
| H2 | -0.030 (rank 2) | -0.017 (rank 3) |

On D1, P1 and L1 the shares agree to within a few hundredths. L2 favours B, H1 favours A (in B the runner-up is k8s-agent, which the question also names, so that is not a miss). **Neither the rank edge nor the raw gaps can be attributed to an embedding model on this corpus.** Both are equally confident on direct questions and equally weak on paraphrases: on P2 both spread five results over 0.025-0.035, meaning neither saw anything about the question in the descriptions, and the agent's LLM picked the right answer by reading the content, not by rank.

### 3. Grounding measures the agent's model, not the server

In both runs the agent broke the prompt rule "Do not fetch manifests, do not delegate to another agent": on L1 and L2 the decisive fact (the secret's key, the server URL) came from the live cluster via `k8s-agent`. Run A also made a stray "get pods" call on P1. The honest answer from the stores on L2 would have been "not found" in both runs. So 7/9 against 5/9 reflects partly the corpus (P2, H2 in B) and partly identical model behaviour (L1, L2 in both).

Model behaviour also differed between runs with no visible cause in the prompt: A called `get-schema` on all 9 questions, B on none; A made 27 calls, B 16; A did not write `key` into metadata although the prompt asks for it, B did. The prompts differ by two tool names and one sentence. This is the noise level of a single run on `gemini-3.1-flash-lite`, and differences of this size between A and B cannot be read as properties of the servers.

### 4. Operational numbers differ by an order of magnitude and do not depend on the corpus

| | A | B |
|---|---|---|
| MCP pod peak memory | 42 MiB over the whole lifetime, ingest included | 517 MiB after ingest, 276 MiB idle, 1246 MiB on the first attempt |
| Memory request in the manifest | 32Mi | 512Mi |
| Image | `ghcr.io/den-vasyliev/abox/qdrant-mcp:0.4.0` | `mcp-server-qdrant:local`, rebuilt and `kind load`ed after every Codespace restart |
| Score in the tool result | yes | no; evaluation needed a separate script |
| Text beyond 128 tokens | embedded in full | silently truncated |

The 1246 MiB peak on B's first attempt is the regime in which the official server was OOMKilled before, which is why the in-house server exists. Truncation at 128 tokens did not bite here only because the prompt forces 2-4 sentence descriptions; for raw manifests B is unusable.

The downside of A: it is coupled to the llama.cpp route. If the embeddings pod is down, `vector_store` and `vector_find` fail, whereas B depends on Qdrant alone.

## Options considered

1. **Keep the in-house `qdrant-mcp`** (A). Chosen.
2. **Switch to the official `mcp-server-qdrant` with MiniLM** (B). Same answer quality, but 12x the memory per replica, a locally built image, silent truncation of long text, no scores. Rejected.
3. **Official server with a larger fastembed model.** Would remove the 128-token limit and the 384 dims, but keeps the model in the pod with even more memory and keeps the local image. Not tested.
4. **Run both servers side by side.** Two vector spaces, double ingest, the agent has to choose a tool. Rejected: adds complexity and nothing A does not already give.

## Decision

`retrieval-agent` keeps the in-house `qdrant-mcp` (`vector_store` / `vector_find`, nomic via llama.cpp, collection `abox-nomic`) as its vector tool set. `qdrant-mcp-official` does not go into `releases/`. Everything in `lab4/` stays lab material and is not reconciled by Flux.

The decision rests on operational grounds. The retrieval comparison did not contradict them, but it also did not show an advantage for either embedding model: on 14 short documents and 9 questions nomic and MiniLM are indistinguishable.

## Consequences

`retrieval-agent` keeps `vector_store` / `vector_find`. The choice rests on operating cost; the measurement showed only that retrieval quality does not argue against it, not that nomic is better.

Retrieval quality is bounded by what the agent writes at ingest, not by the embedding model. Every lost point and every ungrounded answer traced to a description the LLM left thin. Prompt work is created: the lab's ingest step (one entry per object, no raw YAML, a 2-4 sentence description, `key` in metadata) goes into `releases/agent-retrieval.yaml`. The sentence "Only the beginning of the text is embedded" does not, because it is false for this server.

The grounding rule remains an instruction and therefore remains a risk. "Do not delegate to another agent" was broken in both runs on the same two questions, and nothing enforces it. The only enforcement available is taking `k8s-agent` out of the agent's tools at question time, and that is a separate decision.

Vector retrieval is coupled to the llama.cpp route. When the embeddings pod is down, both vector tools fail while the graph still answers. This is accepted; the alternative was an in-pod model at ten times the memory.

The two embedding models remain uncompared. Separating them needs fixed description texts, no cluster access at question time, and more than one run. Until then a claim about nomic against MiniLM has to be measured, not inherited from this ADR.

## Limits of this comparison

- One run per tool set, 14 objects, 9 questions, hand scoring by one judge. A one-point difference is within noise.
- The corpora differ: descriptions were LLM-generated, and run B's graph lost 4 `USES_TOOL` edges and gained one wrong `USES_MODEL` edge because `k8s-agent` returned a summary instead of YAML.
- D2 in run A was answered from the graph, so vector search was not exercised there. The L type does not test truncation: the "late" detail is the third or fourth sentence, within 128 tokens.
- Ingest wall time was measured only for B.

## If the embedding models are to be compared on their own

- Fix the description texts in a file and index them through both servers, so only the vectors differ.
- Remove `k8s-agent` from `retrieval-agent`'s tools during questions, or split ingest and retrieval into two agents, so answers can only come from the stores.
- Three or more runs per configuration, a larger corpus (add the HelmRelease, Gateway and HTTPRoute objects the agent is meant to ingest anyway), and questions whose answer lives only in the second half of a long text.
- Compare gap as a share of the top-5 spread, not the raw gap.
