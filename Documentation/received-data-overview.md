# Received data overview

What we have been given so far, what each file is for, and what's still missing.

## Data categories

| Category               | What it is                                                                       | Status                                           |
|------------------------|----------------------------------------------------------------------------------|--------------------------------------------------|
| CAD files              | STEP and JT exports of a machine                                                 | received one example machine                     |
| Unstructured knowledge | general design guidelines, specific knowledge about machines and assembly groups | received after the in-person meeting             |
| Structured data        | not defined yet                                                                  | open                                             |

## Files from the shared drive

### Received first

| File                            | Format                                                 | Size             | Purpose                                           |
|---------------------------------|--------------------------------------------------------|------------------|---------------------------------------------------|
| Inventor project (Pack&Go)      | `.ipj` with `.iam` files in the project data directory | ~280 MB in total | Source of truth for the example machine           |
| `TEF1006U001-G00_802.stp`       | STEP export                                            | 128 MB           | File a Creator uploads and CAD parser reads       |
| `TEF1006U001-G00_802.jt`        | JT export                                              | 28 MB            | Alternative export of the same machine            |
| `CAD_Formats_description.docx`  | Word                                                   | –                | AI-generated overview of possible CAD formats     |
| `TEF2_Vorstellung_EN.pdf`       | PDF                                                    | –                | Two slides with the project idea and requirements |
| Walkthrough transcript of 21.10 | transcript                                             | –                | Summary of our first meeting                      |

### After in-person meeting

| File                                                                    | Format   | Purpose                                                                                                 |
|-------------------------------------------------------------------------|----------|---------------------------------------------------------------------------------------------------------|
| `AMOS Konstruktionsreview-20261026_131636-Besprechungsaufzeichnung.mp4` | video    | Design review: domain engineer/expert walks through functions and structure of the example machine      |
| `AMOS_ Konstruktionsreview_Transscipt.docx`                             | Word     | AI transcript of the review, an example of unstructured input                                           |
| `Zusammenfassung_Konstruktiuonsreview`                                  | document | AI-generated English summary of the review                                                              |
| `Beispielstückliste_NuP1.xlsx`                                          | Excel    | Parts list of independent parts (USB cables, sensors, cabinets, …)                                      |
| **`Buckets_Example.docx`**                                              | Word     | **⚠️Important:** kinds of knowledge ("buckets") users want to save and find for the example machine    |
| **Requirements Bosch V1**                                               | document | **⚠️Important:** structured requirements and use cases the product should support                      |
| **Search examples (Engineer Prompts)**                                  | document | **⚠️Important:** example questions a user in the Basic role would ask in the chat                      |
| `TEF1006U001-G00_802.jt`, `.stp`                                        | JT, STEP | Duplicates of the files above                                                                           |

## What the STEP file contains beyond geometry

- **Read by parser**:
  - name of assemblies and parts, assembly hierarchy
  - bounding-box size per assembly and part
- **Not read:** iProperties or part numbers

## Still missing

- More example Inventor projects
- Anonymized sample customer request(s)
- Structured knowledge data

## Open points

- What structured data, if any, will we receive?
- Can we get further machines and an anonymized customer request?
