1. Chatbot

sample question works

What product is the most expensive?
Custom question - Error: 500 Server Error: Internal Server Error for url: http://agent:8010/prompt

2. Turn on Jaeger

exclude HelmRelease from Flux reconcile
```
kubectl -n otel-demo annotate helmrelease opentelemetry-demo \
  kustomize.toolkit.fluxcd.io/reconcile=disabled


kubectl -n otel-demo patch helmrelease opentelemetry-demo --type merge \
  -p '{"spec":{"values":{"jaeger":{"enabled":true}}}}'
```
SHOP_URL/jaeger/ui/ - 

3. phoenix
```
kubectl -n mlflow annotate helmrelease otel-collector \
  kustomize.toolkit.fluxcd.io/reconcile=disabled

read -s KEY
kubectl -n otel-demo patch helmrelease opentelemetry-demo --type merge -p "
spec:
  values:
    opentelemetry-collector:
      config:
        exporters:
          otlp_grpc/phoenix:
            endpoint: phoenix-svc.phoenix.svc.cluster.local:4317
            tls:
              insecure: true
            headers:
              authorization: Bearer $KEY
        service:
          pipelines:
            traces:
              exporters: [otlp_grpc/jaeger, debug, span_metrics, otlp_grpc/mlflow-bridge, otlp_grpc/phoenix]
"
```

Problem 
otlp_grpc/phoenix: rpc error: code = Unauthenticated
Solve
create an API Keys
PHOENIX_API_KEY=



- faces with otel collector soft limit 
mlflow and Phoenix have trace, Jaeger no 
trace_exporter: Failed to export span batch due to timeout, max retries or shutdown


# Instalation LAB6&7

Demo shop & K8S-agent send traces into OpenTelemetry Collector. Every Trace tool has the same traces.
```
Shop services (agent, chatbot, cart, ...)/kagent
        │
        │  trace
        ▼
otel-collector-agent from otel-demo
        │
        ├── copy ──► Jaeger
        │
        └── copy ──► otel-collector mlflow  (otel-collector, namespace mlflow) - need to add experiments + name
        │
        └── copy ──► Phoenix 
```
| Trace | Agent | Instrumentation | What it contains |
|---|---|---|---|
| `71f62ce3195d51f762af444e6a4cdc6a` | Astronomy Shop chatbot (LangGraph) | Traceloop / OpenLLMetry | 23 spans, 4 services; prompts, responses, tool calls|
| `d6f3f08ae6e54fea1c3521ca62acbbee` | kagent `k8s-agent` | Google ADK | 8 spans, 2 services; token usage, model, tool input and output |


# Comparison

OpenTelemetry gives possibility to collect traces, spans and `gen_ai.*` attributes from different apps and different programming languages.

**Jaeger** provides detailed nested span view but not so undestendable. It shows service boundaries and resource attributes. There is needed the GenAI information but the veiw(display) as tag. Nevertheless it has whole information but it cant calculate tokens sum across trace. It helps to understand what happened in the system. Which service and node handled a span, where the delay or error is, how the agent's tool call continues into HTTP, gRPC, and SQL spans of other services. 

**MLflow** based on traceID. Nice graph view. It provides excact costs per trace and LLM call. there is Inputs/Outputs view, including the ADK-specific attributes used by kagent. Exact cost and token totals per trace and per LLM call, a separate experiment per trace source, and evaluation tooling next to the traces.

**Phoenix**  dublicate `gen_ai.*` into own format (OpenInference). for example
gen_ai.operation.name = execute_tool	openinference.span.kind = TOOL
gen_ai.tool.name	tool.name
gen_ai.tool.call.id	tool.id
gen_ai.tool.description	tool.description

The conversation with system prompt, user message, tool calls, and tool definitions, a token breakdown per span, and filtering by span kind (`llm`, `tool`, `agent`).

**Phoenix**  & **MLflow**  both recognize agent, LLM, and tool spans, aggregate token usage, calculate cost and group traces into sessions. They provide better GenAI obervation especially token and sum informations.

On my opinion all three tracing tools are good depence on our needs and functionaity.
