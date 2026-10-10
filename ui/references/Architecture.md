flowchart TD
    A["Source or User Intent"] --> B["OneShot System Intake"]
    B --> C{"Identify input and purpose"}

    C --> T["Text / Raw Input"]
    C --> F["Files / Folders"]
    C --> V["Images / Diagrams"]
    C --> M["Mixed Content"]
    C --> R["Research Needed"]

    T --> P["Text Understanding"]
    F --> Q["Inventory and Content Inspection"]
    V --> W["Visual / Structural Inspection"]
    M --> X["Multi-source Inspection"]
    R --> Y["Browser Research and Evidence"]

    P --> S["System Summarize"]
    Q --> S
    W --> S
    X --> S
    Y --> S

    S --> Z{"Quality and Coverage Check"}
    Z -->|Sufficient| O["Prepared Context Available"]
    Z -->|Incomplete| I["Partial Context + Known Gaps"]
    Z -->|Unusable| E["Report Limitation"]

    B -.-> TR["System Activity / Trace"]
    Q -.-> TR
    X -.-> TR
    Y -.-> TR
    Z -.-> TR