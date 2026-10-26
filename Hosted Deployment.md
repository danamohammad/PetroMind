# PetroMind hosted computation

Version 1.6.1 uses the existing Cloudflare account and its Free plan. No Render or Railway account, payment method, cross-provider service key, local server or browser model runtime is required. The public website submits calculations to a private Cloudflare Python service through a service binding.

## Architecture

`Hosted Worker.mjs` serves the interface, checks origin/size/rate limits, and sends numerical work to the `ScientificJobs` Durable Object. That object admits one scientific job at a time and holds temporary job state in memory. Scientific Python requests go through the `SCIENTIFIC` service binding to `petromind-science`, whose `ScientificSolver` Durable Object runs the numerical functions. Its workers.dev URL, preview URLs and routes are disabled. JavaScript data calculations and telemetry summaries run in the gateway's Durable Object. The assistant runs Qwen3-30B-A3B-FP8 on Cloudflare Workers AI.

Only date/counter values and result-expiry alarm timestamps are persisted. Fluid inputs, measurements, questions and numerical outputs are not written to application storage or logs. Results expire after ten minutes, are deleted when the browser retrieves them, and disappear if the object restarts. The provider still processes service/network metadata. Browser project storage is separate; export backups before moving devices.

Cancellation discards the result and prevents its application. A synchronous Python calculation already in flight may finish within Cloudflare's resource limits; cancellation does not claim to interrupt native numerical routines instantly. The shared solver remains busy until that request finishes or times out.

## Free-service limits

The application permits 50 AI questions, 200 scientific jobs and 5,000 summary/simulation requests per UTC day, shared across visitors. Cloudflare's own Free quotas can stop service earlier. No paid upgrade or overage plan is selected. Per-address burst limits are 5 AI requests and 120 other API requests per minute.

Cloudflare Durable Objects have a default 30-second active-CPU limit per invocation and 128 MiB isolate memory. Network/loading time is separate; the gateway times a scientific request out after two minutes. Cold library loading can take a minute. Large fits, imports or traces can exceed the free service's resources; those fail explicitly without invented results or a fallback to the visitor's device. This is a public research/demo service without an availability SLA.

## Reproduce the private Python build

In `Cloudflare Backend`, install Node.js, uv and the pinned Python deployment tooling. Use Python 3.14 for the build tools. `pyproject.toml` pins direct dependencies and `pylock.toml` records the WASM package versions and hashes. The verified numerical versions are NumPy 2.4.6, SciPy 1.18.0, Thermo 0.6.1, chemicals 1.5.2 and fluids 1.3.1; spreadsheet import uses openpyxl 3.1.5.

1. Run `uv run --python 3.14 pywrangler sync` to install the Pyodide packages.
2. Run `uv run --python 3.14 python "Build Scientific Bundle.py"`. The builder copies the original installed packages into generated `python_modules`, preserves NumPy documentation needed during import, removes unused documentation in selected libraries, and defers unused fluids/SciPy optimizer imports. Numeric function bodies are retained. Unused chemical lookup databases are excluded by the Wrangler configuration; PetroMind supplies explicit component properties. Package license files are retained.
3. Run `wrangler deploy` directly from `Cloudflare Backend`. Do not run another package sync between the adaptation step and deployment. The build copies the three scientific modules from `public` into the generated source directory and extracts the existing import reader without loading the EOS for file imports.
4. Deploy the gateway from the repository root with `wrangler deploy`. The existing domain remains `petromind.dana-edu.pp.ua`. No `BACKEND_KEY` or `BACKEND_URL` is needed for this Cloudflare configuration.

Generated environments, vendored packages and copied scientific source are excluded from Git. Rebuild them from the pinned packages and published source. The older Docker, Render and Railway configuration files remain optional alternatives for a larger privately operated backend; they are not used by this release.

## Verification and rollout

Deploy `Hosted Preview.jsonc` before changing the production domain. Run `python "tests/Hosted Cloudflare Checks.py" https://YOUR-PREVIEW-ORIGIN` to exercise public/synthetic fixtures remotely. This covers PVT reference agreement, binary/heavy envelopes, EOS tuning, published brine/solids checks, engineering modules, predictor training, import and hosted AI. The script runs no local numerical models. API/client unit tests use mocked solver responses.

Verify the interface in the KNU work browser using a fresh preview origin so existing saved fluid projects are untouched. After production deployment, verify `/api/status`, a public calculation and the visible result charts. Remove temporary preview/probe services after verification.

References: [Python packages](https://developers.cloudflare.com/workers/languages/python/packages/), [Durable Object limits](https://developers.cloudflare.com/durable-objects/platform/limits/), [Free pricing](https://developers.cloudflare.com/durable-objects/platform/pricing/), [Worker limits](https://developers.cloudflare.com/workers/platform/limits/).
