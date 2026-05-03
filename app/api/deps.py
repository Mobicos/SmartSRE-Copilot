"""FastAPI dependency-injection helpers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from app.api.providers import (
    get_aiops_application_service,
    get_chat_application_service,
    get_native_agent_application_service,
)
from app.application.aiops_application_service import AIOpsApplicationService
from app.application.chat_application_service import ChatApplicationService
from app.application.native_agent_application_service import NativeAgentApplicationService
from app.platform.persistence.database import get_db

SessionDep = Annotated[Session, Depends(get_db)]

ChatServiceDep = Annotated[ChatApplicationService, Depends(get_chat_application_service)]
AIOpsServiceDep = Annotated[AIOpsApplicationService, Depends(get_aiops_application_service)]
NativeAgentServiceDep = Annotated[
    NativeAgentApplicationService, Depends(get_native_agent_application_service)
]
