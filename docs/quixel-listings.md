# Quixel Bridge Listings

The listing system used in Fab is different from the old Megascans backend. Here is a comprehensive guide to how the old format may be obtained, and additional information on how to rebuild the old taxonomy tree.

## What actually changed

Fab dropped Quixel's rich per‑asset taxonomy (biome, semantic tags, curated "collections"
like Broadleaf Forest) and exposes only coarse marketplace categories. But the old Megascans
backend is still online and still unauthenticated for browsing/metadata — Fab just doesn't
surface it. Your screenshot's tree ("COLLECTIONS → Environment → Natural → Broadleaf
Forest") was never a single API field; it was built client‑side from that taxonomy. You can
rebuild it.

The endpoints that still work (verified just now)

1. Search index — the thing that powered Bridge's browser. Same hardcoded proxy key the
Bridge web client ships:

POST https://proxy-algolia-prod.quixel.com/algolia/cache
header  x-api-key: 2Zg8!d2WAHIUW?pCO28cVjfOt9seOWPx@2j
body    {"url":"https://6UJ1I5A072-2.algolianet.com/1/indexes/assets/query?x-algolia-applica
tion-id=6UJ1I5A072&x-algolia-api-key=e93907f4f65fb1d9f813957bdc344892",
        "params":"hitsPerPage=1000&page=0"}
Returns 18,835 assets, no login. Each hit carries exactly the theme fields Fab hides:

category: "nature"        subCategory: "tree"
biome: "forest biome"     region/locations: "Americas"
assetCategories: ["3D asset | nature", "3D asset"]
contains: ["Wood"]        _tags: ["broadleaf","forests","moss","tyresta",...]
type: "3d"                resolution: 8192

2. Full per‑asset metadata (richer semanticTags, environment, meshes, previews, download
components):
GET https://quixel.com/v1/assets/{id}     ← no auth, returns 200

3. Download (only for assets your account already owns):
POST https://quixel.com/v1/downloads      ← needs  Authorization: Bearer <token>
The bearer token comes from the auth cookie of a logged‑in quixel.com session
(JSON.parse(cookie).token). The old GET https://quixel.com/v1/assets list endpoint is now
dead (404) — the Algolia proxy replaces it.

## How to rebuild the "theme-aware" tree

Important constraint I confirmed: this Mongo‑backed proxy only honors query (full‑text),
page, hitsPerPage (max 1000), and attributesToRetrieve. facetFilters/filters/facets are
silently ignored (a facetFilters query still returned all 18,835). So the right design is:
mirror the whole index once (~19 pages), cache it, and build/filter the tree locally. That's
cheap and also gives you finer control than the old Bridge.

Mapping to your screenshot:
- The flat category tree (Environment → Natural…) → group by assetCategories / category /
subCategory.
- Curated collections (Broadleaf Forest, Iceland, Lava Field) → these were tag/location
bundles. Broadleaf Forest = assets whose _tags contain broadleaf+forests (often a location
tag like tyresta). Build these as saved tag‑filter presets.

```python
import requests, time

PROXY = "https://proxy-algolia-prod.quixel.com/algolia/cache"
HDRS  = {"x-api-key": "2Zg8!d2WAHIUW?pCO28cVjfOt9seOWPx@2j",
        "content-type": "application/json"}
ALGOLIA = ("https://6UJ1I5A072-2.algolianet.com/1/indexes/assets/query"
            "?x-algolia-application-id=6UJ1I5A072"
            "&x-algolia-api-key=e93907f4f65fb1d9f813957bdc344892")

def fetch_all(attrs="objectID,name,type,category,subCategory,biome,"
                    "assetCategories,contains,region,_tags,previews"):
    page, out = 0, []
    while True:
        params = f"hitsPerPage=1000&page={page}&attributesToRetrieve={attrs}"
        r = requests.post(PROXY, headers=HDRS,
                        json={"url": ALGOLIA, "params": params}, timeout=30).json()
        out += r["hits"]
        if page >= r["nbPages"] - 1: break
        page += 1; time.sleep(0.3)
    return out           # cache to JSON; refresh occasionally

# build the tree locally, e.g.:
#   category -> subCategory -> assets       (the flat taxonomy)
#   biome buckets                            (forest/desert/tundra/...)
#   curated presets: lambda a: {"broadleaf","forests"} <= set(a["_tags"])
```

For each asset you show, call https://quixel.com/v1/assets/{id} on demand to get download
components + preview URLs, then (if the user owns it and you have their bearer token) POST
to /v1/downloads.

## Caveats worth designing around

- Unofficial & unstable: those keys are scraped from the web client. Epic could rotate/kill
them anytime — keep a config so you can swap keys, and fail gracefully.
- Legacy = frozen: ~18.8k already‑migrated assets; no new content, and a handful weren't
carried over. Downloads still require the asset to be acquired on the account, and free
claiming ended 2024‑12‑31.
- No sanctioned alternative yet: Epic has repeatedly said there's no public Fab API, so this
legacy backend is genuinely the only programmatic route to the fine taxonomy. Treat it as
best‑effort and cache aggressively (be polite: 1000/page, small delays) to avoid tripping
rate limits.

## Sources

- Megascans API Docs — Assets (https://quixel.github.io/megascans-api-docs/assets/) /
Quick-Start (https://quixel.github.io/megascans-api-docs/quick-start-guide/)
- jamiephan claim-all gist (Algolia proxy + keys)
(https://gist.github.com/jamiephan/0c04986c7f2e62d5c87c4e8c8ce115fc)
- WAUthethird/quixel-megascans-scripts (metadata + download flow)
(https://github.com/WAUthethird/quixel-megascans-scripts)
- aldenparker mass-download gist (/v1/downloads)
(https://gist.github.com/aldenparker/0d8fee85469d3561bc3a772a03d642cb)
- Quixel→Fab Transition FAQ (https://support.fab.com/s/article/Fab-Transition-FAQs) · Fab
API forum request (https://forums.unrealengine.com/t/is-there-or-will-there-be-a-fab-api-mos
tly-for-quixel-as-of-right-now-but-preferably-for-all-assets/2103358)
