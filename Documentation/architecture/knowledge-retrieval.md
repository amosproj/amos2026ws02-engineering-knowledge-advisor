# Knowledge Storage and Retrieval

## Decisions

- **Records:**
  * source of truth, stored in Postgres
  * e.g. machines, assembly groups, instances, CAD files, knowledge items
  * `records` table holds ontology-validated records in a JSONB column, `record_links` table for links between records
- **Ontology-grounded RAG (OG-RAG):**
  * stored in Postgres: `ograg_*` tables
  * hypergraph: backend-derived knowledge graph from stored records
  * hyperedges (facts): edges of the knowledge graph connecting hypernodes
  * hypernode: string `key: value` pairing of property name and property value
  * search picks closest hypernodes to request query and the smallest set of facts that covers them
  * answer generation based on chosen facts only with citations
- **Search:**
  * semantic:
    - `pgvector`, HNSW with cosine similarity
    - all embeddings live in an `ograg_vectors` table
    - returns top-k results by distance metric
  * lexical:
    - `pg_trgm`
    - returns top-k results by similarity score
- **Embedding model:**
  * [Huggingface: `intfloat/multilingual-e5-base`](https://huggingface.co/intfloat/multilingual-e5-base)
  * 768 dimensions
  * multilingual including German, English
  * expects prefixes `query: ` for requests and `passage: ` for texts
  * hosted locally, CPU
  * MIT license
- **LLM:**
  * providers are configured with backend's `LLMService`
  * [`Documentation/architecture/llm-integration.md`](llm-integration.md)

## Approaches / RAG

### Vanilla (pgvector embedding search)

- split text into chunks, embed chunks and store the embeddings
- search results top-k chunks most similar to the request query
- knows nothing about structure of data
  * unless mentioned in text, which is not guaranteed with chunks
- no answer refusal when no chunk actually matches

### Ontology-Grounded RAG (OG-RAG)

- [arXiv:2412.15235](https://arxiv.org/abs/2412.15235), [GitHub: `microsoft/ograg2`](https://github.com/microsoft/ograg2)
- unit of retrieval is an ontology-shaped fact
- facts carry identity information of what the fact is about
- set cover chooses facts that together cover all the matched keys and values of the request
- **Additions to paper:**
  * deterministic refusal to answer if nothing passes a similarity threshold
  * LLM **MUST** cite a fact, or declare request query uncovered, otherwise refusal

### CiteGuard-RAG

- [arXiv:2609.15830](https://arxiv.org/abs/2609.15830)
- retrieval combines embeddings with lexical keyword search, e.g. BM25
- answers must cite chunks and are checked against them
- failing answers are regenerated
- refusal if evidence is too weak

|                     | OG-RAG                                                    | CiteGuard-RAG                           |
|---------------------|-----------------------------------------------------------|-----------------------------------------|
| **Ontology**        | Used for: facts, identity context, anchor, search modes   | None                                    |
| **Records**         | Deterministic mapping onto facts                          | Must be turned into text first          |
| **Embeddings**      | Each unique key, each unique value of semantic properties | Each chunk                              |
| **Refusal**         | None in paper (see **additions** above)                   | Evidence threshold and validation       |
| **Host**            | Postgres, pgvector, pg_trgm                               | Postgres, pgvector, pg_search           |

## Why OG-RAG

- **Ontology as domain-anchor:**
  * annotations define record classes, which properties are copied as context, which are searched by meaning, spelling or as filters
  * new domain class or property: ontology change, no storage and search code change, no database schema change
- **Derived hypergraph:**
  * disposable, not a backup priority
  * rebuildable after ontology change or embedding model switch
  * an embedding model switch only re-embeds unique texts of `key: value` pairs
- **Citable facts:**
  * each fact is a numbered, self-contained block
  * answers point at exactly what they rely on, refusals list what was examined
- **Records as data:**
  * structured domain data instead of chunked text documents, usable in frontend
  * but: documents (e.g. `.md`, `.pdf`) need to be extracted into records first

## Changing the Embedding Model

- `ograg_vectors` table: keeps used model name per embedding row
- only current embedding model's vectors are kept
- backend drops vectors and re-embeds everything if configured model differs at startup
- during re-embedding, search uses vectors embedded so far and reports an incomplete index
- change of model to one with a new dimensionality requires:
  * database migration of the vector column in `ograg_vectors` table

## Changing the Ontology

| Annotation             | Purpose                                                                       |
|------------------------|-------------------------------------------------------------------------------|
| `og:record`            | Marker: class is stored as records                                            |
| `og:anchor`            | The class search results are grouped by                                       |
| `og:identity`          | Marker: property is copied as context into facts of linking records           |
| `og:edgeType` `parent` | Link to the record's parent: which records a fact's context comes from        |
| `og:search`            | Enum: `semantic` (embedded), `lexical` (spelling), `filter` (numbers)         |
| `og:provenance`        | Marker: property holds the document ID a record was extracted from            |

- change of ontology requires:
  * **NO** database schema migration
  * rebuild the hypergraph
- change of ontology class shapes (e.g. renamed or removed properties) requires:
  * migrate records: re-validate every record on new ontology by original input
