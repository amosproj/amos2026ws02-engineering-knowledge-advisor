# Seed data

Example content for building and demonstrating the app with realistic data instead of test data.

## `bosch-example/knowledge-items.json`

18 knowledge items about the Bosch example machine `TEF1006U001-G00_802` (#89). They were extracted from the German transcript of the Konstruktionsreview on 26.10.2026 with Christoph Gesell, Tobias Kober and Julian Ortner. The import (#90) loads them.

The human-readable extraction, with the original German quote and timestamps for every item, is the Google Doc "Konstruktionsreview 26.10.2026 – Extraktion" in the shared drive folder `29-Oct-2026`.

### Format (`eka-seed-knowledge/v1`)

| Field | Meaning |
|---|---|
| `machine.identifier` | Name of the root assembly of the machine the items belong to |
| `sources` | Documents the items come from, by id |
| `items[].id` | Stable id within the file, so a second import can skip items it already created |
| `items[].appliesTo` | Assembly group identifiers (the CAD definition name, e.g. `TEF1006U001-G01_801`), not record ids. Record ids are new on every CAD import; the import looks the id up by this name. |
| `items[].appliesToMachine` | `true` when the item is about the whole machine instead of one group |
| `items[].itemType` | One of the `og:itemType` values in `ontology_v0.jsonld` |
| `items[].author` | The engineer who said it. The ontology has no `author` property yet; #11 adds it. |
| `items[].source` | Source id and transcript timestamps (`m:ss`) |
| `items[].properties` | `og:KnowledgeProperties` fields: `name`, `statement`, `reasoning`, `condition`, `consequence`, `recommendation`, `confidence` |

The text is in English; the source is German.

### Checks

`tests/seed/test_seed_files.py` checks the file against the ontology: allowed `itemType` and `confidence` values, known property names, an author and an element on every item.

The assembly names were checked against `TEF1006U001-G00_802.jt`. G01, G02, G05 and G25 were named in the review. G20 (robot) was matched by part dimensions only. Confirm it after importing the STEP file.
