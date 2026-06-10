import logging
import uuid

from sentence_transformers import SentenceTransformer
from sqlalchemy import select, text

from src.ai_newsletter.database.engine import async_session
from src.ai_newsletter.models.models import Digest, DigestCache

logger = logging.getLogger(__name__)
_embedder: SentenceTransformer | None = None


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer("BAAI/bge-small-en-v1.5")
    return _embedder


async def get_cached_digest(topic: str, threshold: float = 0.82):
    query_vec = str(_get_embedder().encode(topic, normalize_embeddings=True).tolist())

    async with async_session() as db:
        stmt = text("""
        SELECT digest_id, topic, 1 - (topic_embedding <=> :vec) AS similarity
        FROM digest_cache
        ORDER BY topic_embedding <=> :vec
        LIMIT 1
        """)
        result = await db.execute(stmt, {"vec": query_vec})
        row = result.first()

        if row and row.similarity >= threshold:
            digest_stmt = select(Digest).where(
                Digest.id == row.digest_id, Digest.status == "ready"
            )

            digest = (await db.execute(digest_stmt)).scalar_one_or_none()

            if digest:
                logger.info(f"Cache hit ({row.similarity:.3f}) for: {topic}")
                return {
                    "digest_id": str(digest.id),
                    "content": digest.content,
                    "extra_data": digest.extra_data,
                    "cached_topic": row.topic,
                    "similarity": round(row.similarity, 3),
                }
        return None


async def save_to_cache(topic: str, digest_id: str):
    vec = _get_embedder().encode(topic, normalize_embeddings=True).tolist()

    async with async_session() as db:
        await db.execute(
            DigestCache.__table__.insert().values(
                topic=topic,
                topic_embedding=vec,
                digest_id=uuid.UUID(digest_id),
            )
        )
        await db.commit()
        logger.info(f"Cached topic: {topic} -> {digest_id}")
