# Прогін A: наш qdrant-mcp (nomic через llama.cpp)

Записи цього прогону, зібрані з `logs.md`. Хронологія, спільні для обох прогонів речі (вибір моделі агентів, доступ до UI, команди) лишаються в `logs.md`. Порівняння з прогоном B у `summary.md`.

## Конфігурація

| | |
|---|---|
| MCPServer | `qdrant-mcp`, образ `ghcr.io/den-vasyliev/abox/qdrant-mcp:0.4.0`, код у `mcp/qdrant-mcp/` |
| Тули | `vector_store`, `vector_find` |
| Ембединги | `nomic-embed-text-v1.5` через llama.cpp `/v1/embeddings` (`http://llama-cpp-embeddings.llama-cpp:8090`), 768 вимірів |
| Колекція | `abox-nomic`, Cosine |
| Довгий текст | сервер ріже на шматки по `EMBEDDING_MAX_INPUT_CHARS` (7000 символів) і вбудовує все |
| Score | `vector_find` повертає score в кожному результаті |
| Файл агента | `lab4/retrieval-agent-mcp-llmcpp.yaml` |
| Модель агентів | `gemini-gemini-3-1-flash-lite` (Gemini `gemini-3.1-flash-lite`) для retrieval-agent і k8s-agent |
| Пік пам'яті пода MCP | 42 MiB за весь час роботи пода (з 11:52 UTC, включно з інгестом і питаннями). Модель поза подом, у llama.cpp |

## Промпт: вирівнювання з прогоном B

Порівняння файлів показало, що в `retrieval-agent-mcp-llmcpp.yaml` лишився старий промпт інгесту. З ним агент міг покласти в `vector_store` сирий YAML, а наш сервер ріже довгий текст на шматки і вбудовує все. Тоді порівнювались би два різні способи інгесту, а не MiniLM з nomic.

**Змінено:**

- Крок 4 інгесту тепер такий самий, як у B: один виклик `vector_store` на об'єкт, без сирого YAML, опис на 2-4 речення з kind, namespace і name на початку, у metadata є `key`.
- Гібридний пошук іде в `read-cypher` за `key` з metadata, як у B.

**Після змін промпти A і B відрізняються лише:**

- назвами тулів: `vector_store` / `vector_find` в A, `qdrant-store` / `qdrant-find` у B;
- реченням про формат `<entry>` і ліміт 5 результатів, яке є лише в B.

Поза промптом різні лише MCP-сервер у tools і підпис у `description`, який моделі не передається.

**Свідоме рішення:** речення «Only the beginning of the text is embedded» залишено і в A, хоча для нашого сервера воно неправдиве. Воно змушує модель писати короткі описи, і тоді тексти в обох прогонах однакової форми.

## Пробний інгест (до підключення офіційного MCP)

Агента попросили проінгестити «всіх Agent в namespace kagent». Результат:

- В `abox-nomic` потрапило 2 точки замість 7: список усіх агентів одним документом і окремо k8s-agent.
- У Neo4j вийшло 7 нод Agent, але лише 2 зв'язки, обидва від k8s-agent.

**Висновок:** у запиті треба явно перелічувати типи об'єктів і просити один документ на об'єкт, а перед кожним прогоном чистити обидва сховища.

## Інгест на повному корпусі

Після перезапуску Codespace (2026-09-27) кластер порожній, тож інгест A іде в чисті сховища. Запит:

```
Ingest these objects, one at a time: every kagent.dev Agent, ModelConfig,
MCPServer and RemoteMCPServer in namespace kagent. For each object ask
k8s-agent for its full YAML, write it to the graph, then store one
vector_store entry for it. When done, list every key you ingested.
```

| Вимір | Значення |
|---|---|
| Об'єктів | 14: 7 Agent, 2 ModelConfig, 3 MCPServer, 2 RemoteMCPServer |
| Точок у `abox-nomic` | 14, по одній на об'єкт, 768 вимірів; нічого не різалось |
| Нод у Neo4j | 14 |
| Ребер | `USES_MODEL` 7, `USES_TOOL` 10 |
| Час інгесту | не засічено |

Об'єкти: Agent argo-rollouts-conversion-agent, helm-agent, k8s-agent, kgateway-agent, observability-agent, promql-agent, retrieval-agent; ModelConfig default-model-config, gemini-gemini-3-1-flash-lite; MCPServer neo4j-mcp, qdrant-mcp, qdrant-mcp-official; RemoteMCPServer kagent-tool-server, kagent-grafana-mcp.

**Відхилення від промпту:** у metadata є kind, name і namespace, але немає `key`. Гібридний пошук усе одно можливий, бо ключ складається з namespace і name.

**Стиль описів:** перелік полів, а не проза. Наприклад: «Agent kagent/helm-agent. Configuration: Declarative. Model: default-model-config. Tools: kagent-tool-server (RemoteMCPServer). Runtime: go. System Message: Helm Expert ...». Деталі, які потрапили в описи і важливі для питань:

| Об'єкт | Є в описі | Немає в описі |
|---|---|---|
| kagent-tool-server | Kubernetes, Argo Rollouts, Cilium, Istio, Helm, Kubescape, Prometheus | адреса `http://kagent-tools.kagent:8084/mcp` |
| default-model-config | OpenAI, gpt-4.1-mini, секрет `kagent-openai` | ключ `OPENAI_API_KEY` |
| neo4j-mcp | образ `neo4j/mcp:v1.6.0`, URI `bolt://neo4j.neo4j:7687` | |
| k8s-agent | «KubeAssist troubleshooting agent» | слово «expert» |

## Відповіді

Правила: кожне питання в новому чаті з retrieval-agent, не в сесії інгесту; дані тулів з API kagent `/api/sessions/<id>/tasks`. Класифікація питань і очікувані відповіді у `summary.md`.

**D1. Which MCP server connects to Neo4j?** Сесія `01a0e319-0a66-75e3-93a2-6053f7d96e87`.

- Тули, 2 виклики: `get-schema`, потім `vector_find` із запитом «MCP server that connects to Neo4j». `read-cypher` не викликався.
- Топ-5 `vector_find`:

  | Місце | Об'єкт | Score |
  |---|---|---|
  | 1 | neo4j-mcp | 0.808 |
  | 2 | kagent-grafana-mcp | 0.675 |
  | 3 | qdrant-mcp-official | 0.660 |
  | 4 | qdrant-mcp | 0.653 |
  | 5 | retrieval-agent | 0.652 |

- Відповідь: neo4j-mcp, образ `neo4j/mcp:v1.6.0`, URI `bolt://neo4j.neo4j:7687`. Обидві деталі є в описі, вигаданого немає.
- Оцінка: 2. Відрив від другого місця 0.13.

**D2. Which model config uses OpenAI gpt-4.1-mini?** Сесія `01a0e31a-459d-7461-9201-47bf67c0695c`.

- Тули, 2 виклики: `get-schema`, потім `read-cypher`:
  ```
  MATCH (mc:ModelConfig) WHERE mc.model CONTAINS 'gpt-4.1-mini'
  RETURN mc.key, mc.model, mc.provider
  ```
  `vector_find` не викликався.
- Відповідь: `kagent/default-model-config`, OpenAI `gpt-4.1-mini`, джерело граф. Вигаданого немає.
- Оцінка: 2. Місце у векторному пошуку: не застосовно.
- Токени з UI: 11247 усього, 11130 вхідних, 117 вихідних.
- Модель і провайдер лежать у властивостях ноди ModelConfig, тож агент відповів із графа, без ембедингів. D2 тут не перевіряє векторний пошук.

**P1. My pod keeps crashing, which agent can troubleshoot it?** Сесія `01a0e31b-4af1-7762-9ec3-8ef3e434da16`.

- Тули, 4 виклики:
  1. `k8s_agent` з запитом «get pods»: живе читання кластера, не пошук у сховищах. У відповідь не пішло.
  2. `get-schema`.
  3. `read-cypher`: `MATCH (a:Agent) RETURN a.key, a.name, a.namespace`, усі 7 агентів.
  4. `vector_find` із запитом «troubleshoot crashing pods».
- Топ-5 `vector_find`:

  | Місце | Об'єкт | Score |
  |---|---|---|
  | 1 | k8s-agent | 0.584 |
  | 2 | kagent-grafana-mcp | 0.553 |
  | 3 | helm-agent | 0.543 |
  | 4 | argo-rollouts-conversion-agent | 0.530 |
  | 5 | retrieval-agent | 0.523 |

- Відповідь: k8s-agent, «KubeAssist troubleshooting agent». Додатково названо helm-agent для проблем із Helm-релізами. Обидва факти є в описах, вигаданого немає.
- Оцінка: 2.
- Відрив від другого місця лише 0.03, всі score низькі (0.52-0.58). Правильний об'єкт першим, але впевненість пошуку слабка.

**P2. Which component hands out service-mesh and network-policy tooling?** Сесія `01a0e31e-f8fe-783f-b6ad-a2aa7a87dd35`.

- Тули, 2 виклики: `get-schema`, потім `vector_find` із запитом «service-mesh network-policy tooling».
- Топ-5 `vector_find`:

  | Місце | Об'єкт | Score |
  |---|---|---|
  | 1 | helm-agent | 0.601 |
  | 2 | kagent-tool-server | 0.595 |
  | 3 | kgateway-agent | 0.585 |
  | 4 | argo-rollouts-conversion-agent | 0.571 |
  | 5 | default-model-config | 0.566 |

- Відповідь: kagent-tool-server, бо серед його тулів є Cilium (network policy, service mesh) та Istio (service mesh). Назви тулів узято з опису. Зв'язок «Cilium означає network policy» модель додала з власних знань, і він правильний.
- Оцінка: 2.
- Правильний об'єкт лише на 2-му місці, на 0.006 нижче за helm-agent. Усі п'ять score між 0.57 і 0.60: nomic фактично не відрізнив потрібний опис від інших. Правильну відповідь знайшла модель, а не ранжування.

**L1. Which Kubernetes secret and key hold the API key for the default model config?** Сесія `01a0e320-2cdc-740d-ba65-d674fb4b007e`. Очікувано зі сховищ: секрет kagent-openai, ключ «не знайдено».

- Тули, 4 виклики:
  1. `get-schema`.
  2. `read-cypher`: `MATCH (m:ModelConfig {name: "default"}) RETURN m`. Ім'я вгадано неправильно, результат порожній.
  3. `vector_find` із запитом «default model config API key secret».
  4. `k8s_agent` з запитом «get ModelConfig default-model-config -n kagent -o yaml»: живе читання кластера. Ключ `OPENAI_API_KEY` узято саме звідси.
- Топ-5 `vector_find`:

  | Місце | Об'єкт | Score |
  |---|---|---|
  | 1 | default-model-config | 0.737 |
  | 2 | gemini-gemini-3-1-flash-lite | 0.621 |
  | 3 | promql-agent | 0.616 |
  | 4 | observability-agent | 0.609 |
  | 5 | helm-agent | 0.608 |

- Відповідь: секрет `kagent-openai`, ключ `OPENAI_API_KEY`. Факт правильний, але ключа в сховищах немає: він прийшов із живого кластера. Агент сам пише, що підтвердив відповідь через k8s-agent.
- Оцінка: 2 за правильність, обґрунтованість часткова. Лише зі сховищ було б 1: секрет знайдено, ключ ні.
- Пошук спрацював: правильний об'єкт на 1-му місці, відрив 0.12.

**L2. At which HTTP endpoint is the kagent tool server reachable?** Сесія `01a0e322-1c8b-723e-ada6-74a15f119221`. Очікувано зі сховищ: «не знайдено», бо адреси в описі немає.

- Тули, 3 виклики:
  1. `get-schema`.
  2. `vector_find` із запитом «kagent tool server endpoint».
  3. `k8s_agent` з запитом «get RemoteMCPServer kagent-tool-server -n kagent -o yaml»: живе читання кластера.
- Топ-5 `vector_find`:

  | Місце | Об'єкт | Score |
  |---|---|---|
  | 1 | kagent-tool-server | 0.799 |
  | 2 | helm-agent | 0.741 |
  | 3 | k8s-agent | 0.733 |
  | 4 | kgateway-agent | 0.727 |
  | 5 | argo-rollouts-conversion-agent | 0.698 |

- Відповідь: `http://kagent-tools.kagent:8084/mcp`. Агент чесно пише, що адресу взято з кластера через k8s-agent.
- Оцінка: 2 за правильність, обґрунтованість «ні»: зі сховищ адресу взяти неможливо. Якби агент дотримався промпту, правильною відповіддю було б «не знайдено».
- Пошук спрацював: правильний об'єкт на 1-му місці, відрив 0.06.

**H1. Which tool server does the Kubernetes expert agent use, and what does it expose?** Сесія `01a0e325-dbc7-756d-aec2-8fb867babaf0`.

- Тули, 3 виклики:
  1. `get-schema`.
  2. `read-cypher`: `MATCH (a:Agent {name: "k8s-agent"})-[r:USES_TOOL]->(t) RETURN t.name, labels(t)`, результат kagent-tool-server.
  3. `vector_find` із запитом «What does kagent-tool-server expose?».
- Топ-5 `vector_find`: 1 kagent-tool-server 0.787, 2 helm-agent 0.731, 3 k8s-agent 0.724, 4 kgateway-agent 0.705, 5 observability-agent 0.691.
- Відповідь: kagent-tool-server (з графа); Kubernetes management, Argo Rollouts, Cilium, Istio, Helm, Kubescape, Prometheus (з вектора). Кожен факт має вказане джерело, вигаданого немає.
- Оцінка: 2.
- Порядок зворотний до промпту: спершу граф, потім вектор. Те, що «Kubernetes expert agent» означає k8s-agent, модель вгадала з назви без пошуку: в описі стоїть «KubeAssist troubleshooting agent», слова «expert» там немає.

**H2. Which agents depend on the tool server that provides Helm and Prometheus tooling?** Сесія `01a0e327-e489-7d3b-86bc-f90b15758f0a`.

- Тули, 3 виклики, у порядку з промпту:
  1. `get-schema`.
  2. `vector_find` із запитом «Helm and Prometheus tooling».
  3. `read-cypher`: `MATCH (a:Agent)-[:USES_TOOL]->(t:RemoteMCPServer {name: 'kagent-tool-server'}) RETURN a.key`.
- Топ-5 `vector_find`: 1 helm-agent 0.601, 2 kagent-tool-server 0.571, 3 promql-agent 0.533, 4 observability-agent 0.515, 5 argo-rollouts-conversion-agent 0.497.
- Відповідь: усі 5 агентів (observability-agent, kgateway-agent, helm-agent, argo-rollouts-conversion-agent, k8s-agent), з графа. Сервер визначено з вектора. Вигаданого немає.
- Оцінка: 2.
- Правильний об'єкт знову на 2-му місці, як у P2: helm-agent обходить його на 0.03. Модель однаково вибрала сервер, бо шукала саме «tool server», а не агента.

**N1. Which agent uses Anthropic Claude?** Сесія `01a0e329-1893-7a04-ad1c-7c7e174a8710`.

- Тули, 4 виклики:
  1. `vector_find` із запитом «Which agent uses Anthropic Claude?». У топ-5 лише агенти (0.57-0.63), Claude чи Anthropic не згадано в жодному.
  2. `get-schema`.
  3. `read-cypher`: пошук ModelConfig з `claude` у model або `anthropic` у provider, результат порожній. `CONTAINS` чутливий до регістру, тож провайдера «Anthropic» цей запит не знайшов би. Помилку перекрив наступний запит.
  4. `read-cypher`: усі пари Agent → ModelConfig. 7 агентів: 2 на Gemini, 5 на OpenAI.
- Відповідь: жодного агента з Claude немає. Перевірено обидва сховища, перелічено фактичних провайдерів. Вигаданого немає, у кластер агент не ходив.
- Оцінка: 2. Місце: не застосовно.
- Правило промпту «перш ніж казати, що чогось немає, виклич get-schema і read-cypher» виконано.

## Підсумок прогону

- 9 із 9 питань з оцінкою 2.
- Правильний об'єкт першим у 5 із 7 питань із векторним пошуком; у P2 і H2 він на 2-му місці, і в обох випадках його обійшов helm-agent.
- Відповідь повністю зі сховищ у 7 із 9. У L1 ключ, а в L2 адреса прийшли з живого кластера.
- Звертання до k8s-agent у P1, L1, L2. Усі три йшли в одну сесію k8s-agent (`01a0e2b9-...`), тож він зберігав контекст між питаннями.
- Викликів тулів разом: 27. `get-schema` викликано в кожному питанні.

**Знахідка: Gemini ігнорує заборону в промпті.** У розділі Retrieve сказано: «Do not fetch manifests, do not delegate to another agent». Попри це в P1, L1 і L2 агент викликав `k8s-agent` і брав факти з живого кластера, коли їх бракувало у сховищах. Промпт не міняли, щоб A і B лишались порівнюваними.
