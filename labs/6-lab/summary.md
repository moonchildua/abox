# LAB6
Demo - https://opentelemetry.io/docs/demo/architecture/  

## Components:
Astronomy online shop with some services that are written in different Programming languadges(JavaScript, Go, Python, .NET, Rust and Java) with its own observability stack(Jaeger,Prometheus,OpenSearch,Grafana and otel-collectors)

In cluster also present  **Phoenix** and  **MLflow**


Every Astronomy online shop service connects OpenTelemetry SDK. Every purchase has one traceID with service's spanID that OpenTelemetry SDK creates.

There is a load-generator (Locust) that imitate online clients.
also edpoints /feature/ where you can play with flagd configuration and breake functinality
 Agent, chatbot and mcp, its genAI part of shop.


Deployed abox from `feat/otel-demo` with mentioned customised demo
in abox project we turn off some services

```
    jaeger:
      enabled: false
    prometheus:
      enabled: false
    grafana:
      enabled: false
    opensearch:
      enabled: false
```

## Mlflow configure
But we send trace to otel-collector in Mlflow ns 

We need to create Experiments in  Mlflow to receive trace.
its very important to create 
exist Default = 0
create test to receive ExperimentsID= 1

for triage-core ExperimentsID= 2
for otel-demo ExperimentsID = 3


## default Schema

```
Shop services
        │
        │  trace
        ▼
otel-collector-agent from otel-demo
        │   
        └── copy ──► otel-collector mlflow  (otel-collector, namespace mlflow)
                               │
                               └── copy ──► MLflow
```


Sampling is not configured on demo, it means that we write all trace