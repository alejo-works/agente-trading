"""
Cliente ChromaDB — Motor del RAG.
Gestiona la conexión y las colecciones de documentos.
"""
import chromadb
from chromadb.config import Settings
from loguru import logger
import os

# Directorio donde se persiste la base de datos vectorial
CHROMA_PATH = os.getenv("CHROMA_PATH", "./chroma_db")


def get_chroma_client() -> chromadb.ClientAPI:
    """Retorna cliente ChromaDB persistente."""
    client = chromadb.PersistentClient(
        path=CHROMA_PATH,
        settings=Settings(anonymized_telemetry=False)
    )
    logger.info(f"ChromaDB conectado en: {CHROMA_PATH}")
    return client


def get_or_create_collection(name: str) -> chromadb.Collection:
    """Obtiene o crea una colección en ChromaDB."""
    client = get_chroma_client()
    collection = client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"}
    )
    logger.info(f"Colección '{name}': {collection.count()} documentos")
    return collection


# Colecciones del sistema
COLLECTIONS = {
    "ftmo_rules":   "Reglas y límites de la cuenta FTMO",
    "strategies":   "Documentación de las 3 estrategias de trading",
    "trade_history":"Historial de operaciones para RL",
}
