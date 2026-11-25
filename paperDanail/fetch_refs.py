"""Query Crossref API for real, verified 2022-2025 journal papers on motor current DL fault diagnosis and domain generalization."""
import json
import urllib.parse
import urllib.request
from pathlib import Path

QUERIES = [
    ("mcsa_dl", "motor current signature analysis deep learning fault diagnosis 1D CNN", 6),
    ("dc_motor_dl", "DC motor fault diagnosis armature current deep learning", 6),
    ("var_speed_gen", "rotating machinery fault diagnosis unseen speed domain generalization", 6),
    ("inception_fault", "InceptionTime fault diagnosis motor current vibration", 5),
]

out = []
for tag, q, rows in QUERIES:
    url = (
        "https://api.crossref.org/works?"
        + urllib.parse.urlencode({
            "query": q,
            "filter": "from-pub-date:2022-01-01,until-pub-date:2025-12-31,type:journal-article",
            "rows": rows,
            "select": "DOI,title,author,container-title,volume,issue,page,article-number,published-print,published-online,issued",
        })
    )
    req = urllib.request.Request(url, headers={"User-Agent": "PaperCheck/1.0 (mailto:research@tu-sofia.bg)"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    out.append(f"\n=== {tag} ===")
    for item in data["message"]["items"]:
        doi = item.get("DOI", "")
        title = (item.get("title") or [""])[0].replace("\n", " ")
        journal = (item.get("container-title") or [""])[0]
        vol = item.get("volume", "")
        iss = item.get("issue", "")
        page = item.get("page") or item.get("article-number") or ""
        yr = (item.get("issued", {}).get("date-parts", [[""]])[0] or [""])[0]
        authors = []
        for a in item.get("author", [])[:6]:
            g = a.get("given", "")
            f = a.get("family", "")
            if f:
                inits = " ".join(p[0] + "." for p in g.replace("-", " ").split() if p)
                authors.append(f"{inits} {f}".strip())
        if len(item.get("author", [])) > 6:
            authors = authors[:3] + ["et al."]
        out.append(f"  [{yr}] {', '.join(authors)} | \"{title}\" | {journal} | vol={vol}, no={iss}, pp={page} | https://doi.org/{doi}")

Path(__file__).resolve().parent.joinpath("_inspect", "crossref_candidates.txt").write_text("\n".join(out), encoding="utf-8")
print("OK")
