<!-- 
1. Розгорнутися з релізу feat/llmd-embeddings 
2. Додати офіційний qdrant MCP https://github.com/qdrant/mcp-server-qdrant 
3. Налаштувати модель для retrivial-agent та k8s-agent
4. Додати інструменти офіційного qdrant MCP
5. Налаштувати системний промпт для використання офіційного qdrant MCP
6. Проіндексувати будь-які дані (наприклад k8s маніфести) з sentence-transformers/all-MiniLM-L6-v2
7. Проіндексувати ті ж самі дані з дефолтним qdrant MCP (змініть тулсет)
8. Порівняти та оцінити якість Agentic Retrieval і додати результати до ADR 

retrival 
якщо я питаю що там в системному промті агента обзервабіліті - це вектор 
що визиває або які інструменти використовуються в обзервабіліті - це граф а потім вектор 
-->

# TODO:

1. deploy abox project from feat/llmd-embeddings  branch
2. Flux functionality:
Flux Kustomization releases controll. every 2 min kustomize-controller does server-side apply...and refresh to default state that is in spec
workaround:
```kubectl annotate agent k8s-agent -n kagent kustomize.toolkit.fluxcd.io/reconcile=disabled --overwrite
kubectl -n kagent annotate agent retrieval-agent kustomize.toolkit.fluxcd.io/reconcile=disabled --overwrite
kubectl -n kagent annotate agent promql-agent kustomize.toolkit.fluxcd.io/reconcile=disabled --overwrite
```
3. Configure AI model for  retrivial-agent та k8s-agent 
4. Build and push official mcp-server-qdrant  з all-MiniLM-L6-v2 моделью та підняти 
```
docker build -t mcp-server-qdrant:local lab4/
kind load docker-image mcp-server-qdrant:local --name abox
```
5. retrivial-agent + qdrant MCP fixed(den)
 5.1. ingest data
 5.2. Ask question. dont forget a new chat

6. configure retrivial-agent використовувати офіційний qdrant MCP
  6.1. Ingest data
  6.2. Ask question. dont forget a new chat

7. Compare result

8. neo4j
- forward port for 2 ports in cli
```
kubectl port-forward -n neo4j svc/neo4j 7474:7474 7687:7687 --address 0.0.0.0

- bolt port switch to public
gh codespace ports visibility 7687:public -c obscure-memory-v65r5vjr4g43p6j4
Open in browser
https://obscure-memory-v65r5vjr4g43p6j4-7474.app.github.dev/browser/

Login:
bolt+s://
Connect URL	obscure-memory-v65r5vjr4g43p6j4-7687.app.github.dev:443
Username / Password	neo4j / abox-neo4j
```

## prase for ingest for both retrivial-agent types
```
Ingest these objects, one at a time: every kagent.dev Agent, ModelConfig, MCPServer and RemoteMCPServer in namespace kagent. For each object ask k8s-agent for its full YAML, write it to the graph, then store one qdrant-store entry for it. When done, list every key you ingested.
```


## Questions
| # | Тип | Що перевіряє | Питання | Очікувана відповідь |
|---|---|---|---|---|
| D1 | прямий | ключові слова є в описі | Which MCP server connects to Neo4j? | neo4j-mcp; конкуренти qdrant-mcp і qdrant-mcp-official |
| D2 | прямий | те саме | Which model config uses OpenAI gpt-4.1-mini? | default-model-config |
| P1 | перефразований | ключових слів у описі немає | My pod keeps crashing, which agent can troubleshoot it? | k8s-agent; в описі лише «troubleshooting», конкуренти 6 інших агентів |
| P2 | перефразований | те саме | Which component hands out service-mesh and network-policy tooling? | kagent-tool-server; в описі це «Cilium» та «Istio» |
| L1 | деталь у глибині тексту | чи доносить агент деталь з останнього речення | Which Kubernetes secret and key hold the API key for the default model config? | kagent-openai, OPENAI_API_KEY; якщо деталі в описі немає, чесна відповідь «не знайдено» |
| L2 | деталь у глибині тексту | те саме | At which HTTP endpoint is the kagent tool server reachable? | http://kagent-tools.kagent:8084/mcp; або «не знайдено» |
| H1 | гібридний | вектор + граф | Which tool server does the Kubernetes expert agent use, and what does it expose? | kagent-tool-server через USES_TOOL; Kubernetes, Cilium, Istio, Helm, Kubescape, Prometheus |
| H2 | гібридний | вектор, потім граф по вхідних ребрах | Which agents depend on the tool server that provides Helm and Prometheus tooling? | 5 агентів: argo-rollouts-conversion-agent, helm-agent, k8s-agent, kgateway-agent, observability-agent |
| N1 | негативний | чи не вигадує | Which agent uses Anthropic Claude? | жодного |
