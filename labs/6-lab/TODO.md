<!-- 
1. Розгорнути abox з гілки otel. Ознайомитись з сетапом https://opentelemetry.io/docs/demo/architecture/ 

2. Провести випробування demo продукту та занотувати ваші питання та спостереження з точки зору o11y

3. Опціонально*: додати ваших агентів та сетап kagent до системи o11y 
-->

OpenTelemetry Demo
Astronomy online shop with some services that are written in different Programming languadges 
+
OpenTelemetry 

1. spin up abox
2. ngrok-operator stacks . neet to add secrets
 - create account, copy AUTHTOKEN, create API_KEY
    2.1 
    
    ```
    kubectl -n ngrok-operator create secret generic ngrok-operator-credentials \
  --from-literal=API_KEY=<api key> \
  --from-literal=AUTHTOKEN=<authtoken>
```

3. agentgateway-llm

```
  - add secrets

  kubectl -n agentgateway-system create secret generic agentgateway-llm-secrets \
  --from-literal=GEMINI_API_KEY="" \
  --from-literal=TRIAGE_LLM_KEY="$(openssl rand -hex 24)"

kubectl -n agentgateway-system get secret agentgateway-llm-secrets \
  -o jsonpath='{.data.TRIAGE_LLM_KEY}' | base64 -d

kubectl port-forward -n agentgateway-system deploy/agentgateway-llm 15000:15000
```

4. configure mlfow 

```
https://obscure-memory-v65r5vjr4g43p6j4-8080.app.github.dev/ - shop
https://obscure-memory-v65r5vjr4g43p6j4-8080.app.github.dev/feature - Flagd Configurator
loadGeneratorTraffic - off - then I started to see my trace
imageSlowLoad - off - image epears very slowly and you can see execution time 10s.... state in progress -  upstream_cluster is image provider
```


OTEL
opamp-server
```
kubectl port-forward -n otel-demo svc/opamp-server 4321:4321
```


how to setup allerting in MLflow?
