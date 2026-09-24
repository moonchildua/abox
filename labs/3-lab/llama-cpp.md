## LLama.cpp server
llama.cpp lets you run LLM locally on your device with minimal setup and state-of-the-art performance.


install llama.cpp https://llama-cpp.com/

create folder for models
```
export LLAMA_CACHE="$HOME/models"
```

run llama with needed model
```
llama serve -hf nomic-ai/nomic-embed-text-v1.5-GGUF:Q8_0 --embedding --port 8080
llama serve -hf ggml-org/embeddinggemma-300M-GGUF:Q8_0 --embedding --port 8081
llama serve -hf Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0 --embedding --pooling last -ub 8192 --port 8082
```