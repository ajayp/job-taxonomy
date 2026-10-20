# jobTaxonomy

- [Project Summary](#project-summary)
- [Workflow](#workflow)
- [Setup and build](#setup-and-build)
- [Adding your own job titles](#adding-your-own-job-titles) (`data/supplementaryJobTitles.csv`)
- [Loading into Mongo](#loading-into-mongo)
- [Mongo fuzzy search (Atlas)](#mongo-fuzzy-search-atlas)
- [Background](#background) (O*NET/SOC schema design)

# Project Summary
This project is designed to process occupational data from the U.S. Department of Labor's O*NET database and import it into MongoDB. It creates two collections: jobFunctions (for broad job categories like "Marketing Managers") and jobTitles (for specific titles like "Marketing Director").

# Workflow

```
data/onet/*  +  data/supplementaryJobTitles.csv
        |  python build_taxonomy.py          (source of truth, validated)
        v
taxonomy/occupations.csv   taxonomy/titles.csv
        |  python mongoFunctionsLoad.py / mongoTitlesLoad.py   (set MONGO_URI)
        v
Mongo: jobFunctions, jobTitles      (jobTitles.code -> jobFunctions.code)
```

- `taxonomy/occupations.csv`: every O*NET occupation with `jobZone`, `whiteCollar` flag and the full SOC hierarchy (major, minor, broad, detailed), derived from `SOC_structure.csv`.
- `taxonomy/titles.csv`: alternate titles (`source=onet`) plus supplementary additions (`source` = the supplement file's name, e.g. `supplementaryJobTitles`).
- The white-collar rule (SOC major groups + Job Zone 4/5) lives in one place: the constants at the top of `build_taxonomy.py`.
- Loaders support `--dry-run` and `--limit N`; `build_taxonomy.py --limit 20 --out /tmp/x` builds a small sample. The build exits non-zero if a supplementary title has an unknown code or an occupation is missing from the SOC structure.
- This replaces the pipeline in `../jobFunctionsJobTitlesScripts` (left unchanged for reference); that folder also holds the unrelated Crunchbase loaders.

# Setup and build

Use this for a first install and again for each new O*NET release. The result is `taxonomy/*.csv`; loading into Mongo is a separate, optional step (next sections).

1. **Install** (Python 3.9+), in a virtual environment: `python3 -m venv .venv && source .venv/bin/activate && pip install pymongo` (add `mongomock` to run the tests). The build itself needs only the standard library. Run `source .venv/bin/activate` again in each new shell.
2. **Get the O*NET data** (first install, or a new release): download the text files from https://www.onetcenter.org/database.html#all-files and copy `Occupation Data.txt`, `Job Titles.txt` and `Job Zones.txt` into `data/onet/` (filenames can change). Update `data/onet/SOC_structure.csv` from https://www.onetcenter.org/taxonomy/2019/structure.html.
3. **Build**: `python build_taxonomy.py` and fix anything it reports. This rewrites `taxonomy/*.csv`; commit them.

# Adding your own job titles

O*NET's title list doesn't include every title people really use (e.g. "Founder", "Managing Director"). To add your own, map each one to an O*NET occupation code in a CSV; they're merged in on every build, so they survive O*NET refreshes.

`data/supplementaryJobTitles.csv` is an input file, not a script: you never run it. You edit it, then run the build, which reads it.

1. **Edit the file.** Add one line per title, in the form `SOC code,Title[,Short title]`, e.g. `11-2011.00,Marketing Officer`.
   - The code must be a full O*NET code including the `.00` suffix (`11-1011.00`, not `11-1011`). Find it by searching `taxonomy/titles.csv` for a similar title; major groups: https://www.bls.gov/soc/2018/major_groups.htm
   - The first line is a header row (`O*NET-SOC Code,...`) and is skipped; keep it or delete it. Only the first three columns are read; anything after them (such as `Source(s)`) is ignored. Blank lines are skipped.
2. **Rebuild:** `python build_taxonomy.py`. This merges the file into `taxonomy/titles.csv`, tagging those rows with `source=supplementaryJobTitles` (the file name without `.csv`). The build exits non-zero and lists the offending lines if a code doesn't match an O*NET occupation, so fix those and rerun.
3. **Check:** `grep supplementaryJobTitles taxonomy/titles.csv` should show your new rows.
4. **Load into Mongo** (optional): `python mongoTitlesLoad.py --dry-run`, then `python mongoTitlesLoad.py`.

To use a different or additional file, pass `--supplement`, repeated as needed: `python build_taxonomy.py --supplement data/mine.csv --supplement data/other.csv`. This replaces the default file rather than adding to it, so list `data/supplementaryJobTitles.csv` too if you still want it. The file name becomes the `source` value; `manual` and `onet` are reserved and rejected.

# Loading into Mongo

Optional: only needed to use the data (and Atlas fuzzy search) from Mongo. Run after Setup and build.

1. **Connect**: `export MONGO_URI="mongodb+srv://..."` (credentials and database options are below). The code reads environment variables only and does not load a `.env` file; if you keep the values in one (it is gitignored), run `set -a; source .env; set +a` first.
2. **Preview**: `python mongoFunctionsLoad.py --dry-run` and `python mongoTitlesLoad.py --dry-run`.
3. **Load**: `python mongoFunctionsLoad.py` then `python mongoTitlesLoad.py`. Each load replaces the documents this pipeline owns, so a refresh needs no cleanup.

Options and rules:

- Set `MONGO_URI` or `MONGODB_URI`; if it has no credentials or still has Atlas's `<username>`/`<password>` placeholders, `MONGODB_USERNAME` / `MONGODB_PASSWORD` are filled in. Databases and collections are created on first insert. Optional: `MONGO_DB` or `--db` (default `jobTaxonomy`), `--collection` to target a new collection.
- Every document has a `source`. Every non-`manual` document is owned by this pipeline: each load deletes them and reloads from `taxonomy/*.csv`, so titles O*NET removed disappear on the next load.
- Documents with `source: "manual"` are never touched (`manual` and `onet` are reserved, so a supplement file can't use those names). Add hand-made titles with `source: "manual"`.
- `--include-manual` deletes everything, manual documents too (asks for confirmation, `--yes` skips it).
- Guards: aborts on an empty load or if the new load is >20% smaller than the owned documents it replaces (`--force` overrides). `--dry-run` reports counts, `--limit N` loads a sample.
- Indexes: the loaders create unique indexes automatically (`jobFunctions.code`; `jobTitles.code` + `title`); the title-to-function `$lookup` uses the `code` one, so the join needs nothing else. The Atlas Search indexes you create by hand are described in Mongo fuzzy search: `title` on `jobTitles`, and optionally `functions` on `jobFunctions`.
- There is deliberately no supplementary file for `jobFunctions` (unlike job titles). `jobFunctions` mirrors O*NET occupations one to one, and adding or overriding functions by hand would unbalance the hierarchy and the `jobTitles.code` -> `jobFunctions.code` mapping. To cover a missing title, add it to the supplementary titles instead.
- Tests for these rules: `pip install mongomock && python -m unittest test_loaders`.

# Mongo fuzzy search (Atlas)

Requires the data to be loaded (previous section). There are two Atlas Search indexes: `title` on `jobTitles` (required for title search) and `functions` on `jobFunctions` (optional, only to search the functions themselves). Steps 1 to 3 below are for `title`; the `functions` index follows them.

1. Create an Atlas Search index on the `jobTitles` collection (database `jobTaxonomy` by default): Atlas UI > Search > Create Search Index > JSON Editor, **index name `title`** (the queries below refer to it by name; Atlas defaults to `default`, so change it), with this definition:
```json
{
  "mappings": {
    "dynamic": false,
    "fields": {
      "title": {
        "type": "string"
      }
    }
  }
}
```

2. In the Atlas console, query the `title` index. Here we are searching for the job title "**pesient pabnk**" aka "**bank president**" using fuzzy search
```js
[
  {
    $search: {
      index: "title",
      text: {
          "query": "pesient pabnk",
          "path": "title",
          "fuzzy": {
            "maxEdits": 2,
            "maxExpansions": 2,
            "prefixLength": 0
          }
      }
    }
  }
]
```
![image](https://user-images.githubusercontent.com/85851707/234724768-219d8f17-e616-4258-b6e6-267916f0baea.png)

3. Let's find all the job functions associated with "**pesient pabnk**" using an aggregate query, results are ordered by highest score, screenshot of results below.
```
db.getCollection("jobTitles").aggregate([
  {
    $search: {
        "index": "title",
      "text": {
        "path": "title",
        "query": "pesient pabnk",
        "fuzzy": {
          "maxEdits": 2, //Maximum number of single-character edits to match the specified search term, max value is 2.
          // With a maxEdits value of 1, a query for "cat" will match docs containing "cat," "hat," "cut," "cats," and "cart" as words can be formed by changing only one char in "cat" (e.g., changing "c" to "h" gives "hat").
          // However, "dog" requires two changes ("c" to "d" and "t" to "g") to match "cat," so it would not be included in the search results.
          // With a maxEdits value of 2, the same query would also match documents containing "dog," "cog," and "coat" because these words can be formed by changing two or fewer characters in "cat."
          "maxExpansions": 2, //The maximum number of variations to generate and search for. maxexpansions is max num of variations that can be generated for the search term.
          //When searching for "cat" with a maxExpansions value of 5, the search engine will generate variations of "cat" with one edit distance,
          // such as "hat" and "cut,"
          // and then stop searching after the fifth variation is generated. This means that the search will not include variations with an edit distance of two,
          // such as "dog."
           //However, with a maxExpansions value of 10,
           //the search engine will continue to generate variations of "cat" until it reaches the maximum limit of 10.
           //This means that it will include variations with an edit distance of two, such as "dog," "cog," and "coat," as well as variations with an edit distance of one, such as "catch" and "chat."
          "prefixLength": 0 //Number of characters at the beginning of each term in the result that must exactly match. The default value is 0.
          //prefixLength value : 2, a query for "cat" would match docs containing "cat" and "cats," but not "cart" or "cut."
          // With a prefixLength value of 3, the same query would only match documents containing "cat."
        }
      }
    }
  },
  {
    $limit: 10
  },
  {
    $lookup: {
      "from": "jobFunctions",
      "localField": "code",
      "foreignField": "code",
      "as": "function"
    }
  },
  {
    $project: {
      "_id": 0,
      "title": 1,
      "function": { $arrayElemAt: ["$function.title", 0] },
      "score": { $meta: "searchScore" }
    }
  }
])
```

<img width="716" alt="image" src="https://user-images.githubusercontent.com/85851707/234725224-b2d6cae7-7286-4a87-a6e2-97d1dcd4499e.png">

## Optional: search the functions themselves (`functions` index)

Not needed for mapping a title to its function (that uses the `code` index and the `$lookup` above). Create this only if you want to search `jobFunctions` directly, e.g. "marketing" finding Marketing Managers, or searching by description text.

Atlas UI > Search > Create Search Index > JSON Editor, database `jobTaxonomy`, collection `jobFunctions`, **index name `functions`**:
```json
{
  "mappings": {
    "dynamic": false,
    "fields": {
      "title": { "type": "string" },
      "description": { "type": "string" },
      "majorGroup": { "type": "token" },
      "minorGroup": { "type": "token" },
      "whiteCollar": { "type": "boolean" }
    }
  }
}
```

Example: fuzzy search function titles and descriptions for "marketng manager", white-collar functions only:
```js
db.jobFunctions.aggregate([
  { $search: { index: "functions",
      compound: {
        must: [{ text: { query: "marketng manager", path: ["title", "description"],
                         fuzzy: { maxEdits: 2 } } }],
        filter: [{ equals: { path: "whiteCollar", value: true } }]
      } } },
  { $limit: 10 },
  { $project: { _id: 0, code: 1, title: 1, minorGroup: 1, score: { $meta: "searchScore" } } }
])
```

Also optional: if you will list functions by hierarchy (e.g. every function in a minor group), add a regular index. Skip it until a query needs it:
```js
db.jobFunctions.createIndex({ majorCode: 1, minorCode: 1 })
```

# Background

## O*NET schema design

The SOC system is a hierarchical classification system that organizes occupations into groups based on the work performed, the skills and knowledge required, and other characteristics of the job. The SOC system has four hierarchical levels, which are:

1. Major groups: There are 23 major groups, such as "Management Occupations", "Healthcare Practitioners and Technical Occupations", and "Production Occupations".
2. Minor groups: Each major group is divided into several minor groups. For example, the major group "Management Occupations" includes minor groups such as "Chief Executives", "General and Operations Managers", and "Advertising, Marketing, and Promotions Managers".
3. Broad occupations: Each minor group is divided into several broad occupations. For example, the minor group "Chief Executives" includes broad occupations such as "Chief Executive Officers", "Chief Financial Officers", and "Chief Operating Officers".
4. Detailed occupations: Each broad occupation is divided into several detailed occupations. For example, the broad occupation "Chief Executive Officers" includes detailed occupations such as "Chief Executive Officer (CEO)", "Executive Director", and "President".

Below the detailed level, O*NET adds alternate titles:

- Synonyms: Each detailed occupation may have one or more synonyms, which are alternative names or titles for the occupation.
- Occupations not elsewhere classified: This category includes occupations that cannot be classified into any of the other categories.

Source: https://www.onetcenter.org/taxonomy/2019/structure.html

## How to use this data

We create two datasets for import into Mongo that are imported into collections jobFunctions and jobTitles.

jobFunctions collection has the "SOC Code", majorGroup,  and minorGroup fields
jobTitles collection has the job title, short title and "SOC code" that maps to jobFunctions
