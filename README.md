# PetroMind

An open petroleum engineering workbench for fluid composition, vapor–liquid equilibrium, surface PVT, laboratory comparisons and production time series.

Live site: https://petromind.dana-edu.pp.ua

## Use it

1. Load the supplied example or import a composition CSV/Excel file. You can edit every mole fraction and component property directly.
2. Check the composition total. Normalize only when that is appropriate for your data.
3. Enter reservoir, separator, stock-tank and standard-gas conditions. Fluid-workbench pressures are absolute (psia), temperatures are Celsius. The separate flow-assurance studies retain their source units, including MPag for the wax experiments.
4. Click **Calculate fluid properties**. The first calculation loads scientific Python and dependencies; subsequent calculations reuse them.
5. Choose a PVT property, zoom the chart, download PNG, export the calculated CSV, or print to PDF.
6. Use **Phase behavior → Trace phase envelope**. Adaptive continuation follows bubble and dew branches through turning points. It reports a verified mixture critical point, cricondentherm and cricondenbar. A complete trace must return to the chosen pressure floor on both branches; limits or numerical failures are marked partial.
7. Use **Laboratory & tuning** to enter or import measured Bo, Rs, Bg, liquid density, bubble pressure or CCE relative volume (total volume / saturated-liquid volume at the same temperature). Compare first, select up to six bounded parameters, then fit. Review the diagnostics before **Apply fitted parameters**. Revert is available, and both fit reports and prediction tables can be exported. The synthetic tuning demo tests recovery of a known interaction; it is not laboratory calibration.
8. Use **Production trends** to import dates, oil rates and optional water rates, or enter them manually. The example is explicitly synthetic.
9. **Save project** stores inputs in this browser. **Export project** creates a portable JSON backup. Import it on another device to continue.

## Privacy and persistence

All scientific computation and imported-data processing happen in the visitor's browser. There is no user-data API, database, shared project store or analytics tracker. The active project (including its calibration record and edits) is automatically saved in this browser and restored on reload. The supplied demonstration is used only when no active project is available. Named saved projects and the active project use localStorage and can be lost when browser data is cleared. Download backups. Static hosting and library/font providers receive normal asset requests (including IP address), but no datasets are sent to them by this application.

## Scientific scope

Thermo 0.6.1 provides PR, PR78 and SRK vapor–liquid equilibrium. Pyodide 0.29.0 runs the same Python engine in a Web Worker. Plotly draws actual calculated points. Component properties and default PR interactions come from ThermoPack 2.2.3; the original supplied pseudocomponent assumptions are preserved and editable.

The supplied example is an uncalibrated research model; each user fluid must be calibrated separately. Agreement with another EOS implementation is numerical verification, not validation against laboratory measurements. Heavy-cut labels must represent non-overlapping fractions. The Brine & solids workspace provides separate NaCl brine properties, ideal multisolid wax equilibrium and binary Flory–Huggins liquid–liquid asphaltene separation. These are not coupled to the hydrocarbon VLE flash. The older Flow assurance workspace retains empirical wax pressure-trend calibration and measured asphaltene-onset comparisons. Component-linear volume translation is available in both phases, with optional linear temperature slopes about 298.15 K. VLE is unchanged; translated volumes must remain positive. This release provides no caloric properties. Bounded local least-squares fitting adjusts selected interactions or pseudocomponent Tc/Pc/acentric factors, volume shifts, temperature slopes or LBC viscosity critical volumes. It uses scaled residuals and equal total weight per property; zero values have explicit scale floors. Rank-deficient or nonconverged fits cannot be applied. Boundary hits are disclosed. Fitting data are not independent validation. No generative-AI service is used.

Phase-envelope tracing uses log K, log T and log P equilibrium equations with adaptive pseudo-arclength steps and a fixed log-K specification near criticality. Scaled residuals reject trivial solutions. The mixture critical point satisfies a zero minimum stability eigenvalue and zero third derivative along its eigenvector. Maxima are refined separately; they are not used as critical-point guesses. This follows a connected V–L envelope; disconnected branches, LLE and solids are outside scope. Numerical failures retain only converged points. Production forecasts are simple exponential historical baselines with no economic limit, operational constraints or calibrated uncertainty band.

## Implementation

- `public/Fluid Engine.py`: validated inputs, EOS construction, flash, separator train, PVT sweep, saturation, continuation, mixture criticality, CCE volume and bounded laboratory fitting.
- `public/Calculation Worker.js`: pinned browser Python runtime and request dispatch.
- `public/App.mjs`: UI, input editing, charts, imports, project storage and export.
- `public/Data Tools.mjs`: CSV parser, CSV export protection and production analysis.
- `references/ThermoPack Comparison.json`: independent-engine comparisons for four fluids/states.
- `tests/Engine Tests.py`, `tests/Advanced EOS Tests.py`, `tests/Data Tests.mjs`: physical/data invariants, continuation, partial-trace handling, synthetic fitting, held-out prediction and import/export checks.
- `tests/Envelope Crosscheck.py` and `references/Envelope Comparison.json`: reproducible independent ThermoPack checks of binary PR/SRK and heavy PR envelope critical points and maxima.

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
'Validation Environment/bin/python' 'tests/Advanced EOS Tests.py'
'Validation Environment/bin/python' 'tests/Envelope Crosscheck.py'
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

## Calibration records

Project imports can include a sample-specific calibration record with source table/page provenance, fitting and held-out metrics, lump definitions and qualifications. A fitted model status applies only while its composition, EOS and parameters match that record. The public repository does not include private laboratory reports or project exports. No single calibration is valid for every fluid. CCE data and differential liberation are different experiments: do not compare differential-liberation Bo/Rs to a separator-flash prediction.

Method references: [phase-envelope equations](https://thermotools.github.io/thermopack/memo/envelopes/envelopes.pdf), [mixture criticality](https://thermotools.github.io/thermopack/memo/critical/critical.pdf).

## Version 1.2 laboratory workflows

Ordered differential-liberation, multi-stage separator and viscosity protocols retain every gas-removal stage. The common residual-oil reference and ideal standard-gas reference are explicit. Laboratory gas FVF is ft³/scf; the main workbench Bg uses RB/SCF and a real-gas reference. These conventions must not be mixed.

Protocols import/export as JSON. Stage pressures, property values and training/validation/derived roles are editable. Automatic fitting excludes validation/derived observations and experiments disabled for fitting, in both UI and engine. Curves and CSV exports distinguish thermodynamic predictions from shape-preserving PCHIP interpolation of training measurements. Interpolation has no extrapolation or cross-temperature mixing.

LBC viscosities are available only when all active components have positive viscosity critical-volume inputs. Their calibration is distinct from equilibrium fitting. Volume translation uses `V = V_EOS - sum(x_i * (c_i + cT_i * (T - 298.15)))`; units are m³/mol and m³/mol/K. A zero shift and zero slope preserve prior numerical results. Slopes should be validated over the temperature range used.

Private field reports, extracted measurements, fitted projects and rejected candidates are kept outside this public source tree. A wider bound or lower fitting objective alone is not evidence that a characterization is physically acceptable. Imported records retain holdout errors, coverage, exclusions and unresolved issues.

Version 1.2 did not include brine, wax or asphaltene physical models; version 1.4 adds the separate models described below. Quality contours and statistical confidence intervals remain outside scope. The application is not fully field validated.


## Version 1.3: published flow-assurance reference cases

Open **Flow assurance**, choose a published case, and click **Load selected study**. Wax cases support **Fit empirical trend**, in-range evaluation, editable observations, training/validation roles, CSV result export, JSON import/export and separate browser saves. These studies do not change the active EOS project. Flow studies use their own save/export buttons; project JSON covers the EOS workspace.

- **Wax:** Tai et al., ACS Omega (2026), DOI [10.1021/acsomega.5c06286](https://doi.org/10.1021/acsomega.5c06286), Table 5. First-crystallization means and reported standard deviations, converted from kelvin to Celsius. Natural-gas and nitrogen pressurization are separate cases. The experimental procedure specifies **MPa gauge**, retained as MPag. These are gas-pressurized dead-oil calorimeter experiments, not the private Halfaya/Sarta live fluids.
- **Asphaltene:** Ali, Al-Jawad & Ali, Journal of Engineering (2019), DOI [10.31026/j.eng.2019.08.08](https://doi.org/10.31026/j.eng.2019.08.08), pp. 117 and 122. HFx1 / Sadi formation: upper onset **7015 psia at 86.1 °C**; reservoir pressure 4406.6 psia. The single measured onset supports a temperature-specific pressure comparison. It cannot identify an onset envelope, lower boundary, precipitated quantity or model parameters. This sample is different from HF-003 / 28873-IB.

Wax fits use weighted linear least squares, weight = 1 / SD². Two conditions (2.5 and 12.5 MPag) are held out; six train the two coefficients. This selection and regression are PetroMind's analysis, not a model claimed by the authors. Natural-gas held-out RMSE is 0.2421 °C, maximum error 0.3416 °C; nitrogen held-out RMSE is 0.08135 °C, maximum error 0.08268 °C. Error bars describe reported replicate scatter; no model confidence intervals are claimed. Predictions outside the training span are disabled. Validation/reference rows never enter fitting. Four distinct training conditions are required; mixed known/unknown training uncertainties are rejected.

Public case values are attributed factual transcriptions. No private laboratory reports or full journal articles are redistributed. Edits are labeled user studies; source provenance remains visible. The experimental references do not establish field validation or calibration for another sample. Version 1.4 adds a NaCl property model and fitting controls; sample-specific brine calibration still requires matching measurements.

Run `node 'tests/Flow Assurance Tests.mjs'` for the nine new checks covering source units, weighted fits, held-out isolation, range guards, temperature-specific onset comparisons and invalid data. Reference coefficients and results are in `references/Flow Assurance Checks.json`.

## Version 1.4 · physical brine and solids models

Open **Brine & solids**, load a reference study, enter conditions, and calculate. Curves and measurement comparisons export to CSV; study JSON includes inputs and full results. Studies save separately in browser storage. For a new fluid, choose **Start my own study**, enter its identity and source, add measurements, and assign training/validation roles. Reference rows never train the fit. Refit after editing; results invalidate on input changes.

- **NaCl brine:** Kestin viscosity and Rowe–Chou density, kinematic viscosity, compressibility and Bw relative to 20 °C / 0.1 MPa. Published coefficients are laboratory-correlated. Eight pairs of reference-table checks verify the implementation; these are not independent laboratory validation. Sample calibration can fit density and viscosity multipliers within ±5% / ±10%. Only gas-free NaCl water, 20–150 °C, 0.1–35 MPa, 0–6 mol/kg water. Conservative pure-water vapor-pressure guard.
- **Wax:** ideal-liquid / separate-pure-solid equilibrium for up to 30 explicit components. Solves liquid amount with component conservation, computes wax appearance, precipitated mass and phase compositions. Optional solid transition, heat capacity and molar-volume pressure terms. Binary C40/heptane and C50/heptane cooling-DSC examples fit an effective enthalpy multiplier using 5 training and 2 held-out observations each. Held-out onset RMSE: **0.1884 °C** and **0.4030 °C**. These fits represent cooling onset, not validated equilibrium melting, multicomponent yield or deposition rate.
- **Asphaltene:** binary Flory–Huggins common-tangent solution, with a fixed-composition toluene/alkane carrier. Both phases contain carrier; the lever rule conserves volume and asphaltene mass. Reports Gibbs-energy reduction and chemical-potential residual. Nine measured onset mixtures fit effective molar volume and solubility parameter, with three held out. Held-out onset RMSE **0.02339 mass fraction**, or **2.34 wt% percentage points**. Rank 2/2, no parameter bounds reached. Applies to the isolated C7-insoluble reference fraction at **25 °C / 0.1 MPa**. The assumed 1200 kg/m³ asphaltene density is explicit. Yield, reservoir pressure envelopes, resin association, polydispersity and deposition kinetics are not validated or inferred.

No reference calibration is transferred to Halfaya or Sarta. These modules are physical calculations within stated models, not a universal coupled water–vapor–liquid–solid simulator. Mixed salts, aqueous gas solubility, hydrates, mixed wax crystals, carrier fractionation and solids transport require additional models and matching data.

### Reproducible evidence

`public/Physical Models.py` contains equations and input checks. `public/Physical Model Studies.json` contains the attributed public datasets, split roles and fitted parameters. `references/Physical Model Validation.json` contains every predicted/observed comparison. `tests/Physical Model Tests.py` checks conservation, binodal equality, Gibbs reduction, analytic binary wax lever rule, onset continuity, brine derivatives, table reproduction, fitting, held-out separation and domain rejection.

Sources: [Kestin et al. (1981)](https://doi.org/10.1063/1.555641); [Zhou et al. (2026)](https://doi.org/10.3390/pr14081207); [Mohammadi & Richon (2008), Table 1, reproducing Cimino measurements](https://benthamopen.com/contents/pdf/TOTHERJ/TOTHERJ-2-82.pdf). Carrier properties use thermo 0.6.1 HEOS fits at 298.15 K. No ANN predictions were used as calibration measurements.

Source corrections: wax mole fractions are recalculated from mass fractions; inconsistent C38 and C44 entries are excluded. The NaCl specific-volume quadratic salt term includes its concentration factor `−0.5 w H(T) p²`, omitted in the printed NIST equation; this reproduces the dynamic/kinematic table ratios for both water and 6 molal brine within rounding. Density checks use those rounded table ratios, not direct density observations.

Project restoration checks: `node "tests/Project State Tests.mjs"` verifies persistence, calibration identity, synthetic labels and stale-fit status. Imports with calibration evidence must match its composition, EOS and final applied parameters. Private project data remains outside the public repository.
