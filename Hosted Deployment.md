# Hosted PetroMind

All scientific model computation and predictor training run in the Docker backend. Cloudflare hosts static assets, proxies same-origin API requests and runs the Qwen3 assistant with Workers AI. The browser edits inputs, saves projects and renders charts; it never falls back to local model execution.

## Render Free

Create a Docker Web Service from the public Git URL https://github.com/danamohammad/PetroMind, branch main. Use the repository-root Dockerfile, port 10000 and health check `/health`. Select Free, one instance and no persistent disk. Disable automatic deployment until the initial deployment is verified. Set `PETROMIND_BACKEND_KEY` to a securely generated random secret; use the same value as Cloudflare's `BACKEND_KEY`. Do not commit it or place it in frontend code. The service refuses calculations when the secret is absent.

The free service sleeps after inactivity and may take about a minute to wake. One scientific job is admitted at a time; additional requests receive a busy response. Jobs stop at seven minutes. Completed results expire from memory after ten minutes and the browser deletes its job after receiving the result. Restarts discard all jobs. The application writes no input datasets to disk and disables HTTP access logs; hosting providers still process network/service metadata. This is a public research/demo service without an availability SLA.

## Cloudflare

Set `BACKEND_URL` in wrangler vars to the HTTPS Render service origin. Set `BACKEND_KEY` using `wrangler secret put BACKEND_KEY`. Deploy with `wrangler deploy`. The configuration includes the Workers AI binding, SQLite Durable Object daily quotas, request rate limits, static assets and the existing custom domain. No paid plan is required for this configuration. Free account/provider allowances can stop service before the application quotas are reached.

The shared public allowances reset at 00:00 UTC: 50 AI questions, 200 scientific jobs and 5,000 lightweight telemetry requests. Per-address burst limits are approximate Cloudflare-location limits. Addresses are not written into application storage; the daily quota object stores only date and counters. Job IDs are unguessable bearer capabilities and must not be shared; the browser does not persist them. Inputs are accepted only as bounded JSON data, never executable code. No API secret or backend key is exposed to visitors.

## Development and verification

Install Python 3.12 dependencies with `python -m pip install -r "Server Requirements.txt"`. Node.js must be on PATH or specified in `NODE_BINARY`. Run `python "server/Scientific Server.py"` with a temporary development key. For a full local preview, use Wrangler dev with a local configuration containing `BACKEND_URL=http://127.0.0.1:10000`, `LOCAL_TEST=true` and the temporary `BACKEND_KEY`. Never deploy LOCAL_TEST or the temporary key. Local testing is development only; no production service depends on the developer's computer.

Run `python "tests/Hosted Server Tests.py"`, `node --test "tests/Hosted Worker Tests.mjs"` and `node --test "tests/Hosted Client Tests.mjs"`, followed by the existing scientific/data regression suites. Use public or synthetic data for deployment checks. Verify a scientific result, pressure survey, predictor and hosted assistant at the live domain before declaring migration complete. Existing browser-saved calibration records must survive reload unchanged.
