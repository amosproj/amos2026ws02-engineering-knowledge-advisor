Build, user, and technical documentation

## Architecture

- [`architecture/software-architecture.md`](architecture/software-architecture.md)
- [`architecture/llm-integration.md`](architecture/llm-integration.md) - LLM provider configuration and API
- [`architecture/knowledge-retrieval.md`](architecture/knowledge-retrieval.md) - knowledge storage and retrieval (OG-RAG, embeddings)

## Contracts

- `openapi.json` - API contract, exported by FastAPI and imported by REST clients (Postman, Insomnia, Bruno, ...)

## Misc

- `sbom/` - CycloneDX software bill of materials for the application dependencies
- `bpmn/` - BPMN 2.0 process flow diagrams, open in `bpmn.io` or other process modellers
- [`received-data-overview.md`](received-data-overview.md) - data received from company partner, what is missing, open points
