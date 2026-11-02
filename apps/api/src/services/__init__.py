"""Services interfaces. Each implementation should be in a subpackage of its own.

Import interfaces from here (``from services import RecordStore``). They are defined in one module per domain:

| Module                    | Interfaces                                                                   |
|---------------------------|------------------------------------------------------------------------------|
| ``services.json_types``   | ``Json``, ``JsonObject`` (parsed JSON)                                       |
| ``services.database``     | ``Tx``, ``ConflictError``, ``UnstorableValueError`` (shared by all stores)   |
| ``services.records``      | ``RecordStore``                                                              |
| ``services.search``       | ``KnowledgeIndex``                                                           |
| ``services.graph``        | ``GraphStore``                                                               |
| ``services.vectors``      | ``VectorStore``                                                              |
| ``services.embeddings``   | ``Embedder``                                                                 |
| ``services.llm``          | ``LLM``                                                                      |
| ``services.object_store`` | ``ObjectStore``                                                              |
| ``services.documents``    | ``DocumentStore``, ``TextExtractor``, ``KnowledgeExtractor``                 |

The interface modules import each other by module (``from services.database import Tx``): they are loaded while
this file runs. Implementations live in subpackages and inherit from their interface. ``tests/fakes.py``
implements interfaces in memory for the tests.
"""

from services.database import ConflictError as ConflictError
from services.database import Tx as Tx
from services.database import UnstorableValueError as UnstorableValueError
from services.documents import Document as Document
from services.documents import DocumentStatus as DocumentStatus
from services.documents import DocumentStore as DocumentStore
from services.documents import Extracted as Extracted
from services.documents import KnowledgeExtractor as KnowledgeExtractor
from services.documents import Passage as Passage
from services.documents import TextExtractor as TextExtractor
from services.embeddings import Embedder as Embedder
from services.graph import FactMeta as FactMeta
from services.graph import FactRow as FactRow
from services.graph import FactView as FactView
from services.graph import Filter as Filter
from services.graph import GraphStore as GraphStore
from services.graph import Hypernode as Hypernode
from services.graph import HypernodeSpec as HypernodeSpec
from services.graph import Lane as Lane
from services.graph import LexicalCandidate as LexicalCandidate
from services.graph import Membership as Membership
from services.graph import NumberRow as NumberRow
from services.json_types import Json as Json
from services.json_types import JsonObject as JsonObject
from services.llm import LLM as LLM
from services.llm import LLMError as LLMError
from services.object_store import ObjectStore as ObjectStore
from services.records import Link as Link
from services.records import Record as Record
from services.records import RecordLinkedError as RecordLinkedError
from services.records import RecordStore as RecordStore
from services.search import KnowledgeIndex as KnowledgeIndex
from services.search import MaintenanceReport as MaintenanceReport
from services.search import Retrieval as Retrieval
from services.search import SearchMode as SearchMode
from services.search import SearchSettings as SearchSettings
from services.vectors import VectorKind as VectorKind
from services.vectors import VectorStore as VectorStore
