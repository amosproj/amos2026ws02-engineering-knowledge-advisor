"""Services interfaces. Each implementation should be in a subpackage of its own.

Import interfaces from here (``from services import RecordStore``). They are defined in one module per domain:

| Module                         | Interfaces                                                                 |
|--------------------------------|----------------------------------------------------------------------------|
| ``services.json_types``        | ``JsonValue``, ``JsonObject`` (parsed JSON)                                     |
| ``services.database``          | ``Tx``, ``ConflictError``, ``UnstorableValueError`` (shared by all stores) |
| ``services.records``           | ``RecordStore``                                                            |
| ``services.search``            | ``KnowledgeIndex``, ``SearchMode``                                         |
| ``services.hypergraph``        | ``GraphStore``, ``Lane``                                                   |
| ``services.vectors``           | ``VectorStore``                                                            |
| ``services.embedding_service`` | ``EmbeddingService``                                                       |
| ``services.llm_service``       | ``LLMService``                                                             |

The interface modules import each other by module (``from services.database import Tx``): they are loaded while
this file runs. Implementations live in subpackages and inherit from their interface. ``tests/fakes.py``
implements interfaces in memory for the tests.
"""

from services.database import ConflictError as ConflictError
from services.database import Tx as Tx
from services.database import UnstorableValueError as UnstorableValueError
from services.embedding_service import EmbeddingService as EmbeddingService
from services.hypergraph import FactRow as FactRow
from services.hypergraph import FactView as FactView
from services.hypergraph import GraphStore as GraphStore
from services.hypergraph import HypernodeSpec as HypernodeSpec
from services.hypergraph import Lane as Lane
from services.json_types import JsonObject as JsonObject
from services.json_types import JsonValue as JsonValue
from services.llm_service import LLMService as LLMService
from services.records import Link as Link
from services.records import Record as Record
from services.records import RecordLinkedError as RecordLinkedError
from services.records import RecordStore as RecordStore
from services.records import StaleVersionError as StaleVersionError
from services.search import KnowledgeIndex as KnowledgeIndex
from services.search import Retrieval as Retrieval
from services.search import SearchMode as SearchMode
from services.vectors import VectorKind as VectorKind
from services.vectors import VectorStore as VectorStore
