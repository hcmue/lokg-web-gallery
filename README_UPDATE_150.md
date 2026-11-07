# LOKG-IR: upgrade the existing HCMUE repository from 72 to 150 samples

Target: https://github.com/hcmue/lokg-web-gallery
Public gallery: https://hcmue.github.io/lokg-web-gallery/
Public guide: https://hcmue.github.io/lokg-web-gallery/huong-dan.html

## What this incremental patch contains

- 78 new HTML examples, IDs `WEB-<GROUP>-013` through `WEB-<GROUP>-025`.
- 78 WebP thumbnails rendered from the actual example pages.
- One shared CSS file for new samples and a Vietnamese HTML user guide.
- Idempotent expansion script for the YAML catalog, offline fallback JSON, index navigation and legacy test assertions.
- Backend fixes for preserving `layout`, `components`, and explicitly entered `relations` metadata when the Admin edits the catalog.
- Retrieval support for *teacher-annotated* directed relationship concepts; no visual inference or automatic HTML parsing.
- Six additional consistency/regression tests.

**Safety:** This incremental ZIP intentionally does NOT contain `data/catalog.yaml`,
`docs/gallery-fallback.json`, `docs/index.html`, or the prior 72 samples. It is
safe to overlay onto v3.1 or v3.2 and then execute the expansion script.
It never uploads secrets or changes the cloud database.

## Windows PowerShell deployment

Prepare the repository working tree and back up your catalog:

```powershell
cd D:\Projects\lokg-web-gallery
git status
git pull --ff-only origin main
Copy-Item data\catalog.yaml ..\lokg_catalog_backup.yaml
```

Copy/extract this patch ZIP into the repository root (the location that contains
`app`, `data`, `docs`, `scripts`, and `tests`). Example:

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\LOKG_IR_Patch_150_Mau.zip" -DestinationPath "D:\Projects\lokg-web-gallery" -Force
```

Now generate the new catalog/index and verify everything:

```powershell
cd D:\Projects\lokg-web-gallery
py -m pip install -r requirements.txt pytest
py scripts\expand_to_150.py
py scripts\build_gallery.py
py -m pytest -q
git status
```

Expected: 150 records, 150 HTML files, 150 `.webp` files, six groups of 25.
Do not run the old `seed_catalog.py`; it is intended for the original 72 seeds.

Commit changes:

```powershell
git add app data docs scripts tests README.md README_UPDATE_150.md
git commit -m "Expand HCMUE Web UI gallery to 150 examples"
git push origin main
```

Render connected to `main` should auto-deploy if Auto Deploy is enabled. If
Render is still serving 72 records after GitHub Pages is updated, open its
Admin interface, click refresh/reload catalog, or redeploy the service.

Check:
- `https://hcmue.github.io/lokg-web-gallery/huong-dan.html`
- `https://hcmue.github.io/lokg-web-gallery/pages/WEB-ECO-025.html`
- `https://hcmue.github.io/lokg-web-gallery/previews/WEB-EDU-025.webp`
- `https://lokg-ir-web-links.onrender.com/api/health` (expect `items: 150`)

## Conditions / limitations

1. The 78 newly generated examples are teaching/demo UIs, not live commercial
   sites. Forms and buttons in the samples do not submit real transactions.
2. New relations reflect layout annotations embedded in sample metadata and
   must be reviewed by the teacher before use as research relevance labels.
3. Matching a relation phrase in a query is a constrained text parser, not
   image understanding or full spatial reasoning.
4. If other users have independently inserted additional catalog items, the
   generator aborts rather than silently deleting them. Reconcile extras
   before enforcing the exact 150-sample count.
5. This ZIP is a source-code delivery; no GitHub commit, GitHub Pages deploy,
   or Render deploy was performed by the assistant.
