## LLama.cpp server
llama.cpp lets you run LLM locally on your device with minimal setup and state-of-the-art performance.


install llama.cpp https://llama-cpp.com/

create folder for models
```
export LLAMA_CACHE="$HOME/models"
```

run llama with needed model
```
llama serve -hf nomic-ai/nomic-embed-text-v1.5-GGUF:Q8_0 --embedding
```