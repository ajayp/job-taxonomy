# Plan: enrich the taxonomy for search

Status: PLAN ONLY. Nothing below is implemented. Check in before starting step 1.

## Goal
Make job search better (free-text, by what a job does and which tools it uses), without hurting title lookup.

## Decisions so far
- Primary use is search enrichment.
- Free-text search over task text (needs Atlas Search indexes).
- New data goes in separate CSVs and separate collections, not extra columns on `occupations.csv`.
- Mongo loaders, tests and indexes are in scope for every new dataset.
- The white-collar rule is open for change.

## Findings that shape the plan (measured on current data)
- 1,016 occupations, 54,281 titles. No orphan titles, no missing hierarchy.
- 93 occupations have no Job Zone, no tasks and no software (mostly "All Other" catch-alls and military). They are wrongly `whiteCollar=False` in 30 managerial/professional cases.
- "All Other" occupations hold 14% of titles ("Production Workers, All Other" alone holds 5%).
- 6,325 title strings map to more than one occupation ("Engineer" -> 40).
- Task Statements: 18,838 rows / 923 occupations, ~20 per occupation, 39% of occupations have a task from 2024-2026, only 5% have nothing newer than 2015.
- Software Skills: 31,821 rows / 8,753 distinct tools / 923 occupations. File has NO date column, so currency is unverified.
- Not worth adding for search: Task Ratings (except importance), Essential Skills, Career Interest Types.

## Steps (in order)

### 1. Build fixes (`build_taxonomy.py`)
- [ ] Normalize whitespace in titles (collapse double spaces, strip); add a test with the `"Product Management  Vice President"` case.
- [ ] Add `isAllOther` column to `occupations.csv` (title contains "All Other").
- [ ] Revisit the white-collar rule in the constants block:
  - [ ] Decide treatment of occupations with no Job Zone (currently forced False).
  - [ ] Decide whether Office/Admin Support (43) and zone-3 managers should count.
  - [ ] Print a before/after diff of flipped occupations; get approval before changing the output.
- [ ] Add a per-title specificity signal (e.g. `titleCount` per occupation, or `isAllOther` carried onto titles) so search can down-weight catch-alls. Decide the exact field with the user.
- [ ] Update README (Data model, White-collar rule) for the new columns.

### 2. Tasks (new `taxonomy/tasks.csv`, collection `jobTasks`)
- [ ] Add `data/onet/Task Statements.txt` and extend the build; fields: `code`, `taskId`, `task`, `taskType`, `date`.
- [ ] Validate: every `code` exists in `occupations.csv`; build fails otherwise.
- [ ] Decide whether to keep Analyst-sourced rows (587 rows, lower quality) and untyped tasks (418).
- [ ] `mongoTasksLoad.py` using `mongoload.load`, unique key `code` + `taskId`; add `source`.
- [ ] Regular index on `code`; Atlas Search index `tasks` on `task` (document the JSON definition in README, same style as `title`/`functions`).
- [ ] Tests in `test_loaders.py` (install `mongomock`; it is not installed in the current environment).

### 3. Software skills (new `taxonomy/software.csv`, collection `jobSoftware`)
- [ ] Add `data/onet/Software Skills.txt`; fields: `code`, `example`, `category`, `hotTechnology`, `inDemand`.
- [ ] Note in README that the source file has no date.
- [ ] `mongoSoftwareLoad.py`; unique key `code` + `example`; index on `code`.
- [ ] Atlas Search index `software` on `example` and `category` (autocomplete + fuzzy).
- [ ] Tests.

### 4. Related occupations (new `taxonomy/related.csv`, collection `jobRelated`)
- [ ] Add `data/onet/Related Occupations.txt` (not yet provided by the user); fields: `code`, `relatedCode`, `tier`, `rank`.
- [ ] Validate both codes exist.
- [ ] `mongoRelatedLoad.py`; compound index `code`, `tier`, `rank`.
- [ ] Tests.

### 5. Search validation
- [ ] Write 20-30 real queries (titles, vague titles like "analyst", task phrases, tool names like "Excel").
- [ ] Run before/after against Atlas; record which improve and which regress.
- [ ] Only keep a new dataset if it improves the queries it was meant for.

### 6. Reported titles (optional, gated)
- [ ] First diff `Sample of Reported Titles` against `titles.csv`; build only if it adds a meaningful number of new titles (decide the threshold with the user).

## Open questions for the user
1. White-collar: what should the rule be for occupations with no Job Zone?
2. Keep Analyst-sourced tasks, or only Incumbent and Occupational Expert?
3. Can you attach `Related Occupations.txt` (and `Sample of Reported Titles.txt` if step 6 goes ahead)?
4. Which O*NET version are the files in `data/onet/`? The repo does not record it; add it to the README?

## Review
(Fill in after each step: what changed, measured results, anything surprising.)
