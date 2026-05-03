"""FastAPI-native dependency providers.

Replaces the AppContainer with module-level ``@lru_cache`` singleton
functions that FastAPI can depend on directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING

from loguru import logger

from app.config import config
from app.infrastructure import checkpoint_saver
from app.infrastructure.knowledge import (
    DashScopeEmbeddings,
    DocumentSplitterService,
    VectorIndexService,
    VectorSearchService,
    VectorStoreManager,
)
from app.platform.persistence import (
    agent_feedback_repository,
    agent_run_repository,
    aiops_run_repository,
    chat_tool_event_repository,
    conversation_repository,
    indexing_task_repository,
    scene_repository,
    tool_policy_repository,
    workspace_repository,
)

if TYPE_CHECKING:
    from app.agent_runtime import AgentRuntime, ToolCatalog, ToolExecutor
    from app.application.aiops_application_service import AIOpsApplicationService
    from app.application.chat import RagAgentService
    from app.application.chat_application_service import ChatApplicationService
    from app.application.indexing import IndexingTaskService
    from app.application.native_agent_application_service import NativeAgentApplicationService


# ---------------------------------------------------------------------------
# Health DTO
# ---------------------------------------------------------------------------


@dataclass
class ServiceHealth:
    """Core dependency health status."""

    status: str
    message: str


# ---------------------------------------------------------------------------
# Infrastructure providers
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_embedding_service() -> DashScopeEmbeddings:
    """Return the singleton DashScope embeddings service."""
    logger.info("Initializing DashScope Embeddings service...")
    return DashScopeEmbeddings(
        api_key=config.dashscope_api_key,
        model=config.dashscope_embedding_model,
        dimensions=1024,
    )


@lru_cache(maxsize=1)
def get_vector_store_manager() -> VectorStoreManager:
    """Return the singleton VectorStore manager."""
    logger.info("Initializing VectorStore manager...")
    return VectorStoreManager(
        embedding_service=get_embedding_service(),
    )


@lru_cache(maxsize=1)
def get_vector_search_service() -> VectorSearchService:
    """Return the singleton VectorSearch service."""
    return VectorSearchService(
        embedding_service=get_embedding_service(),
    )


@lru_cache(maxsize=1)
def get_document_splitter_service() -> DocumentSplitterService:
    """Return the singleton DocumentSplitter service."""
    return DocumentSplitterService()


@lru_cache(maxsize=1)
def get_vector_index_service() -> VectorIndexService:
    """Return the singleton VectorIndex service."""
    return VectorIndexService(
        document_splitter_service=get_document_splitter_service(),
        vector_store_manager=get_vector_store_manager(),
    )


# ---------------------------------------------------------------------------
# Application-service providers (lazy imports for heavy modules)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_rag_agent_service() -> RagAgentService:
    """Return the singleton RAG Agent runtime service."""
    logger.info("Initializing RAG Agent service...")
    from app.application.chat import RagAgentService

    return RagAgentService(
        streaming=True,
        checkpointer=checkpoint_saver,
    )


@lru_cache(maxsize=1)
def get_indexing_task_service() -> IndexingTaskService:
    """Return the singleton IndexingTask application service."""
    from app.application.indexing import IndexingTaskService

    return IndexingTaskService(
        repository=indexing_task_repository,
        vector_indexer_provider=lambda: get_vector_index_service(),
        max_retries_provider=lambda: config.indexing_task_max_retries,
    )


@lru_cache(maxsize=1)
def get_tool_catalog() -> ToolCatalog:
    """Return the singleton native Agent tool catalog."""
    from app.agent_runtime import ToolCatalog

    return ToolCatalog()


@lru_cache(maxsize=1)
def get_tool_executor() -> ToolExecutor:
    """Return the singleton native Agent tool executor."""
    from app.agent_runtime import ToolExecutor, ToolPolicyRepositoryAdapter

    return ToolExecutor(
        policy_store=ToolPolicyRepositoryAdapter(tool_policy_repository),
    )


@lru_cache(maxsize=1)
def get_agent_runtime() -> AgentRuntime:
    """Return the singleton native SRE Agent Runtime."""
    from app.agent_runtime import AgentRuntime

    return AgentRuntime(
        tool_catalog=get_tool_catalog(),
        tool_executor=get_tool_executor(),
    )


@lru_cache(maxsize=1)
def get_chat_application_service() -> ChatApplicationService:
    """Return the singleton Chat application service."""
    from app.application.chat_application_service import ChatApplicationService

    return ChatApplicationService(
        rag_agent_service=get_rag_agent_service(),
        conversation_repository=conversation_repository,
        chat_tool_event_repository=chat_tool_event_repository,
    )


@lru_cache(maxsize=1)
def get_aiops_application_service() -> AIOpsApplicationService:
    """Return the singleton AIOps application service."""
    from app.application.aiops_application_service import AIOpsApplicationService

    return AIOpsApplicationService(
        agent_runtime=get_agent_runtime(),
        aiops_run_repository=aiops_run_repository,
        conversation_repository=conversation_repository,
        workspace_repository=workspace_repository,
        scene_repository=scene_repository,
    )


@lru_cache(maxsize=1)
def get_native_agent_application_service() -> NativeAgentApplicationService:
    """Return the singleton NativeAgent application service."""
    from app.application.native_agent_application_service import (
        NativeAgentApplicationService,
    )

    return NativeAgentApplicationService(
        agent_runtime=get_agent_runtime(),
        tool_catalog=get_tool_catalog(),
        workspace_repository=workspace_repository,
        scene_repository=scene_repository,
        tool_policy_repository=tool_policy_repository,
        agent_run_repository=agent_run_repository,
        agent_feedback_repository=agent_feedback_repository,
    )


# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------


def initialize_services() -> None:
    """Initialize services required at application startup.

    Currently triggers the VectorStore / Milvus connection so that any
    schema-mismatch problems surface before the app starts accepting
    traffic.
    """
    from app.core.milvus_client import milvus_manager

    # Ensure Milvus connection and collection are ready.
    milvus_manager.connect()
    # Eagerly build the vector store manager (depends on embeddings).
    _ = get_vector_store_manager()


async def shutdown_services() -> None:
    """Gracefully shut down runtime services.

    Called during FastAPI ``shutdown`` event.  Cleans up resources that
    hold open connections or background tasks, then clears all cached
    provider singletons so they are not reused across process restarts
    (e.g. in a ``--reload`` development server).
    """
    if get_rag_agent_service.cache_info().currsize > 0:
        await get_rag_agent_service().cleanup()

    # Close Milvus connections.
    from app.core.milvus_client import milvus_manager

    milvus_manager.close()

    # Evict every cached provider so a fresh set is created on next access.
    get_embedding_service.cache_clear()
    get_vector_store_manager.cache_clear()
    get_vector_search_service.cache_clear()
    get_document_splitter_service.cache_clear()
    get_vector_index_service.cache_clear()
    get_rag_agent_service.cache_clear()
    get_indexing_task_service.cache_clear()
    get_tool_catalog.cache_clear()
    get_tool_executor.cache_clear()
    get_agent_runtime.cache_clear()
    get_chat_application_service.cache_clear()
    get_aiops_application_service.cache_clear()
    get_native_agent_application_service.cache_clear()


def get_service_health() -> dict[str, ServiceHealth]:
    """Return a health summary of core dependencies.

    Uses ``cache_info`` to check whether a provider has been called
    (i.e. the service has been initialized) without triggering lazy
    initialization itself.
    """
    embedding_ready = get_embedding_service.cache_info().currsize > 0
    vector_store_ready = (
        get_vector_store_manager.cache_info().currsize > 0
        and get_vector_store_manager().is_initialized
    )
    rag_ready = get_rag_agent_service.cache_info().currsize > 0
    aiops_ready = get_aiops_application_service.cache_info().currsize > 0
    checkpoint_ready = checkpoint_saver is not None

    return {
        "embedding": ServiceHealth(
            status="ready" if embedding_ready else "not_initialized",
            message="Embedding service initialized"
            if embedding_ready
            else "Embedding service not yet initialized",
        ),
        "vector_store": ServiceHealth(
            status="ready" if vector_store_ready else "not_initialized",
            message="VectorStore initialized"
            if vector_store_ready
            else "VectorStore not yet initialized",
        ),
        "rag_agent": ServiceHealth(
            status="ready" if rag_ready else "not_initialized",
            message="RAG Agent initialized" if rag_ready else "RAG Agent not yet initialized",
        ),
        "aiops": ServiceHealth(
            status="ready" if aiops_ready else "not_initialized",
            message="AIOps application service initialized"
            if aiops_ready
            else "AIOps application service not yet initialized",
        ),
        "checkpoint": ServiceHealth(
            status="ready" if checkpoint_ready else "not_initialized",
            message="Checkpoint store initialized"
            if checkpoint_ready
            else "Checkpoint store not yet initialized",
        ),
    }
