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
а що визиває або які інструменти використовуються в обзервабіліті - це граф а потім вектор 
-->

Flux Kustomization releases controll. every 2 min kustomize-controller does server-side apply...and refresh to default state that is in spec
workaround:
kubectl annotate agent k8s-agent -n kagent kustomize.toolkit.fluxcd.io/reconcile=disabled --overwrite
kubectl -n kagent annotate agent retrieval-agent kustomize.toolkit.fluxcd.io/reconcile=disabled --overwrite
kubectl -n kagent annotate agent promql-agent kustomize.toolkit.fluxcd.io/reconcile=disabled --overwrite