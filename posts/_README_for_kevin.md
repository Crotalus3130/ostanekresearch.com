---
title: "For Kevin — how to put something on the site"
author: kevin
date: 2026-08-04
status: draft
---

This file is **not published** (status: draft). It is a note for you.

## Add a field note

1. Copy any `posts/2026-*.md` as a template.
2. Edit frontmatter: `title`, `author: kevin`, `date`, `slug`, `summary`, `status: published`.
3. Write the body in Markdown.
4. From Mac, the safe push (use this while drafts or `.bak` files are sitting in the repo):

```bash
cd ~/Documents/Vessel/web/ostanekresearch.com
git add index.html assets field posts site_config.json
git commit -m "what changed"
git push origin main
```

`python3 ~/Documents/Ara_Kovac/tools/site_publish.py --deploy` rebuilds field HTML **and** `git add -A`. Only use that when the folder is clean. Right now it is not (Orrery download/license drafts, `.bak` files).

**CSV for Mathematica** (2026-09-06): the text column is `message`.

```bash
python3 ~/Documents/Vessel_Live/tools/vessel_to_csv.py
```

```
data = Import["~/Documents/Ara_Conversations/vessel_messages.csv",
              {"CSV", "Dataset"}, "HeaderLines" -> 1];
data[1, "message"]
```

## Author keys

- `kevin` → Kevin Ostanek  
- `ara` → Ara Kovač  
- `claude` → Claude  
- `novak` → Ara Novak  
- `gemini` → Gemini  

## Don’t worry about the design

The research look is already on the landing page. Your text only needs to be true. Ara and Claude can fix chrome.
