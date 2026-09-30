# Журнал лабораторної 4: Agentic Retrieval з двома Qdrant MCP

Хронологія того, що зроблено, навіщо, і якими командами. Ведеться паралельно з роботою.
Англійською той самий матеріал для рецензента лежить у `ADR-001-agentic-retrieval-qdrant-mcp.md`.

## Завдання

1. Розгорнутися з релізу feat/llmd-embeddings
2. Додати офіційний Qdrant MCP (github.com/qdrant/mcp-server-qdrant)
3. Налаштувати модель для retrieval-agent та k8s-agent
4. Додати інструменти офіційного Qdrant MCP
5. Налаштувати системний промпт для використання офіційного Qdrant MCP
6. Проіндексувати дані (k8s маніфести) з sentence-transformers/all-MiniLM-L6-v2
7. Проіндексувати ті ж дані з нашим qdrant-mcp (змінити тулсет)
8. Порівняти та оцінити якість Agentic Retrieval і додати результати до ADR

## Позначення

- **Прогін B** це офіційний MCP: тули `qdrant-store` / `qdrant-find`, модель MiniLM, 384 виміри, колекція `abox-minilm`.
- **Прогін A** це наш MCP: тули `vector_store` / `vector_find`, модель nomic через llama.cpp, 768 вимірів, колекція `abox-nomic`.

---

## Пункт 1. Розгортання з релізу

Кластер тягне OCI-артефакт `releases-llmd-embeddings`. Зроблено до початку журналу.

## Пункт 2. Офіційний Qdrant MCP

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

**Увага:** після перезапуску Codespace образ зникає. Тоді треба повторити дві команди збірки вище.

## Пункт 3. Модель для агентів

- Обидва агенти виведено з-під Flux, щоб він не відкотив ручні зміни:
  ```bash
  kubectl annotate agent k8s-agent -n kagent kustomize.toolkit.fluxcd.io/reconcile=disabled --overwrite
  kubectl -n kagent annotate agent retrieval-agent kustomize.toolkit.fluxcd.io/reconcile=disabled --overwrite
  ```
- Модель змінювали тричі:

| Модель | Що сталося |
|---|---|
| Gemini `gemini-3.1-flash-lite` | Повторювана помилка 503 «high demand» від Google посеред інгесту |
| OpenAI `gpt-5-mini` | k8s-agent виконав тули і 14+ хвилин чекав відповіді моделі |
| OpenAI `gpt-4.1-mini`, ModelConfig `openai-gpt-4-1-mini` | Той самий «завис». Причина знайшлась: агент розсилав k8s-agent багато паралельних запитів (див. нижче) |

**Остаточно:** після gpt-4.1-mini обидва агенти повернули на Gemini `gemini-gemini-3-1-flash-lite`, і на ній пройшли обидва прогони, інгест і питання (див. розділ «Модель агентів» нижче). Модель має бути однаковою в прогонах A і B.

## Пункт 4. Тули офіційного MCP в retrieval-agent

- Поточну конфігурацію агента вивантажено з кластера в `lab4/retrieval-agent-mcp-official.yaml`.
- У tools додано `qdrant-mcp-official` з `qdrant-store` і `qdrant-find`.
- Тули Qdrant потрібні лише retrieval-agent. k8s-agent тільки читає кластер, і в нього тули не змінювались.

## Пункт 5. Системний промпт

**Що таке системний промпт:** це поле `spec.declarative.systemMessage` в агенті. kagent надсилає цей текст моделі першим повідомленням у кожній розмові.

**Чому його треба міняти:** модель бачить тули лише як назву і схему аргументів. Як їх використовувати, каже промпт, а старий промпт називав лише `vector_store` / `vector_find`.

**Що змінено в `retrieval-agent-mcp-official.yaml`:**

- Назви тулів замінено на `qdrant-store` / `qdrant-find`.
- Інгест: один виклик `qdrant-store` на об'єкт, без сирого YAML. В `information` йде опис на 2-4 речення, у `metadata` йдуть kind, namespace, name і key.
- Пошук: для гібридних питань агент бере `key` з metadata результату і з ним іде в `read-cypher`.
- Блок нашого `qdrant-mcp` прибрано з tools, щоб у прогоні B був лише один Qdrant-сервер.
- `neo4j-mcp` залишено: граф потрібен в обох прогонах.

**Чому короткий опис, а не YAML:** MiniLM в офіційному сервері бачить лише перші 128 токенів тексту, решту обрізає. Я виміряла це, запустивши fastembed у нашому образі. Наш сервер ділить довгий текст на шматки, а офіційний так не робить.

**Перевірка перед застосуванням:** серверний dry-run пройшов, а назви аргументів звірено з офіційним кодом mcp-server-qdrant v0.8.1.

**Для прогону A** є файл `retrieval-agent-mcp-llmcpp.yaml`. Він має відрізнятися від файлу B лише назвами тулів і блоком MCP-сервера.

## Пробний інгест (до пункту 4)

Ще до підключення офіційного MCP агента попросили проінгестити всіх Agent. Результат:

- В `abox-nomic` потрапило 2 точки замість 7: список усіх агентів одним документом і окремо k8s-agent.
- У Neo4j вийшло 7 нод Agent, але лише 2 зв'язки, обидва від k8s-agent.

**Висновок:** у запиті треба явно перелічувати об'єкти, а перед кожним прогоном чистити обидва сховища.

## Проблеми з інгестом і їх рішення

| Проблема | Причина | Рішення |
|---|---|---|
| 503 від Gemini | перевантаження на боці Google | перейти на OpenAI |
| Агент зупинявся на пів дорозі | легка модель завершує хід після кількох тулів | короткі запити по 2-3 об'єкти |
| Вигадана назва тула `k8s_agent` | модель помилилась, справжня назва `kagent__NS__k8s_agent` | агент сам виправився, нічого робити не треба |
| Сесія висить у working | агент розіслав 18 паралельних запитів k8s-agent, завершились лише 2 | пачки по 2-3 об'єкти, речення в промпті проти паралельних викликів, перезапуск k8s-agent |

Порядок інгесту в промпті такий: спершу граф, потім вектор. Neo4j перевіряє ключ через обмеження унікальності. Якщо збій станеться посередині, у графі буде нода без вектора, а не вектор, що вказує в нікуди.

Корисні команди:

```bash
# скинути завислий k8s-agent
kubectl rollout restart deploy/k8s-agent -n kagent

# очистити граф перед прогоном
kubectl exec -n neo4j neo4j-0 -- cypher-shell -u neo4j -p abox-neo4j 'MATCH (n) DETACH DELETE n'
```

Колекції Qdrant видаляються в адмінці на порту 6333. Обидва MCP-сервери створюють свою колекцію самі при першому записі.

## Доступ до UI

- **kagent UI:** `kubectl port-forward -n kagent svc/kagent-ui 8080:8080 --address 0.0.0.0`
- **Neo4j Browser:** перевірений спосіб, 2026-09-27.
  1. Прокинути обидва порти однією командою kubectl. Форвард через k9s не підходить: він слухає лише 127.0.0.1 і не тримає багато з'єднань, а Browser при завантаженні тягне десятки файлів, і сторінка лишається білою.
     ```bash
     kubectl port-forward -n neo4j svc/neo4j 7474:7474 7687:7687 --address 0.0.0.0
     ```
  2. Зробити 7687 Public. Поки він Private, проксі GitHub відповідає на WebSocket редиректом 302 на сторінку входу, і Browser не може під'єднатись. 7474 можна лишити Private.
     ```bash
     gh codespace ports visibility 7687:public -c obscure-memory-v65r5vjr4g43p6j4
     ```
  3. Відкрити в браузері сторінку з **7474**: `https://obscure-memory-v65r5vjr4g43p6j4-7474.app.github.dev/browser/`. На адресі 7687 сторінки немає, там буде білий екран.
  4. У формі входу схема і адреса вводяться в два окремі поля:

     | Поле | Значення |
     |---|---|
     | випадний список | `bolt+s://` |
     | Connect URL | `obscure-memory-v65r5vjr4g43p6j4-7687.app.github.dev:443`, без схеми |
     | Username / Password | `neo4j` / `abox-neo4j` |

  5. Після роботи повернути 7687 у Private: `gh codespace ports visibility 7687:private -c obscure-memory-v65r5vjr4g43p6j4`.

  **Чому `bolt+s://`, а не `neo4j+s://`.** За документацією JavaScript-драйвера Neo4j, на якому працює Browser, схеми `neo4j*` отримують від сервера таблицю маршрутизації навіть для одного сервера. Сервер повертає свою внутрішню адресу в кластері, недоступну ззовні. Схеми `bolt*` під'єднуються напряму до вказаної адреси. Джерело: neo4j.com/docs/javascript-manual/current/connect-advanced/.

  **Шум у консолі браузера, який не заважає:** `MaxListenersExceededWarning` друкує Node.js у форвардері VS Code; `ObjectMultiplex - orphaned data` друкує розширення MetaMask; рядки `SSO discovery` означають, що Browser шукає SSO, якого в нас немає.
- **Qdrant:** адмінка на порту 6333.

## Пункт 6. Інгест. Статус: зроблено

Інгест пройшов. Наступні кроки:

1. Записати результат інгесту: кількість об'єктів, точок у колекції, нод і ребер у Neo4j, час і пікову пам'ять поду MCP.
   ```bash
   kubectl exec -n neo4j neo4j-0 -- cypher-shell -u neo4j -p abox-neo4j 'MATCH (n) RETURN labels(n)[0] AS label, count(*) AS nodes'
   kubectl exec -n neo4j neo4j-0 -- cypher-shell -u neo4j -p abox-neo4j 'MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS edges'
   kubectl exec -n kagent deploy/qdrant-mcp-official -- cat /sys/fs/cgroup/memory.peak
   ```
2. Задати п'ять питань, кожне в новій сесії.
3. Після питань очистити Neo4j і перейти до прогону A.

## Питання для порівняння

Питання однакові для обох прогонів, кожне задається в новій сесії.

| # | Питання | Очікувана відповідь | Тип |
|---|---|---|---|
| 1 | Which agent should I ask to install or upgrade a Helm chart? | helm-agent | прямий |
| 2 | I want dashboards and metrics for my services, which agent do I talk to? | observability-agent | перефразований |
| 3 | What tools does the agent that manages Helm releases use? | helm-agent та його тули | гібридний |
| 4 | Which agents use the Gemini model config? | див. примітку | граф, контрольний |
| 5 | Which agent manages Terraform state? | такого немає | негативний |

**Примітка до питання 4:** агенти вже не на Gemini. Перефразуй питання під модель, яка реально є в графі. Наприклад: «Which agents use the openai-gpt-4-1-mini model config?», очікувана відповідь k8s-agent і retrieval-agent.

**Що записувати по кожному питанню:**

- які тули викликав агент
- на якому місці серед 5 результатів стоїть правильний об'єкт
- оцінку: 2 правильна, 1 часткова, 0 хибна
- чи немає у відповіді вигаданих фактів

Пікову пам'ять поду MCP дає `cat /sys/fs/cgroup/memory.peak`: байти з моменту старту поду. Metrics API в кластері немає, тому `kubectl top` не працює.

---

## Прогін B, спроба 1: інгест «every ...» одним запитом

**Запит:**

```
Ingest these objects, one at a time: every kagent.dev Agent, ModelConfig,
MCPServer and RemoteMCPServer in namespace kagent. For each object ask
k8s-agent for its full YAML, write it to the graph, then store one
qdrant-store entry for it. When done, list every key you ingested.
```

**Результат: проінгестовано лише 4 об'єкти з приблизно 15.** Граф і Qdrant збігаються:

- `kagent/k8s-agent`
- `kagent/default-model-config`
- `kagent/kagent-tool-server`
- `kagent/neo4j-mcp`

| Вимір | Значення |
|---|---|
| Точок у `abox-minilm` | 4, бо `qdrant-find` з лімітом 5 повернув лише 4 записи |
| Ребер у Neo4j | 1, `USES_TOOL` від k8s-agent до kagent-tool-server |
| Пікова пам'ять поду `qdrant-mcp-official` | 1306669056 байт, приблизно 1246 MiB, з моменту старту поду |

Перший підрахунок нод за лейблами показав 3 ноди, без neo4j-mcp. Список ключів, отриманий трохи пізніше, показав уже 4. Схоже, агент ще дописував граф, коли ти рахувала.

Ребра `USES_MODEL` від k8s-agent немає: він використовує `openai-gpt-4-1-mini`, а цієї ModelConfig у графі немає.

**Висновок:** запит «every ...» агент знову виконав не до кінця. Решту треба доінгестити пачками по 2-3 об'єкти з іменами.

**Увага:** ті 4 об'єкти, що вже є, у пачки не включати. Граф повтор витримає, бо там MERGE. А `qdrant-store` в офіційному сервері щоразу створює нову точку, і повтор дасть дублікати.

---

## Рішення: корпус це 4 об'єкти

Замість доінгесту решти вирішили залишити корпус із 4 об'єктів, які реально записались, і формулювати питання лише по них. Для прогону A ті самі 4 об'єкти інгестяться за іменами.

Що є в описах (з результатів `qdrant-find`):

| Об'єкт | Що записано в описі |
|---|---|
| k8s-agent | Kubernetes expert, cluster operations, troubleshooting, maintenance; runtime Go; використовує kagent-tool-server |
| default-model-config | OpenAI gpt-4.1-mini, секрет kagent-openai, ключ OPENAI_API_KEY |
| kagent-tool-server | RemoteMCPServer, HTTP на kagent-tools.kagent:8084/mcp; тули для Kubernetes, Cilium, Istio, Helm, Kubescape, Prometheus |
| neo4j-mcp | образ neo4j/mcp:v1.6.0, підключення bolt://neo4j.neo4j:7687 |

Граф: одне ребро USES_TOOL від k8s-agent до kagent-tool-server.

Попередні п'ять питань (helm-agent, observability-agent тощо) скасовано: цих об'єктів у корпусі немає.

### Питання, трійка 1

| # | Питання | Очікувана відповідь | Тип |
|---|---|---|---|
| 1 | My pod keeps crashing, which agent can troubleshoot it? | k8s-agent | перефразований: слів «pod», «crashing» в описі немає, є «troubleshooting» |
| 2 | Which MCP server connects to the graph database, and at what address? | neo4j-mcp, bolt://neo4j.neo4j:7687 | прямий, з деталлю зі spec |
| 3 | Which tool server does the Kubernetes expert agent use, and what does it expose? | kagent-tool-server через USES_TOOL; Kubernetes, Cilium, Istio, Helm, Kubescape, Prometheus | гібридний: qdrant-find + read-cypher |

На другу трійку залишено негативне: «Which agent uses Anthropic Claude?», очікувана відповідь «жодного».

### Питання, фінальний набір: 8 + 1

Замінює «трійку 1» вище. По 2 питання на тип, усі по 4 проінгестованих об'єктах. Кожне в новій сесії, однаково в обох прогонах.

**Прямі**, ключові слова є в описі:

| # | Питання | Очікувана відповідь |
|---|---|---|
| D1 | Which MCP server connects to Neo4j? | neo4j-mcp |
| D2 | Which model config uses OpenAI gpt-4.1-mini? | default-model-config |

**Перефразовані**, ключових слів з опису немає:

| # | Питання | Очікувана відповідь |
|---|---|---|
| P1 | My pod keeps crashing, which agent can troubleshoot it? | k8s-agent, в описі є лише «troubleshooting» |
| P2 | Which component hands out service-mesh and network-policy tooling? | kagent-tool-server, в описі це «Istio» і «Cilium» |

**Деталь у глибині тексту**, відповідь стоїть в останньому реченні опису:

| # | Питання | Очікувана відповідь |
|---|---|---|
| L1 | Which Kubernetes secret and key hold the API key for the default model config? | kagent-openai, OPENAI_API_KEY |
| L2 | At which HTTP endpoint is the kagent tool server reachable? | http://kagent-tools.kagent:8084/mcp |

**Гібридні**, потрібні і вектор, і граф:

| # | Питання | Очікувана відповідь |
|---|---|---|
| H1 | Which tool server does the Kubernetes expert agent use, and what does it expose? | kagent-tool-server через USES_TOOL; Kubernetes, Cilium, Istio, Helm, Kubescape, Prometheus |
| H2 | Which agents depend on the tool server that provides Helm and Prometheus tooling? | qdrant-find знаходить kagent-tool-server, read-cypher по вхідних USES_TOOL дає k8s-agent |

**Негативне**, поза типами:

| # | Питання | Очікувана відповідь |
|---|---|---|
| N1 | Which agent uses Anthropic Claude? | жодного; перевіряємо, чи агент не вигадує |

**Застереження щодо типу «деталь у глибині».** У векторах лежать описи на 2-4 речення, а не маніфести, бо так вимагає промпт в обох прогонах. «Глибина» тут це останнє речення, приблизно 50 токенів від початку, тобто в межах 128 токенів MiniLM. Обрізання цей тип, найімовірніше, не зачепить: він перевіряє, чи агент доносить деталь до відповіді, а не якість ембедингу. Перевірка самого обрізання потребувала б окремого прогону із сирим YAML у `qdrant-store`. У висновках не приписувати MiniLM те, чого не міряли.

**Що записувати по кожному питанню:** виклики тулів, місце правильного об'єкта серед результатів qdrant-find (1-5 або промах), оцінка відповіді 0-2, чи є вигадані факти.

---

## Модель агентів

Перевірено командою `kubectl get agent`: обидва агенти, retrieval-agent (generation 9) і k8s-agent (generation 6), працюють на ModelConfig `gemini-gemini-3-1-flash-lite`, тобто Gemini `gemini-3.1-flash-lite`. Поле `thoughtSignature` у відповідях це підтверджувало.

Тобто після невдалої спроби з gpt-4.1-mini (18 паралельних викликів) агентів повернули на Gemini flash-lite. Вдалий інгест 4 об'єктів теж пройшов на Gemini flash-lite. Отже, прогін B повністю, інгест і питання, йде на одній моделі.

**Для прогону A:** обидва агенти мають лишатися на `gemini-gemini-3-1-flash-lite`.

---

## Перезапуск Codespace (2026-09-27)

Codespace вимкнувся, кластер kind зник разом з усім, що робилось руками: образ офіційного MCP, ModelConfig Gemini з секретом, правки агентів, дані в Neo4j і Qdrant. Результати прогону B збережено тут і в ADR.

Що треба відновити після `make fix-egress`, `make fix-docker-acl`, `make run`:

1. Образ офіційного MCP: `docker build` і `kind load`, потім `kubectl apply -f lab4/qdrant-mcp-official.yaml`.
2. ModelConfig `gemini-gemini-3-1-flash-lite` з ключем Gemini, через kagent UI.
3. Анотації `reconcile=disabled` на обох агентах.
4. k8s-agent переключити на `gemini-gemini-3-1-flash-lite`.

## Підготовка прогону A: вирівнювання промптів

Порівняння файлів показало, що в `retrieval-agent-mcp-llmcpp.yaml` лишився старий промпт інгесту. З ним агент міг покласти в `vector_store` сирий YAML, а наш сервер ріже довгий текст на шматки і вбудовує все. Тоді порівнювались би два різні способи інгесту, а не MiniLM з nomic.

**Змінено в `retrieval-agent-mcp-llmcpp.yaml`:**

- Крок 4 інгесту тепер такий самий, як у B: один виклик `vector_store` на об'єкт, без сирого YAML, опис на 2-4 речення з kind, namespace і name на початку, у metadata є `key`.
- Гібридний пошук іде в `read-cypher` за `key` з metadata, як у B.

**Після змін промпти відрізняються лише:**

- назвами тулів: `qdrant-store` / `qdrant-find` у B, `vector_store` / `vector_find` в A;
- реченням про формат `<entry>` і ліміт 5 результатів, яке є лише в B, бо це формат саме офіційного сервера.

Поза промптом різні лише MCP-сервер у tools (`qdrant-mcp-official` у B, `qdrant-mcp` в A) і підпис у `description`, який моделі не передається.

**Свідоме рішення:** речення «Only the beginning of the text is embedded» залишено і в A, хоча для нашого сервера воно неправдиве: він вбудовує весь текст шматками. Воно змушує модель писати короткі описи, і тоді тексти в обох прогонах однакової форми.

Речення проти паралельних викликів k8s-agent не додано в жоден файл: прогін B пройшов без нього. Якщо додавати, то в обидва.

---

## Новий план: обидва прогони на повному корпусі

Після перезапуску прогін A проінгестили тим самим запитом, що й B, лише з `vector_store` замість `qdrant-store`:

```
Ingest these objects, one at a time: every kagent.dev Agent, ModelConfig,
MCPServer and RemoteMCPServer in namespace kagent. For each object ask
k8s-agent for its full YAML, write it to the graph, then store one
vector_store entry for it. When done, list every key you ingested.
```

Цього разу запит спрацював повністю: 14 об'єктів замість 4. Корпус став іншим, ніж у B, тож порівнювати напряму не можна.

**Рішення:** спершу прогін A на повному корпусі, потім прогін B заново тим самим запитом «every ...». Результати B на 4 об'єктах лишаються в журналі як попередній прогін.

### Прогін A: інгест

| Вимір | Значення |
|---|---|
| Точок у `abox-nomic` | 14, по одній на об'єкт, 768 вимірів; наш сервер нічого не різав |
| Нод у Neo4j | 14 |
| Ребер | `USES_MODEL` 7, `USES_TOOL` 10 |
| Час інгесту | не засічено |

Об'єкти: 7 Agent (argo-rollouts-conversion-agent, helm-agent, k8s-agent, kgateway-agent, observability-agent, promql-agent, retrieval-agent), 2 ModelConfig (default-model-config, gemini-gemini-3-1-flash-lite), 3 MCPServer (neo4j-mcp, qdrant-mcp, qdrant-mcp-official), 2 RemoteMCPServer (kagent-tool-server, kagent-grafana-mcp).

**Відхилення від промпту:** у metadata є kind, name і namespace, але немає `key`. Модель його пропустила. Гібридний пошук усе одно можливий, бо ключ складається з namespace і name.

**Стиль описів інший, ніж у B:** не проза, а перелік полів, наприклад «Agent kagent/helm-agent. Configuration: Declarative. Model: default-model-config. Tools: kagent-tool-server ...». Опис генерує модель, тож він щоразу трохи інший.

### Очікувані відповіді на повному корпусі

Змінилась лише H2. Решта відповідей ті самі, але пошук тепер вибирає з 14 точок, а не з 4.

| # | Очікувана відповідь |
|---|---|
| D1 | neo4j-mcp; тепер конкурує з qdrant-mcp і qdrant-mcp-official |
| D2 | default-model-config |
| P1 | k8s-agent; тепер конкурує з шістьма іншими агентами |
| P2 | kagent-tool-server |
| L1 | kagent-openai; ключ OPENAI_API_KEY, якщо модель його записала |
| L2 | http://kagent-tools.kagent:8084/mcp, якщо модель записала адресу в опис |
| H1 | kagent-tool-server та його можливості |
| H2 | **5 агентів** за графом: argo-rollouts-conversion-agent, helm-agent, k8s-agent, kgateway-agent, observability-agent |
| N1 | жодного |

Для L1 і L2 правильна відповідь залежить від того, чи потрапила деталь в опис. Якщо її там немає, чесна відповідь «не знайдено», і вона теж оцінюється як правильна.

---

---

## Відповіді на питання: почато з початку (2026-09-27)

Усі записані раніше відповіді обох прогонів видалено. Причини:

- Відповіді прогону B отримано на корпусі з 4 об'єктів, а тепер обидва прогони йдуть на повному корпусі.
- Відповіді прогону A поставлено в тій самій сесії, де йшов інгест: модель бачила всі YAML з інгесту, тож оцінки відповідей ненадійні.

**Правила для питань:**

1. Кожне питання в новому чаті з retrieval-agent. Не в сесії інгесту.
2. Після кожного питання перевіряти, що ідентифікатор сесії новий.
3. Дані тулів (аргументи, результати, score) брати з API kagent `/api/sessions/<id>/tasks`.

### Прогін A: відповіді

**D1. Which MCP server connects to Neo4j?** Очікувано: neo4j-mcp.

- Тули: `get-schema`, потім `vector_find` із запитом «MCP server that connects to Neo4j». `read-cypher` не викликався.
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
- Сесія `01a0e319-0a66-75e3-93a2-6053f7d96e87`.

**D2. Which model config uses OpenAI gpt-4.1-mini?** Очікувано: default-model-config.

- Тули: `get-schema`, потім `read-cypher`:
  ```
  MATCH (mc:ModelConfig) WHERE mc.model CONTAINS 'gpt-4.1-mini'
  RETURN mc.key, mc.model, mc.provider
  ```
  `vector_find` не викликався.
- Відповідь: `kagent/default-model-config`, OpenAI `gpt-4.1-mini`, джерело граф. Вигаданого немає.
- Оцінка: 2. Місце у векторному пошуку: не застосовно.
- Токени з UI: 11247 усього, 11130 вхідних, 117 вихідних.
- Сесія `01a0e31a-459d-7461-9201-47bf67c0695c`.

**Примітка:** модель і провайдер лежать у властивостях ноди ModelConfig, тож агент відповів із графа, без ембедингів. D2 не перевіряє якість векторного пошуку. Якщо в прогоні B агент теж піде в граф, D2 не розрізнить прогони.

**P1. My pod keeps crashing, which agent can troubleshoot it?** Очікувано: k8s-agent. Сесія `01a0e31b-4af1-7762-9ec3-8ef3e434da16`, дані з API.

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
- Відрив від другого місця лише 0.03, а всі score низькі (0.52-0.58). Правильний об'єкт на першому місці, але впевненість пошуку слабка.

**P2. Which component hands out service-mesh and network-policy tooling?** Очікувано: kagent-tool-server. Сесія `01a0e31e-f8fe-783f-b6ad-a2aa7a87dd35`.

- Тули: `get-schema`, потім `vector_find` із запитом «service-mesh network-policy tooling».
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
- Правильний об'єкт лише на 2-му місці, на 0.006 нижче за helm-agent. Усі п'ять score між 0.57 і 0.60, тобто nomic фактично не відрізнив потрібний опис від інших. Знайти правильну відповідь допомогла модель, а не ранжування.

**Для L1:** в описі default-model-config записано лише секрет `kagent-openai`, ключа `OPENAI_API_KEY` там немає. Правильна відповідь L1 у прогоні A: секрет kagent-openai, а щодо ключа «не знайдено».

**L1. Which Kubernetes secret and key hold the API key for the default model config?** Очікувано з опису: секрет kagent-openai, ключ «не знайдено». Сесія `01a0e320-2cdc-740d-ba65-d674fb4b007e`.

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
- Оцінка: 2 за правильність, обґрунтованість часткова. Якби відповідь спиралась лише на сховища, оцінка була б 1: секрет знайдено, ключ ні.
- Пошук спрацював добре: правильний об'єкт на 1-му місці, відрив 0.12.

**L2. At which HTTP endpoint is the kagent tool server reachable?** Очікувано зі сховищ: «не знайдено», бо адреси в описі немає. Сесія `01a0e322-1c8b-723e-ada6-74a15f119221`.

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
- Оцінка: 2 за правильність, але обґрунтованість «ні»: зі сховищ адресу взяти неможливо. Якби агент дотримався промпту, правильною відповіддю було б «не знайдено».
- Пошук спрацював: правильний об'єкт на 1-му місці, відрив 0.06.

**H1. Which tool server does the Kubernetes expert agent use, and what does it expose?** Очікувано: kagent-tool-server; Kubernetes, Cilium, Istio, Helm, Kubescape, Prometheus. Сесія `01a0e325-dbc7-756d-aec2-8fb867babaf0`.

- Тули, 3 виклики:
  1. `get-schema`.
  2. `read-cypher`: `MATCH (a:Agent {name: "k8s-agent"})-[r:USES_TOOL]->(t) RETURN t.name, labels(t)`, результат kagent-tool-server.
  3. `vector_find` із запитом «What does kagent-tool-server expose?».
- Топ-5 `vector_find`: 1 kagent-tool-server 0.787, 2 helm-agent 0.731, 3 k8s-agent 0.724, 4 kgateway-agent 0.705, 5 observability-agent 0.691.
- Відповідь: kagent-tool-server (з графа); Kubernetes management, Argo Rollouts, Cilium, Istio, Helm, Kubescape, Prometheus (з вектора). Кожен факт має вказане джерело, вигаданого немає.
- Оцінка: 2.
- Порядок зворотний до промпту: спершу граф, потім вектор. Те, що «Kubernetes expert agent» означає k8s-agent, модель вгадала з назви без пошуку. В описі k8s-agent стоїть «KubeAssist troubleshooting agent», слова «expert» там немає.

**H2. Which agents depend on the tool server that provides Helm and Prometheus tooling?** Очікувано: 5 агентів. Сесія `01a0e327-e489-7d3b-86bc-f90b15758f0a`.

- Тули, 3 виклики, у порядку з промпту:
  1. `get-schema`.
  2. `vector_find` із запитом «Helm and Prometheus tooling».
  3. `read-cypher`: `MATCH (a:Agent)-[:USES_TOOL]->(t:RemoteMCPServer {name: 'kagent-tool-server'}) RETURN a.key`.
- Топ-5 `vector_find`: 1 helm-agent 0.601, 2 kagent-tool-server 0.571, 3 promql-agent 0.533, 4 observability-agent 0.515, 5 argo-rollouts-conversion-agent 0.497.
- Відповідь: усі 5 агентів (observability-agent, kgateway-agent, helm-agent, argo-rollouts-conversion-agent, k8s-agent), з графа. Сервер визначено з вектора. Вигаданого немає.
- Оцінка: 2.
- Правильний об'єкт знову лише на 2-му місці, як у P2: helm-agent обходить його на 0.03. Модель однаково вибрала сервер, бо шукала саме «tool server», а не агента.

**N1. Which agent uses Anthropic Claude?** Очікувано: жодного. Сесія `01a0e329-1893-7a04-ad1c-7c7e174a8710`.

- Тули, 4 виклики:
  1. `vector_find` із запитом «Which agent uses Anthropic Claude?». У топ-5 лише агенти (0.57-0.63), Claude чи Anthropic не згадано в жодному.
  2. `get-schema`.
  3. `read-cypher`: пошук ModelConfig з `claude` у model або `anthropic` у provider, результат порожній. `CONTAINS` чутливий до регістру, тож провайдера «Anthropic» цей запит не знайшов би. Помилку перекрив наступний запит.
  4. `read-cypher`: усі пари Agent → ModelConfig. 7 агентів: 2 на Gemini, 5 на OpenAI.
- Відповідь: жодного агента з Claude немає. Перевірено обидва сховища, перелічено фактичних провайдерів. Вигаданого немає, у кластер агент не ходив.
- Оцінка: 2. Місце: не застосовно.
- Правило промпту «перш ніж казати, що чогось немає, виклич get-schema і read-cypher» виконано.

**Прогін A: питання завершено.** 9 із 9 з оцінкою 2. У P1, L1 і L2 агент звертався до k8s-agent. У L1 і L2 вирішальний факт узято з кластера, а не зі сховищ.

**Знахідка: Gemini ігнорує заборону в промпті.** У розділі Retrieve сказано: «Do not fetch manifests, do not delegate to another agent». Попри це в P1, L1 і L2 агент викликав `k8s-agent` і брав факти з живого кластера, коли їх бракувало у сховищах. Промпт не міняємо, щоб A і B лишались порівнюваними. Перевіряємо, чи повториться в B.

**Як діставати дані з API.** UI прокинута на `localhost:8080`, вона ж віддає API:

```bash
# список сесій: перевірити, що кожне питання в окремій сесії
curl -s "localhost:8080/api/sessions?user_id=admin@kagent.dev" | jq -c '.data[] | {id, name, agent_id, created_at}'
# виклики тулів і відповідь однієї сесії
curl -s "localhost:8080/api/sessions/<id>/tasks?user_id=admin@kagent.dev"
```

Токени з API не збігаються з тими, що показує UI: для D2 сума `usage` в API дає 8933, а UI показує 11247. Тому токени беремо лише з UI або не порівнюємо зовсім.

## Прогін B на повному корпусі

### Підготовка (перевірено 2026-09-27)

- `retrieval-agent`: generation 3, Ready, модель `gemini-gemini-3-1-flash-lite`, `reconcile=disabled`. Тули: neo4j-mcp, qdrant-mcp-official (`qdrant-store`, `qdrant-find`), k8s-agent. У промпті є `qdrant-find` і немає `vector_find`.
- `k8s-agent`: `gemini-gemini-3-1-flash-lite`, `reconcile=disabled`.
- Neo4j: 0 нод.
- Qdrant: лише `abox-nomic` (14 точок, 768 вимірів). `abox-minilm` ще не існує, сервер створить її при першому записі.
- Пам'ять поду `qdrant-mcp-official` до інгесту: `memory.peak` 289017856 байт, приблизно 276 MiB. Под працює 126 хв без перезапуску, тож пік після інгесту рахується від того самого старту.

### Інгест

Той самий запит «every ...» з `qdrant-store`. Сесія `01a0e333-50c9-7b22-b2ce-4d20e61abf8f`. Спершу в ній було «hello», потім запит на інгест.

| Вимір | Прогін B | Прогін A для порівняння |
|---|---|---|
| Об'єктів | 14, той самий набір | 14 |
| Точок у `abox-minilm` | 14, 384 виміри, без дублікатів | 14 |
| Нод у Neo4j | 14 | 14 |
| `USES_MODEL` | 7, одне хибне | 7 |
| `USES_TOOL` | 6 | 10 |
| Час | приблизно 1 хв 45 с, 14:11:42-14:13:27 UTC | не засічено |
| Пік пам'яті `qdrant-mcp-official` | 517 MiB, до інгесту 276 MiB | не застосовно |
| Виклики тулів | k8s-agent 16, write-cypher 14, qdrant-store 14 | |

Час узято з API: початок це мітка в UUIDv7 ідентифікатора задачі, кінець це `status.timestamp`.

**Що пішло не так у графі.** На запит про retrieval-agent k8s-agent повернув прозовий переказ промпту агента замість YAML: без `modelConfig` і без `tools`. Тому retrieval-agent:

- записав хибне ребро `USES_MODEL` на `default-model-config`, хоча в кластері агент на Gemini;
- не записав жодного зі своїх 3 ребер `USES_TOOL` (neo4j-mcp, qdrant-mcp-official, k8s-agent).

Бракує також ребра `observability-agent -> promql-agent`. Разом 4 відсутні `USES_TOOL`.

**Описи у векторі** цього разу написано прозою, `key` у metadata є. Але деталей менше, ніж в A:

- `kagent-tool-server`: лише «Kubernetes, Helm, and operational tools», без Cilium, Istio і Prometheus;
- `neo4j-mcp`: без образу і без bolt-адреси;
- `default-model-config`: без секрету;
- `retrieval-agent`: хибне «uses default-model-config (gpt-4.1-mini)».

**Наслідок для порівняння.** Корпуси A і B не ідентичні: описи генерує модель, і щоразу вони виходять різні. Тепер P2 (Cilium, Istio), H2 (Prometheus), L1 (секрет) і L2 (адреса) залежать від деталей, яких в описах B немає. Чесна відповідь зі сховищ на ці питання в B: «не знайдено» або часткова. Це треба враховувати у висновках, щоб не приписати MiniLM вину моделі, яка писала описи.

### Прогін B: відповіді

**Score для B.** Офіційний `qdrant-find` повертає лише порядок, без score. Score рахуємо окремо скриптом `lab4/score-minilm.py`: він у поді `qdrant-mcp-official` вбудовує той самий запит тією ж MiniLM і шукає в `abox-minilm`. Порядок збігається з тим, що повернув сервер.

```bash
P=$(kubectl get pod -n kagent -o name | grep qdrant-mcp-official)
kubectl cp lab4/score-minilm.py kagent/${P#pod/}:/tmp/score.py -c mcp-server
kubectl exec -n kagent $P -c mcp-server -- python /tmp/score.py "<запит, який агент передав у qdrant-find>"
```

Абсолютні score MiniLM і nomic між собою не порівнюються: це різні моделі з різною шкалою. Порівнюємо місце і відрив від другого.

Скрипт завантажує модель ще раз у тому самому контейнері, тож `memory.peak` після цього вже не відображає роботу сервера. Пік інгесту (517 MiB) записано до першого запуску скрипта.

**D1. Which MCP server connects to Neo4j?** Сесія `01a0e33c-cc0a-7b63-9fea-760da33317b1`.

- Тули, 1 виклик: `qdrant-find` із запитом «MCP server connecting to Neo4j». Ні `get-schema`, ні `read-cypher`.
- Топ-5: 1 neo4j-mcp 0.647, 2 kagent-grafana-mcp 0.365, 3 kagent-tool-server 0.296, 4 qdrant-mcp 0.289, 5 qdrant-mcp-official 0.281.
- Відповідь: neo4j-mcp, «provides Neo4j graph database capabilities». Вигаданого немає. Образу і bolt-адреси у відповіді немає, бо їх немає в описі B.
- Оцінка: 2. Відрив 0.28, в A він був 0.13, тобто MiniLM відокремив правильний об'єкт впевненіше.

**D2. Which model config uses OpenAI gpt-4.1-mini?** Сесія `01a0e33e-06b7-7d8a-8703-5543e02a771c`.

- Тули, 1 виклик: `qdrant-find` із запитом «OpenAI gpt-4.1-mini». Граф не використано.
- Топ-5: 1 default-model-config 0.654, 2 observability-agent 0.375, 3 retrieval-agent 0.281, 4 promql-agent 0.267, 5 kgateway-agent 0.251.
- Відповідь: `kagent/default-model-config`, джерело вектор. Вигаданого немає.
- Оцінка: 2. Відрив 0.28.
- В A агент відповів на D2 з графа, у B з вектора. Тож D2 розрізнив прогони лише за вибором сховища, а не за якістю пошуку. У B опис retrieval-agent на 3-му місці містить хибне «uses default-model-config», але на відповідь це не вплинуло.

**P1. My pod keeps crashing, which agent can troubleshoot it?** Сесія `01a0e33f-741c-7817-ab79-9e2f5a57b078`.

- Тули, 1 виклик: `qdrant-find` із запитом «pod troubleshooting agent». k8s-agent не викликано, в A він був.
- Топ-5: 1 k8s-agent 0.480, 2 helm-agent 0.435, 3 promql-agent 0.407, 4 kagent-tool-server 0.396, 5 observability-agent 0.387.
- Відповідь: k8s-agent, «general-purpose Kubernetes expert … troubleshooting», з вектора. Також згадано helm-agent і observability-agent як агентів із «troubleshooting capabilities». Для helm-agent це є в описі, для observability-agent ні: там лише моніторинг і метрики. Невелике перебільшення, але не вигаданий факт.
- Оцінка: 2. Відрив 0.045, в A він був 0.03. Правильний об'єкт першим в обох прогонах, але впевненість слабка в обох.

**P2. Which component hands out service-mesh and network-policy tooling?** Сесія `01a0e346-a57a-781e-a907-a1f340361824`.

- Тули, 2 виклики: `qdrant-find` із запитом «service-mesh and network-policy tooling», потім `read-cypher` на вхідні `USES_TOOL` до kagent-tool-server.
- Топ-5: 1 kagent-tool-server 0.314, 2 observability-agent 0.312, 3 argo-rollouts-conversion-agent 0.308, 4 kgateway-agent 0.294, 5 helm-agent 0.289.
- Відповідь: kagent-tool-server, правильно. Але в описі B немає ні service mesh, ні network policy, ні Cilium, ні Istio, лише «Kubernetes, Helm, and operational tools». Зв'язок із питанням модель вивела сама: це єдиний сервер тулів у результатах, і граф показує, що ним користуються 5 агентів.
- Оцінка: 2 за правильність, обґрунтованість часткова.
- Перше місце випадкове: відрив 0.002, всі п'ять між 0.29 і 0.31. MiniLM не знайшов у тексті нічого про питання, бо там цього немає. В A потрібний об'єкт був на 2-му місці, але в його описі були Cilium та Istio, тож відповідь спиралась на текст.

**L1. Which Kubernetes secret and key hold the API key for the default model config?** Сесія `01a0e347-cb98-70a6-8ce6-20f2fbe82523`.

- Тули, 2 виклики: `qdrant-find` із запитом «API key for default model config», потім `k8s_agent` з запитом «get modelconfig/default-model-config -n kagent -o yaml». Це живе читання кластера.
- Топ-5: 1 default-model-config 0.508, 2 argo-rollouts-conversion-agent 0.260, 3 promql-agent 0.247, 4 helm-agent 0.246, 5 kgateway-agent 0.234.
- Відповідь: `kagent-openai`, `OPENAI_API_KEY`. Факт правильний, агент чесно пише, що взяв його з кластера. В описі B немає ні секрету, ні ключа, тож обґрунтованість «ні». В A секрет був в описі, а ключ прийшов із кластера.
- Оцінка: 2 за правильність. Пошук спрацював: відрив 0.25.
- Порушення заборони «do not delegate» повторилось і в B.

**L2. At which HTTP endpoint is the kagent tool server reachable?** Сесія `01a0e348-b731-7617-a844-83ece7122093`.

- Тули, 2 виклики: `qdrant-find` із запитом «kagent tool server endpoint», потім `k8s_agent` з запитом «get RemoteMCPServer kagent/kagent-tool-server -o yaml». Це живе читання кластера.
- Топ-5: 1 kagent-tool-server 0.659, 2 helm-agent 0.572, 3 kgateway-agent 0.569, 4 argo-rollouts-conversion-agent 0.551, 5 k8s-agent 0.546.
- Відповідь: `http://kagent-tools.kagent:8084/mcp`, з кластера, агент це вказав. Адреси немає в описах ні A, ні B. Результат такий самий, як в A.
- Оцінка: 2 за правильність, обґрунтованість «ні». Пошук: відрив 0.09, в A був 0.06.

**H1. Which tool server does the Kubernetes expert agent use, and what does it expose?** Сесія `01a0e349-1c81-75ed-8c35-bdc91042d16f`.

- Тули, 2 виклики, у порядку з промпту: `qdrant-find` із запитом «Kubernetes expert agent tool server», потім `read-cypher` по USES_TOOL від `kagent/k8s-agent`, результат kagent-tool-server.
- Топ-5: 1 kagent-tool-server 0.731, 2 k8s-agent 0.712, 3 argo-rollouts-conversion-agent 0.602, 4 helm-agent 0.577, 5 kgateway-agent 0.560. Обидва потрібні об'єкти у двох верхніх рядках.
- Відповідь: kagent-tool-server, «Kubernetes, Helm, and operational tools». Точно за текстом, вигаданого немає.
- Оцінка: 1. Сервер правильний, але зі списку Kubernetes, Argo Rollouts, Cilium, Istio, Helm, Kubescape, Prometheus названо лише Kubernetes і Helm, бо решти немає в описі B.
- На відміну від A, «Kubernetes expert agent» знайдено через вектор, а не вгадано: в описі B ці слова є.

**H2. Which agents depend on the tool server that provides Helm and Prometheus tooling?** Сесія `01a0e349-a644-79d7-8ca9-d65fde7fcf07`.

- Тули, 2 виклики, у порядку з промпту: `qdrant-find` із запитом «Helm and Prometheus tooling», потім `read-cypher` на вхідні `USES_TOOL` до kagent-tool-server.
- Топ-5: 1 promql-agent 0.463, 2 helm-agent 0.446, 3 kagent-tool-server 0.427, 4 observability-agent 0.265, 5 argo-rollouts-conversion-agent 0.254.
- Відповідь: усі 5 агентів із графа. Вигаданих агентів немає.
- Оцінка: 2 за правильність, обґрунтованість часткова. Агент пише, що kagent-tool-server «provides the Helm and Prometheus tooling» і що це взято з вектора. Але в описі B є лише Helm, Prometheus там немає. Вибір сервера правильний, бо це єдиний сервер тулів у результатах.
- Правильний об'єкт на 3-му місці, в A був на 2-му. Вище стоять агенти, чиї описи містять «Prometheus» (promql-agent) і «Helm» (helm-agent).

**N1. Which agent uses Anthropic Claude?** Сесія `01a0e34b-ad3c-77ff-8d6c-7f6ea8855632`.

- Тули, 3 виклики: `qdrant-find` «Agent using Anthropic Claude model», `read-cypher` по всіх парах Agent → ModelConfig, `qdrant-find` «Anthropic Claude model configuration».
- Відповідь: жодного. Названо обидві ModelConfig, OpenAI і Gemini. Вигаданого немає, у кластер агент не ходив.
- Оцінка: 2. Місце: не застосовно.
- `get-schema` не викликано, хоча промпт вимагає цього перед відповіддю «немає». В A агент його викликав. Хибне ребро retrieval-agent → default-model-config було в результаті `read-cypher`, але у відповідь не потрапило, бо агент не перелічував розподіл агентів за моделями.
- Перша спроба (сесія `01a0e349-a644-79d7-8ca9-d65fde7fcf07`) була задана в тому самому чаті, що й H2, тож її не рахуємо. Відповідь там була така сама, і `get-schema` теж пропущено.

**Прогін B: питання завершено.**

### Підсумок A проти B

| | A: nomic, наш MCP | B: MiniLM, офіційний MCP |
|---|---|---|
| Сума оцінок | 18 з 18 | 17 з 18, H1 = 1 |
| Правильний об'єкт першим, з питань із векторним пошуком | 5 з 7: P2 і H2 на 2-му місці | 7 з 8: H2 на 3-му |
| Відповідь повністю зі сховищ | 7 з 9 | 5 з 9 |
| Звертання до k8s-agent | P1, L1, L2 | L1, L2 |
| Викликів тулів разом | 27 | 16 |
| Пік пам'яті MCP-пода | 42 MiB за весь час з 11:52, з інгестом і питаннями A; модель поза подом | 517 MiB |

Що з цього випливає:

- **Ранжування.** У прямих питаннях (D1, D2, L1) MiniLM відокремлює правильний об'єкт з відривом 0.25-0.28, nomic з відривом 0.12-0.13. У перефразованих питаннях обидві моделі ледь відрізняють правильний об'єкт від інших (P1: 0.03 і 0.045).
- **Корпус важить більше за модель ембедингів.** Описи B бідніші: немає Cilium, Istio, Prometheus, секрету, адреси. Через це B втратив бал на H1, а P2 і H2 відповів правильно, але без опори на текст. Ці втрати дала модель, яка писала описи на інгесті, а не MiniLM.
- **Кластер замість сховищ.** L2 не міг відповісти зі сховищ жоден прогін. На L1 A мав у тексті половину відповіді, B нічого. В обох прогонах агент добирав відсутнє з кластера всупереч промпту.
- **Інгест.** B записав граф із помилками: 4 ребра `USES_TOOL` відсутні, 1 `USES_MODEL` хибне. Причина в k8s-agent, який повернув переказ замість YAML. На питання це майже не вплинуло.

## Рішення (пункт 8)

**Залишаємо наш `qdrant-mcp`** (`vector_store` / `vector_find`, nomic через llama.cpp). Офіційний `qdrant-mcp-official` у retrieval-agent не ставимо. Рішення прийнято 2026-09-27, в ADR статус Accepted.

Чому:

1. **Якість відповідей однакова:** 18 з 18 проти 17 з 18. Усе, що B втратив або відповів без опори на текст, пояснюється бідними описами з інгесту. Ці описи пише модель агента, а не модель ембедингів.
2. **MiniLM краще ранжує прямі питання:** відрив 0.25-0.28 проти 0.12-0.13. Жодної відповіді це не змінило.
3. **Вартість на користь нашого:** пік пам'яті MCP-пода 42 MiB проти 517 MiB. Офіційний працює на локальному образі, який зникає після перезапуску Codespace.
4. **Довгі тексти:** наш сервер ріже їх на шматки, MiniLM бачить лише перші 128 токенів.

Обмеження: по одному прогону, 14 об'єктів, 9 питань; корпуси вийшли різні; Gemini порушував правила промпту в обох прогонах. Щоб порівняти саме моделі ембедингів, треба проіндексувати однакові фіксовані тексти через обидва сервери і забрати k8s-agent з тулів на час питань.
