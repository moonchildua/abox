import sys, os
from fastembed import TextEmbedding
from qdrant_client import QdrantClient
q = sys.argv[1]
m = TextEmbedding(os.environ.get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
v = list(m.query_embed([q]))[0].tolist()
c = QdrantClient(url=os.environ["QDRANT_URL"])
r = c.query_points(os.environ["COLLECTION_NAME"], query=v, using="fast-all-minilm-l6-v2", limit=5, with_payload=True)
for i, p in enumerate(r.points, 1):
    print(i, p.payload["metadata"]["name"], round(p.score, 3))
