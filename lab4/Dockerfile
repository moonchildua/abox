# LAB4 -- image for the official Qdrant MCP server. Upstream publishes no
# image, only the PyPI package and this Dockerfile (Dockerfile in
# github.com/qdrant/mcp-server-qdrant), so it is built locally and loaded into
# the kind nodes:
#
#   docker build -t mcp-server-qdrant:local lab4/
#   kind load docker-image mcp-server-qdrant:local --name abox
#
# Differences from upstream: the package version is pinned, and the embedding
# model is downloaded at build time into /models so a pod starts without
# reaching HuggingFace. kmcp restarts the stdio server on every session
# teardown, and a re-download on each restart is ~14s of "connection refused".
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv
RUN uv pip install --system --no-cache-dir mcp-server-qdrant==0.8.1

# fastembed reads the model from FASTEMBED_CACHE_PATH; bake it in.
ENV FASTEMBED_CACHE_PATH=/models
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/all-MiniLM-L6-v2')"

EXPOSE 8000

ENV QDRANT_URL=""
ENV COLLECTION_NAME="default-collection"
ENV EMBEDDING_MODEL="sentence-transformers/all-MiniLM-L6-v2"

CMD ["mcp-server-qdrant"]
