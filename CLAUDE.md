# volume_profile_algo

## Conventions

### 1. Organization & structure (modular)

Keep everything modular. Group code by concern into clearly-labeled,
self-contained folders — each folder owns one thing and holds all files
related to it.

- **Chart / UI lives in `chart/`.** All chart- and UI-related files
  (markup, JS, vendor libs, styles) go there. The chart is meant to be
  **reused across other tasks**, so keep it self-contained and free of
  dependencies on task-specific code.
- **Data lives in `data/`.** Pipeline scripts and datasets.
- Name files and folders for what they contain. A new concern gets a new
  folder rather than being bolted onto an existing one.

More conventions will be added here over time.
