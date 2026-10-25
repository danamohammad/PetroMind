# PetroMind

An open petroleum engineering workbench for fluid composition, vapor–liquid equilibrium, surface PVT, laboratory comparisons and production time series.

Live site: https://petromind.dana-edu.pp.ua

## Use it

1. Load the supplied example or import a composition CSV/Excel file. You can edit every mole fraction and component property directly.
2. Check the composition total. Normalize only when that is appropriate for your data.
3. Enter reservoir, separator, stock-tank and standard-gas conditions. All pressures are absolute (psia), temperatures are Celsius.
4. Click **Calculate fluid properties**. The first calculation loads scientific Python and dependencies; subsequent calculations reuse them.
5. Choose a PVT property, zoom the chart, download PNG, export the calculated CSV, or print to PDF.
6. Use **Phase behavior** to calculate temperature–pressure saturation roots. Failed roots remain gaps.
7. Use **Laboratory comparison** to enter or import measured Bo, Rs, Bg, liquid density or bubble pressure. Compare using the current fluid model.
8. Use **Production trends** to import dates, oil rates and optional water rates, or enter them manually. The example is explicitly synthetic.
9. **Save project** stores inputs in this browser. **Export project** creates a portable JSON backup. Import it on another device to continue.

## Privacy and persistence

All scientific computation and imported-data processing happen in the visitor's browser. There is no user-data API, database, shared project store or analytics tracker. Saved projects use localStorage and can be lost when browser data is cleared. Download backups. Static hosting and library/font providers receive normal asset requests (including IP address), but no datasets are sent to them by this application.

## Scientific scope

Thermo 0.6.1 provides PR, PR78 and SRK vapor–liquid equilibrium. Pyodide 0.29.0 runs the same Python engine in a Web Worker. Plotly draws actual calculated points. Component properties and default PR interactions come from ThermoPack 2.2.3; the original supplied pseudocomponent assumptions are preserved and editable.

This is an uncalibrated research tool. Agreement with another EOS implementation is numerical verification, not validation against laboratory measurements. Heavy-cut labels must represent non-overlapping fractions. No water/brine, solids, wax, asphaltene or liquid–liquid equilibrium model is provided. No volume translation or automated laboratory fitting is claimed. No generative-AI service is used.

Independent isothermal saturation roots do not trace every possible retrograde branch. Near-critical or nonconvergent results remain unavailable. The application does not infer a mixture critical point from a curve maximum. Production forecasts are simple exponential historical baselines with no economic limit, operational constraints or calibrated uncertainty band.

## Implementation

- `public/Fluid Engine.py`: validated inputs, EOS construction, flash, separator train, PVT sweep, saturation and lab comparison.
- `public/Calculation Worker.js`: pinned browser Python runtime and request dispatch.
- `public/App.mjs`: UI, input editing, charts, imports, project storage and export.
- `public/Data Tools.mjs`: CSV parser, CSV export protection and production analysis.
- `references/ThermoPack Comparison.json`: independent-engine comparisons for four fluids/states.
- `tests/Engine Tests.py` and `tests/Data Tests.mjs`: physical/data invariants and import/export checks.

The liquid and vapor EOS classes preserve their respective V–L branches during Thermo's result sorting. Without this setting, its default PIP phase-identification heuristic relabels some dense vapor branches as a second liquid. This release is explicitly V–L, not a model of LLE.

## Local preview

Run from the repository root:

```sh
python3 -m http.server 8765 --directory public
```

Open http://localhost:8765. Serve through HTTP; opening index.html as a file will not support module/worker loading.

## Tests

With Python 3.12+:

```sh
python3 -m venv 'Validation Environment'
'Validation Environment/bin/python' -m pip install -r requirements.txt
'Validation Environment/bin/python' 'tests/Engine Tests.py'
node --test 'tests/Data Tests.mjs'
```

The optional ThermoPack crosscheck script uses the original extracted worker kept outside this public repository. Its completed results are included in `references/`. It never needs the original secrets configuration.

## Deploy

This is a static Cloudflare Worker Assets application. The checked-in `wrangler.jsonc` targets the owner's PetroMind Worker and custom domain. For your own fork, replace account ID, Worker name and route before deploying.

```sh
npx wrangler@4.151.1 login
npx wrangler@4.151.1 deploy
```

Do not commit tokens, secrets, `.env` files, virtual environments or user project exports. The public source contains only the supplied example composition, numerical reference results and application code.

## Attribution

Rebuilt for Dana Mohammad Khidhir from the supplied PetroMind prototype. The original Google Drive source was shared by dyar.ghaffoori. Third-party software retains its own license; see `public/Third Party Notices.txt`. Public visibility alone is not a blanket relicensing of the original author's work.

## Visual design

The blue and cyan visual theme follows the supplied energy-industry design reference. The offshore banner is an original AI-generated illustration, created with the built-in image-generation tool. Prompt: “Original photorealistic offshore platform at blue hour; wide 3:1 composition, illuminated platform on the right, quiet dark-blue ocean and sky on the left for white headings; marine blue, steel blue and cyan with restrained amber work lights; no text or logos.” Saved asset: `public/Offshore Energy.png`.
