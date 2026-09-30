# Comparison: in-house qdrant-mcp (A) vs. the official mcp-server-qdrant (B)

One agent, `retrieval-agent`; one model, `gemini-3.1-flash-lite`; one corpus of 14 kagent objects; two sets of vector tools. Details of each run: `qdrant-den.md` (A) and `qdrant-official.md` (B). Chronology and working commands: `logs.md`. The decision record for the reviewer: `ADR-001-agentic-retrieval-qdrant-mcp.md`. Questions and answers side by side: `table.md`.

## Ingest request

Identical for both runs, differing only in the tool name:

```
Ingest these objects, one at a time: every kagent.dev Agent, ModelConfig,
MCPServer and RemoteMCPServer in namespace kagent. For each object ask
k8s-agent for its full YAML, write it to the graph, then store one
<vector_store | qdrant-store> entry for it. When done, list every key you ingested.
```

The agent prompt in both runs asks for the same thing: one entry per object, no raw YAML, a 2-4 sentence description, kind, namespace, name and key in metadata; graph first (`write-cypher`, MERGE on `key`), then the vector.

## Questions

9 questions, 2 per type plus a negative one. Each in a new chat with retrieval-agent, identical in both runs. Expected answers are for the full corpus of 14 objects.

| # | Type | What it tests | Question | Expected answer |
|---|---|---|---|---|
| D1 | direct | keywords present in the description | Which MCP server connects to Neo4j? | neo4j-mcp; competitors qdrant-mcp and qdrant-mcp-official |
| D2 | direct | same | Which model config uses OpenAI gpt-4.1-mini? | default-model-config |
| P1 | paraphrased | keywords absent from the description | My pod keeps crashing, which agent can troubleshoot it? | k8s-agent; the description says only "troubleshooting", competitors are 6 other agents |
| P2 | paraphrased | same | Which component hands out service-mesh and network-policy tooling? | kagent-tool-server; in the description this is "Cilium" and "Istio" |
| L1 | detail late in the text | whether the agent carries a last-sentence detail into the answer | Which Kubernetes secret and key hold the API key for the default model config? | kagent-openai, OPENAI_API_KEY; if the detail is not in the description, the honest answer is "not found" |
| L2 | detail late in the text | same | At which HTTP endpoint is the kagent tool server reachable? | http://kagent-tools.kagent:8084/mcp; or "not found" |
| H1 | hybrid | vector + graph | Which tool server does the Kubernetes expert agent use, and what does it expose? | kagent-tool-server via USES_TOOL; Kubernetes, Cilium, Istio, Helm, Kubescape, Prometheus |
| H2 | hybrid | vector, then graph on incoming edges | Which agents depend on the tool server that provides Helm and Prometheus tooling? | 5 agents: argo-rollouts-conversion-agent, helm-agent, k8s-agent, kgateway-agent, observability-agent |
| N1 | negative | whether it invents | Which agent uses Anthropic Claude? | none |

**Recorded per question:** tool calls, rank of the expected object among the 5 vector search results, gap to the runner-up, answer score (2 correct, 1 partial, 0 wrong), whether the answer rests on the stores, whether any fact is invented.

**Caveat on type L.** The vectors hold 2-4 sentence descriptions, not manifests. "Late" here means the last sentence, about 50 tokens in, within MiniLM's 128-token window. This type tests whether the agent carries a detail into the answer, not text truncation.

## Two configurations

| | A: in-house `qdrant-mcp` | B: `qdrant-mcp-official` |
|---|---|---|
| Source | `mcp/qdrant-mcp/`, Go, `ghcr.io/den-vasyliev/abox/qdrant-mcp:0.4.0` | PyPI `mcp-server-qdrant==0.8.1`, image built locally from `lab4/Dockerfile` |
| Tools | `vector_store`, `vector_find` | `qdrant-store`, `qdrant-find` |
| Embeddings | `nomic-embed-text-v1.5` via llama.cpp `/v1/embeddings`, out of the pod | `all-MiniLM-L6-v2` via fastembed, in the pod |
| Dimensions | 768 | 384 |
| Collection | `abox-nomic` | `abox-minilm` |
| Long text | chunks at 7000 characters, embeds everything | first 128 tokens only |
| Score in results | yes | no, computed with `score-minilm.py` |
| Agent file | `retrieval-agent-mcp-llmcpp.yaml` | `retrieval-agent-mcp-official.yaml` |

The prompts differ only in tool names and one sentence about the `<entry>` format in B. Both agents, retrieval-agent and k8s-agent, run on `gemini-gemini-3-1-flash-lite` in both runs and are taken out of Flux with the `reconcile=disabled` annotation.

## Ingest

| | A | B |
|---|---|---|
| Objects | 14: 7 Agent, 2 ModelConfig, 3 MCPServer, 2 RemoteMCPServer | 14, same set |
| Points in the collection | 14, one per object | 14, one per object, no duplicates |
| Nodes in Neo4j | 14 | 14 |
| `USES_MODEL` | 7 | 7, one wrong (retrieval-agent → default-model-config) |
| `USES_TOOL` | 10 | 6: missing 3 edges of retrieval-agent and observability-agent → promql-agent |
| Time | not recorded | about 1 min 45 s |
| MCP pod peak memory | 42 MiB over the pod's lifetime | 517 MiB, 276 MiB before ingest |
| `key` in metadata | no | yes |
| Description style | field list | prose |

**The corpora are not identical.** Descriptions are generated by the model on every ingest, and they came out different. Run A's are more detailed:

| Detail | A | B |
|---|---|---|
| kagent-tool-server: Cilium, Istio, Prometheus | present | absent, only "Kubernetes, Helm, and operational tools" |
| kagent-tool-server: URL | absent | absent |
| default-model-config: secret `kagent-openai` | present | absent |
| default-model-config: key `OPENAI_API_KEY` | absent | absent |
| neo4j-mcp: image and bolt URI | present | absent |
| k8s-agent: "Kubernetes expert" | absent, has "troubleshooting" | present |

Because of this, P2, H2, L1 and L2 in B depend on details the descriptions lack. The graph errors in B arose because k8s-agent, asked about retrieval-agent, returned a summary instead of YAML; they barely affected the questions, since all 5 edges to kagent-tool-server are in place.

## Answers

Rank: position of the expected object among the 5 vector search results. Gap: score difference between rank 1 and rank 2 (negative if the expected object is not first). Absolute nomic and MiniLM scores are not comparable, they are different scales. Grounded: whether the answer was taken from the stores.

| # | A: rank / gap | A: score / grounded / calls | B: rank / gap | B: score / grounded / calls |
|---|---|---|---|---|
| D1 | 1 / 0.13 | 2 / yes / 2 | 1 / 0.28 | 2 / yes / 1 |
| D2 | graph only | 2 / yes / 2 | 1 / 0.28 | 2 / yes / 1 |
| P1 | 1 / 0.03 | 2 / yes / 4 | 1 / 0.045 | 2 / yes / 1 |
| P2 | 2 / -0.006 | 2 / yes / 2 | 1 / 0.002 | 2 / partial: no service mesh in the text / 2 |
| L1 | 1 / 0.12 | 2 / partial: key from the cluster / 4 | 1 / 0.25 | 2 / no: secret and key from the cluster / 2 |
| L2 | 1 / 0.06 | 2 / no: URL from the cluster / 3 | 1 / 0.09 | 2 / no: URL from the cluster / 2 |
| H1 | 1 / 0.06 | 2 / yes / 3 | 1 / 0.02 | 1 / yes, but the text lists only Kubernetes and Helm / 2 |
| H2 | 2 / -0.03 | 2 / yes / 3 | 3 / -0.04 | 2 / partial: no Prometheus in the text / 2 |
| N1 | n/a | 2 / yes / 4 | n/a | 2 / yes / 3 |

Where the agent went to the live cluster via k8s-agent:

| | A | B |
|---|---|---|
| Call with no effect on the answer | P1 ("get pods") | |
| Decisive fact from the cluster | L1 (key), L2 (URL) | L1 (secret and key), L2 (URL) |

## Summary

| | A: nomic, in-house MCP | B: MiniLM, official |
|---|---|---|
| Score sum | 18 of 18 | 17 of 18 |
| Expected object at rank 1, questions with vector search | 5 of 7 | 7 of 8 |
| Answer fully from the stores | 7 of 9 | 5 of 9 |
| Delegated to k8s-agent | P1, L1, L2 | L1, L2 |
| Tool calls, total | 27 | 16 |
| `get-schema` before answering | every question | none |
| MCP pod peak memory | 42 MiB | 517 MiB |

What follows:

1. **Answer quality is the same.** The single point B lost (H1) and all its answers without support in the text (P2, H2, L1) are explained by thin descriptions from ingest. Those descriptions are written by the agent's model, not the embedding model. The questions did not separate nomic from MiniLM on answer quality.
2. **By rank, MiniLM comes out slightly ahead, but the corpora differ.** Expected object at rank 1: B 7 of 8, A 5 of 7; MRR 0.92 against 0.86. Raw score gaps (0.25-0.28 against 0.12-0.13 on direct questions) are not comparable: the two models use different score scales, and normalised by the spread of the top 5 the gaps agree on D1, P1 and L1. Both of A's misses (P2, H2) are behind helm-agent, whose run A description carries "Tools: kagent-tool-server" and Helm, so the agent's document outranks the server's own. That is a property of what the model wrote at ingest, and the descriptions in the two runs differ, so the rank advantage cannot be attributed to MiniLM. On paraphrased questions both models are weak (P1: 0.045 and 0.03). On 14 short documents this changed no answer.
3. **The corpus matters more than the embedding model.** The difference between the runs comes from what the model wrote into the description, not from how that description was embedded.
4. **Gemini does not hold to the prompt rules.** In both runs the agent fetched missing facts from the live cluster despite the rule "do not fetch manifests, do not delegate to another agent". In B it also never called `get-schema`. The grounding numbers measure the model as much as the tools.
5. **Cost favours A.** 42 MiB against 517 MiB per replica; B runs on a local image that disappears after a Codespace restart; A uses the embeddings route the gateway already serves. A chunks long text, B sees 128 tokens.

## Decision

**Keep the in-house `qdrant-mcp`** as retrieval-agent's vector tool set. The official `qdrant-mcp-official` is not deployed. Accepted 2026-09-27, ADR status Accepted.

## Limits and next steps

- One run per tool set, 14 objects, 9 questions. A one-question difference is within noise.
- The corpora are not identical: descriptions differ, and B's graph has errors.
- To compare the embedding models themselves: index the same fixed texts through both servers, so that only the vectors differ.
- To measure the stores alone: remove k8s-agent from retrieval-agent's tools during questions, or split ingest and search into two agents.
