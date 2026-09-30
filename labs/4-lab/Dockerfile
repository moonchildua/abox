# LAB4 -- image for the official Qdrant MCP server from github.com/qdrant/mcp-server-qdrant)
# with sentence-transformers/all-MiniLM-L6-v2 model
#
#   docker build -t mcp-server-qdrant:local
#   kind load docker-image mcp-server-qdrant:local --name abox
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv
RUN uv pip install --system --no-cache-dir mcp-server-qdrant==0.8.1

ENV FASTEMBED_CACHE_PATH=/models
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/all-MiniLM-L6-v2')"

EXPOSE 8000

ENV QDRANT_URL=""
ENV COLLECTION_NAME="default-collection"
ENV EMBEDDING_MODEL="sentence-transformers/all-MiniLM-L6-v2"

CMD ["mcp-server-qdrant"]
