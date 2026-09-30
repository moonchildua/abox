# Прогін B: офіційний mcp-server-qdrant (MiniLM через fastembed)

Записи цього прогону, зібрані з `logs.md`. Хронологія, спільні для обох прогонів речі (вибір моделі агентів, доступ до UI, команди) лишаються в `logs.md`. Порівняння з прогоном A у `summary.md`.

## Конфігурація

| | |
|---|---|
| MCPServer | `qdrant-mcp-official`, образ `mcp-server-qdrant:local` з `lab4/Dockerfile`, пакет PyPI `mcp-server-qdrant==0.8.1` |
| Тули | `qdrant-store`, `qdrant-find` |
| Ембединги | `sentence-transformers/all-MiniLM-L6-v2` у поді через fastembed, 384 виміри |
| Колекція | `abox-minilm`, Cosine, `QDRANT_SEARCH_LIMIT=5` |
| Довгий текст | MiniLM бачить лише перші 128 токенів, решту обрізає; шматків сервер не робить |
| Score | `qdrant-find` повертає лише порядок, без score; score рахуємо окремо скриптом `lab4/score-minilm.py` |
| Файли | `lab4/qdrant-mcp-official.yaml` (MCPServer), `lab4/retrieval-agent-mcp-official.yaml` (агент) |
| Модель агентів | `gemini-gemini-3-1-flash-lite` (Gemini `gemini-3.1-flash-lite`) для retrieval-agent і k8s-agent |
| Пік пам'яті пода MCP | 517 MiB після інгесту; 276 MiB до інгесту |

## Розгортання (пункт 2 лабораторної)

**Проблема:** офіційний проєкт не публікує Docker-образ, лише PyPI-пакет і Dockerfile.

**Що зроблено:**

- `lab4/Dockerfile` зібрано на основі апстрімного Dockerfile. Відмінності: версія пакета запінена на 0.8.1, а модель MiniLM скачується під час збірки в `/models`, тож под стартує без доступу до HuggingFace.
- Образ зібрано й завантажено в усі ноди kind:
  ```bash
  docker build -t mcp-server-qdrant:local lab4/
  kind load docker-image mcp-server-qdrant:local --name abox
  ```
- `lab4/qdrant-mcp-official.yaml` описує MCPServer `qdrant-mcp-official`: stdio, колекція `abox-minilm`, `QDRANT_SEARCH_LIMIT=5`. Застосовано через `kubectl apply`.

**Перевірка:**

- kagent UI, розділ MCP & tools: `kagent/qdrant-mcp-official` має `qdrant-find` і `qdrant-store`.
- Тест через MCP-протокол: `qdrant-store` записав речення, `qdrant-find` знайшов його за перефразованим запитом.
- В адмінці Qdrant на порту 6333 з'явилась колекція `abox-minilm`: 384 виміри, Cosine.
- «route not found» у браузері на адресі MCP-сервісу це нормально: сервіс відповідає лише на POST на шлях `/mcp`.

**Увага:** після перезапуску Codespace образ зникає. Тоді треба повторити дві команди збірки вище і `kubectl apply -f lab4/qdrant-mcp-official.yaml`.

## Тули і промпт (пункти 4-5 лабораторної)

- Поточну конфігурацію агента вивантажено з кластера в `lab4/retrieval-agent-mcp-official.yaml`.
- У tools додано `qdrant-mcp-official` з `qdrant-store` і `qdrant-find`. Блок нашого `qdrant-mcp` прибрано, щоб у прогоні був лише один Qdrant-сервер. `neo4j-mcp` залишено: граф потрібен в обох прогонах.
- Тули Qdrant потрібні лише retrieval-agent. k8s-agent тільки читає кластер, у нього тули не змінювались.

**Що змінено в системному промпті** (`spec.declarative.systemMessage`):

- Назви тулів замінено на `qdrant-store` / `qdrant-find`.
- Інгест: один виклик `qdrant-store` на об'єкт, без сирого YAML. В `information` йде опис на 2-4 речення, у `metadata` йдуть kind, namespace, name і key.
- Пошук: для гібридних питань агент бере `key` з metadata результату і з ним іде в `read-cypher`. Додано речення про формат відповіді `<entry><content>...</content><metadata>...</metadata></entry>` і ліміт 5 результатів.

**Чому короткий опис, а не YAML:** MiniLM в офіційному сервері бачить лише перші 128 токенів тексту. Це виміряно запуском fastembed у нашому образі.

**Перевірка перед застосуванням:** серверний dry-run пройшов, назви аргументів звірено з кодом mcp-server-qdrant v0.8.1.

**Особливість `qdrant-store`:** щоразу створює нову точку, тож повторний інгест дає дублікати. Граф повтор витримує, бо там MERGE. Тому перед інгестом колекція має бути порожня або відсутня.

## Інгест

### Підготовка (перевірено 2026-09-27)

- `retrieval-agent`: generation 3, Ready, модель `gemini-gemini-3-1-flash-lite`, `reconcile=disabled`. Тули: neo4j-mcp, qdrant-mcp-official (`qdrant-store`, `qdrant-find`), k8s-agent. У промпті є `qdrant-find` і немає `vector_find`.
- `k8s-agent`: `gemini-gemini-3-1-flash-lite`, `reconcile=disabled`.
- Neo4j очищено: 0 нод.
- Qdrant: лише `abox-nomic` прогону A. `abox-minilm` ще не існує, сервер створить її при першому записі.
- `memory.peak` пода `qdrant-mcp-official` до інгесту: 289017856 байт, приблизно 276 MiB.

### Запит і результат

Сесія `01a0e333-50c9-7b22-b2ce-4d20e61abf8f`.

```
Ingest these objects, one at a time: every kagent.dev Agent, ModelConfig,
MCPServer and RemoteMCPServer in namespace kagent. For each object ask
k8s-agent for its full YAML, write it to the graph, then store one
qdrant-store entry for it. When done, list every key you ingested.
```

| Вимір | Значення |
|---|---|
| Об'єктів | 14, той самий набір, що в A |
| Точок у `abox-minilm` | 14, 384 виміри |
| Нод у Neo4j | 14 |
| Ребер | `USES_MODEL` 7 (одне хибне), `USES_TOOL` 6 (в A було 10) |
| Час | приблизно 1 хв 45 с, 14:11:42-14:13:27 UTC |
| Пік пам'яті пода | 517 MiB (до інгесту 276 MiB) |
| Виклики тулів | k8s-agent 16, write-cypher 14, qdrant-store 14 |

Час узято з API: початок це мітка в UUIDv7 ідентифікатора задачі, кінець це `status.timestamp`.

**Що пішло не так у графі.** На запит про retrieval-agent k8s-agent повернув прозовий переказ промпту агента замість YAML, без `modelConfig` і без `tools`. Тому retrieval-agent:

- записав хибне ребро `USES_MODEL` на `default-model-config`, хоча в кластері агент на Gemini;
- не записав жодного зі своїх 3 ребер `USES_TOOL` (neo4j-mcp, qdrant-mcp-official, k8s-agent).

Бракує також ребра `observability-agent -> promql-agent`. Разом 4 відсутні `USES_TOOL`.

**Описи у векторі** написано прозою, `key` у metadata є (в A його не було). Але деталей менше, ніж в A:

| Об'єкт | Є в описі | Немає в описі |
|---|---|---|
| kagent-tool-server | «Kubernetes, Helm, and operational tools» | Cilium, Istio, Prometheus, адреса |
| default-model-config | OpenAI, gpt-4.1-mini | секрет, ключ |
| neo4j-mcp | «Neo4j graph database capabilities» | образ, bolt-адреса |
| k8s-agent | «general-purpose Kubernetes expert agent», troubleshooting | |
| retrieval-agent | хибне «uses default-model-config (gpt-4.1-mini)» | |

**Наслідок для порівняння.** Корпуси A і B не ідентичні: описи генерує модель, і щоразу вони виходять різні. P2 (Cilium, Istio), H2 (Prometheus), L1 (секрет) і L2 (адреса) залежать від деталей, яких в описах B немає. Чесна відповідь зі сховищ на ці питання в B: «не знайдено» або часткова.

## Як рахували score

Офіційний `qdrant-find` повертає лише порядок. Скрипт `lab4/score-minilm.py` у поді `qdrant-mcp-official` вбудовує той самий запит тією ж MiniLM і шукає в `abox-minilm`. Порядок збігається з тим, що повернув сервер.

```bash
P=$(kubectl get pod -n kagent -o name | grep qdrant-mcp-official)
kubectl cp lab4/score-minilm.py kagent/${P#pod/}:/tmp/score.py -c mcp-server
kubectl exec -n kagent $P -c mcp-server -- python /tmp/score.py "<запит, який агент передав у qdrant-find>"
```

Абсолютні score MiniLM і nomic між собою не порівнюються: різні моделі, різна шкала. Порівнюємо місце і відрив від другого.

Скрипт завантажує модель ще раз у тому самому контейнері, тож `memory.peak` після нього вже не відображає роботу сервера. Пік інгесту (517 MiB) записано до першого запуску скрипта.

## Відповіді

Правила: кожне питання в новому чаті з retrieval-agent, не в сесії інгесту; дані тулів з API kagent `/api/sessions/<id>/tasks`. Класифікація питань і очікувані відповіді у `summary.md`.

**D1. Which MCP server connects to Neo4j?** Сесія `01a0e33c-cc0a-7b63-9fea-760da33317b1`.

- Тули, 1 виклик: `qdrant-find` із запитом «MCP server connecting to Neo4j». Ні `get-schema`, ні `read-cypher`.
- Топ-5: 1 neo4j-mcp 0.647, 2 kagent-grafana-mcp 0.365, 3 kagent-tool-server 0.296, 4 qdrant-mcp 0.289, 5 qdrant-mcp-official 0.281.
- Відповідь: neo4j-mcp, «provides Neo4j graph database capabilities». Вигаданого немає. Образу і bolt-адреси у відповіді немає, бо їх немає в описі.
- Оцінка: 2. Відрив 0.28 (в A 0.13).

**D2. Which model config uses OpenAI gpt-4.1-mini?** Сесія `01a0e33e-06b7-7d8a-8703-5543e02a771c`.

- Тули, 1 виклик: `qdrant-find` із запитом «OpenAI gpt-4.1-mini». Граф не використано.
- Топ-5: 1 default-model-config 0.654, 2 observability-agent 0.375, 3 retrieval-agent 0.281, 4 promql-agent 0.267, 5 kgateway-agent 0.251.
- Відповідь: `kagent/default-model-config`, джерело вектор. Вигаданого немає.
- Оцінка: 2. Відрив 0.28.
- В A агент відповів на D2 з графа, у B з вектора. Хибний опис retrieval-agent на 3-му місці на відповідь не вплинув.

**P1. My pod keeps crashing, which agent can troubleshoot it?** Сесія `01a0e33f-741c-7817-ab79-9e2f5a57b078`.

- Тули, 1 виклик: `qdrant-find` із запитом «pod troubleshooting agent». k8s-agent не викликано (в A був).
- Топ-5: 1 k8s-agent 0.480, 2 helm-agent 0.435, 3 promql-agent 0.407, 4 kagent-tool-server 0.396, 5 observability-agent 0.387.
- Відповідь: k8s-agent, «general-purpose Kubernetes expert … troubleshooting», з вектора. Також згадано helm-agent і observability-agent як агентів із «troubleshooting capabilities». Для helm-agent це є в описі, для observability-agent ні: там лише моніторинг і метрики. Невелике перебільшення, не вигаданий факт.
- Оцінка: 2. Відрив 0.045 (в A 0.03). Правильний об'єкт першим, але впевненість слабка.

**P2. Which component hands out service-mesh and network-policy tooling?** Сесія `01a0e346-a57a-781e-a907-a1f340361824`.

- Тули, 2 виклики: `qdrant-find` із запитом «service-mesh and network-policy tooling», потім `read-cypher` на вхідні `USES_TOOL` до kagent-tool-server.
- Топ-5: 1 kagent-tool-server 0.314, 2 observability-agent 0.312, 3 argo-rollouts-conversion-agent 0.308, 4 kgateway-agent 0.294, 5 helm-agent 0.289.
- Відповідь: kagent-tool-server, правильно. Але в описі немає ні service mesh, ні network policy, ні Cilium, ні Istio, лише «Kubernetes, Helm, and operational tools». Зв'язок із питанням модель вивела сама: це єдиний сервер тулів у результатах, і граф показує, що ним користуються 5 агентів.
- Оцінка: 2 за правильність, обґрунтованість часткова.
- Перше місце випадкове: відрив 0.002, всі п'ять між 0.29 і 0.31. MiniLM не знайшов у тексті нічого про питання, бо там цього немає.

**L1. Which Kubernetes secret and key hold the API key for the default model config?** Сесія `01a0e347-cb98-70a6-8ce6-20f2fbe82523`. Очікувано зі сховищ: «не знайдено», в описі немає ні секрету, ні ключа.

- Тули, 2 виклики: `qdrant-find` із запитом «API key for default model config», потім `k8s_agent` з запитом «get modelconfig/default-model-config -n kagent -o yaml»: живе читання кластера.
- Топ-5: 1 default-model-config 0.508, 2 argo-rollouts-conversion-agent 0.260, 3 promql-agent 0.247, 4 helm-agent 0.246, 5 kgateway-agent 0.234.
- Відповідь: `kagent-openai`, `OPENAI_API_KEY`. Факт правильний, агент чесно пише, що взяв його з кластера.
- Оцінка: 2 за правильність, обґрунтованість «ні». Пошук спрацював: відрив 0.25.
- Порушення заборони «do not delegate» повторилось і в B.

**L2. At which HTTP endpoint is the kagent tool server reachable?** Сесія `01a0e348-b731-7617-a844-83ece7122093`. Очікувано зі сховищ: «не знайдено».

- Тули, 2 виклики: `qdrant-find` із запитом «kagent tool server endpoint», потім `k8s_agent` з запитом «get RemoteMCPServer kagent/kagent-tool-server -o yaml»: живе читання кластера.
- Топ-5: 1 kagent-tool-server 0.659, 2 helm-agent 0.572, 3 kgateway-agent 0.569, 4 argo-rollouts-conversion-agent 0.551, 5 k8s-agent 0.546.
- Відповідь: `http://kagent-tools.kagent:8084/mcp`, з кластера, агент це вказав. Результат такий самий, як в A.
- Оцінка: 2 за правильність, обґрунтованість «ні». Пошук: відрив 0.09 (в A 0.06).

**H1. Which tool server does the Kubernetes expert agent use, and what does it expose?** Сесія `01a0e349-1c81-75ed-8c35-bdc91042d16f`.

- Тули, 2 виклики, у порядку з промпту: `qdrant-find` із запитом «Kubernetes expert agent tool server», потім `read-cypher` по USES_TOOL від `kagent/k8s-agent`, результат kagent-tool-server.
- Топ-5: 1 kagent-tool-server 0.731, 2 k8s-agent 0.712, 3 argo-rollouts-conversion-agent 0.602, 4 helm-agent 0.577, 5 kgateway-agent 0.560. Обидва потрібні об'єкти у двох верхніх рядках.
- Відповідь: kagent-tool-server, «Kubernetes, Helm, and operational tools». Точно за текстом, вигаданого немає.
- Оцінка: 1. Сервер правильний, але зі списку Kubernetes, Argo Rollouts, Cilium, Istio, Helm, Kubescape, Prometheus названо лише Kubernetes і Helm, бо решти немає в описі.
- На відміну від A, «Kubernetes expert agent» знайдено через вектор, а не вгадано: в описі ці слова є.

**H2. Which agents depend on the tool server that provides Helm and Prometheus tooling?** Сесія `01a0e349-a644-79d7-8ca9-d65fde7fcf07`.

- Тули, 2 виклики, у порядку з промпту: `qdrant-find` із запитом «Helm and Prometheus tooling», потім `read-cypher` на вхідні `USES_TOOL` до kagent-tool-server.
- Топ-5: 1 promql-agent 0.463, 2 helm-agent 0.446, 3 kagent-tool-server 0.427, 4 observability-agent 0.265, 5 argo-rollouts-conversion-agent 0.254.
- Відповідь: усі 5 агентів із графа. Вигаданих агентів немає.
- Оцінка: 2 за правильність, обґрунтованість часткова. Агент пише, що kagent-tool-server «provides the Helm and Prometheus tooling» і що це з вектора, але в описі є лише Helm. Вибір сервера правильний, бо це єдиний сервер тулів у результатах.
- Правильний об'єкт на 3-му місці (в A на 2-му). Вище стоять агенти, чиї описи містять «Prometheus» (promql-agent) і «Helm» (helm-agent).

**N1. Which agent uses Anthropic Claude?** Сесія `01a0e34b-ad3c-77ff-8d6c-7f6ea8855632`.

- Тули, 3 виклики: `qdrant-find` «Agent using Anthropic Claude model», `read-cypher` по всіх парах Agent → ModelConfig, `qdrant-find` «Anthropic Claude model configuration».
- Відповідь: жодного. Названо обидві ModelConfig, OpenAI і Gemini. Вигаданого немає, у кластер агент не ходив.
- Оцінка: 2. Місце: не застосовно.
- `get-schema` не викликано, хоча промпт вимагає цього перед відповіддю «немає». В A агент його викликав. Хибне ребро retrieval-agent → default-model-config було в результаті `read-cypher`, але у відповідь не потрапило.
- Перша спроба N1 (сесія `01a0e349-a644-79d7-8ca9-d65fde7fcf07`) була задана в тому самому чаті, що й H2, тож її не рахуємо. Відповідь там була така сама, `get-schema` теж пропущено.

## Підсумок прогону

- 17 із 18 балів: H1 = 1, бо в описі бракує більшості тулів.
- Правильний об'єкт першим у 7 із 8 питань із векторним пошуком; у H2 він на 3-му місці. У прямих питаннях (D1, D2, L1) відрив 0.25-0.28. У P2 перше місце випадкове, відрив 0.002.
- Відповідь повністю зі сховищ у 5 із 9. У P2 і H2 сервер вибрано правильно, але зв'язок із питанням не з тексту; у L1 і L2 факти з живого кластера.
- Звертання до k8s-agent у L1 і L2.
- Викликів тулів разом: 16. `get-schema` не викликано в жодному питанні, хоча промпт вимагає його перед відповіддю «не знайдено».
- Порушення заборони «do not delegate to another agent» повторилось (L1, L2), як і в A.
