"""Services interfaces. Each implementation should be in a subpackage of its own.

Import interfaces from here (``from services import RecordStore``). They are defined in one module per domain:

| Module                    | Interfaces                                                                   |
|---------------------------|------------------------------------------------------------------------------|
| ``services.json_types``   | ``Json``, ``JsonObject`` (parsed JSON)                                       |
| ``services.database``     | ``Tx``, ``ConflictError``, ``UnstorableValueError`` (shared by all stores)   |
| ``services.records``      | ``RecordStore``                                                              |
| ``services.search``       | ``SearchMode``                                                               |
| ``services.graph``        | ``Lane``                                                                     |
| ``services.llm.interface`` | ``LLMService``                                                             |

The interface modules import each other by module (``from services.database import Tx``): they are loaded while
this file runs. Implementations live in subpackages and inherit from their interface. ``tests/fakes.py``
implements interfaces in memory for the tests.
"""

from services.database import ConflictError as ConflictError
from services.database import Tx as Tx
from services.database import UnstorableValueError as UnstorableValueError
from services.graph import Lane as Lane
from services.json_types import Json as Json
from services.json_types import JsonObject as JsonObject
from services.llm import LLMService as LLMService
from services.records import Link as Link
from services.records import Record as Record
from services.records import RecordLinkedError as RecordLinkedError
from services.records import RecordStore as RecordStore
from services.records import StaleVersionError as StaleVersionError
from services.search import SearchMode as SearchMode
