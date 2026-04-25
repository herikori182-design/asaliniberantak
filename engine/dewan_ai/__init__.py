"""
Dewan AI - Multi-domain AI Council System.

Phase 1 foundation:
- AI client abstraction (GLM 4.6 thinking, no fallback)
- Domain knowledge base (per-domain markdown + reasoning examples)
- Prompt templates (per domain + voting)
"""

from .client import (
    AIClientFactory,
    BaseAIClient,
    ReasoningAnalysis,
    GLMThinkingClient,
)
from .discussion import DomainDiscussion
from .manager import DewanAIManager
from .voting import VotingSystem
from .knowledge import DomainKnowledgeBase, KnowledgeBaseManager

__all__ = [
    "AIClientFactory",
    "BaseAIClient",
    "ReasoningAnalysis",
    "GLMThinkingClient",
    "DomainDiscussion",
    "VotingSystem",
    "DewanAIManager",
    "DomainKnowledgeBase",
    "KnowledgeBaseManager",
]

__version__ = "0.1.0"
