# Hosted PetroMind

All scientific model computation and predictor training run in the Docker backend. Cloudflare hosts static assets, proxies same-origin API requests and runs the Qwen3 assistant with Workers AI. The browser edits inputs, saves projects and renders charts; it never falls back to local model execution.

## Railway Free — no-card deployment

Deployment is pending account authorization and hosted verification. This source configuration does not mean the live domain has switched to hosted computation.

Use Railway's Free plan, with no payment method, paid subscription, volume or additional service. Its published allowance is $5 for the initial 30-day trial, followed by $1 per month without rollover. This is limited free hosting, not unlimited compute: exhaustion stops service. The post-trial service limit is one replica, 0.5 GB RAM and up to 1 vCPU. Confirm the account's actual limits before deploying; account verification can restrict network access.

Create one Docker service from the public PetroMind repository. Set the Railway config-file path to `/Railway Deployment.json`. It selects the existing Dockerfile, one replica, idle sleeping, `/health` and at most two restarts on failure. Keep Serverless enabled and verify it on the resulting deployment; the setting takes effect on newly deployed containers. The server already reads Railway's `PORT` and binds to `0.0.0.0`. Use a Railway-generated HTTPS domain behind the existing Cloudflare gateway. Keep GitHub automatic deploys off until the hosted checks pass.

Set `PETROMIND_BACKEND_KEY` as a Railway secret and the same value as Cloudflare's `BACKEND_KEY`, after authorizing the new secret destination. Never commit the key. Set Cloudflare `BACKEND_URL` to the actual verified Railway HTTPS origin. No local machine or browser runs the scientific models.

Railway sleeps idle services after approximately 5–10 minutes without outbound traffic. Do not add keep-alive pings. The server imports the scientific stack only inside a calculation subprocess and releases it when the job finishes. The existing browser polling lasts only for active jobs, except for explicitly active telemetry views. Stop simulated/live telemetry when finished; repeated requests consume the shared free allowance. The app's daily request limits do not guarantee remaining provider credit.

References: [Free plan and trial](https://docs.railway.com/pricing/free-trial), [pricing and resource limits](https://railway.com/pricing), [serverless sleeping](https://docs.railway.com/deployments/serverless), [configuration schema](https://railway.com/railway.schema.json).

## Render Free — alternative requiring verification for this account

Create a Docker Web Service from the public Git URL https://github.com/danamohammad/PetroMind, branch main. Use the repository-root Dockerfile, port 10000 and health check `/health`. Select Free, one instance and no persistent disk. Disable automatic deployment until the initial deployment is verified. Set `PETROMIND_BACKEND_KEY` to a securely generated random secret; use the same value as Cloudflare's `BACKEND_KEY`. Do not commit it or place it in frontend code. The service refuses calculations when the secret is absent.

The free service sleeps after inactivity and may take about a minute to wake. One scientific job is admitted at a time; additional requests receive a busy response. Jobs stop at seven minutes. Completed results expire from memory after ten minutes and the browser deletes its job after receiving the result. Restarts discard all jobs. The application writes no input datasets to disk and disables HTTP access logs; hosting providers still process network/service metadata. This is a public research/demo service without an availability SLA.

## Cloudflare

Set `BACKEND_URL` in wrangler vars to the verified HTTPS scientific-service origin. Set `BACKEND_KEY` using `wrangler secret put BACKEND_KEY`. Deploy with `wrangler deploy`. The configuration includes the Workers AI binding, SQLite Durable Object daily quotas, request rate limits, static assets and the existing custom domain. No paid plan is required for this configuration. Free account/provider allowances can stop service before the application quotas are reached.

The shared public allowances reset at 00:00 UTC: 50 AI questions, 200 scientific jobs and 5,000 lightweight telemetry requests. Per-address burst limits are approximate Cloudflare-location limits. Addresses are not written into application storage; the daily quota object stores only date and counters. Job IDs are unguessable bearer capabilities and must not be shared; the browser does not persist them. Inputs are accepted only as bounded JSON data, never executable code. No API secret or backend key is exposed to visitors.

## Development and verification

Install Python 3.12 dependencies with `python -m pip install -r "Server Requirements.txt"`. Node.js must be on PATH or specified in `NODE_BINARY`. Run `python "server/Scientific Server.py"` with a temporary development key. For a full local preview, use Wrangler dev with a local configuration containing `BACKEND_URL=http://127.0.0.1:10000`, `LOCAL_TEST=true` and the temporary `BACKEND_KEY`. Never deploy LOCAL_TEST or the temporary key. Local testing is development only; no production service depends on the developer's computer.

Run `python "tests/Hosted Server Tests.py"`, `node --test "tests/Hosted Worker Tests.mjs"` and `node --test "tests/Hosted Client Tests.mjs"`, followed by the existing scientific/data regression suites. Use public or synthetic data for deployment checks. Verify a scientific result, pressure survey, predictor and hosted assistant at the live domain before declaring migration complete. Existing browser-saved calibration records must survive reload unchanged.
