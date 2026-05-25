# Interfaces package — Abstract contracts for the system
from .base_agent import IAgent
from .base_crew import ICrew
from .base_task import ITask
from .base_vector_store import IVectorStore
from .base_document_processor import IDocumentProcessor, DocumentChunk, ProcessedDocument
