# Known issues

These are problems we know about in the data and in the standard CABLE runs. Check this list before you read too much into a result at one of these sites.

## Data problems at single sites

| Site | Problem | What we did |
|---|---|---|
| AU-APL, AU-Col, AU-Fog, AU-Wac | "No precip": there's no measured rain. It's 100% ERA5 gap-fill, and far too high (AU-Fog gets 5,800–7,200 mm/yr). | Dropped (`keep=no` in `site_periods.csv`). |
| AU-Lox, AU-RDF, AU-Sno, AU-Wel, AU-Wgt | "Too much precip" in `site_periods.csv`. AU-Lox is also irrigated. | Dropped. |
| AU-MvB | Irrigated. CABLE has no irrigation, so it can't reproduce the latent heat. | Dropped. AU-MvA may also be irrigated, so treat it with care. |
| AU-DaS | Bad Psurf readings on 9 Apr 2022, 03:00–04:00, make Qair spike. | Repaired by `prepare_met_for_cable.py`. |
| AU-Wom, AU-TTE, AU-Whr | Long stretches of flat, blocky gap-filled met (e.g. Wom 2021–24, TTE 2022–25, Whr 2022–24). | Cut out by the years in `site_periods.csv`. |
| AU-Rig 2012, AU-Ync 2022, AU-Whr and AU-Stp 2019 | The rain gauge looks dead but is still flagged as measured (e.g. Ync 2022 has 170 mm in a very wet year). | Cut out by the years in `site_periods.csv`. |
| AU-Otw | Coastal grid cell. CABLE stops at start-up with several patches. | Runs as a single patch (EBF). |
| AU-Wac | Measured LWdown looks too high (it equals σT⁴ of air temperature). | Site dropped anyway (no rain). |

## Problems in the standard CABLE runs

- **Sensible heat is too high** at almost every site (37 of 40; median bias about +17 W/m²).
- **NEE is a weak sink.** CASA is off, so NEE isn't expected to be good. Use GPP for carbon.
- **Snow melts late at alpine sites** (seen at AU-APL, Nov–Dec instead of late Sep).
- **Wetlands and floodplains**: CABLE has no flooding, so it misses the latent heat from standing water (AU-Fog).

## Things to know about the pipeline itself

- Scoring uses daily means (a day needs at least 50% valid steps), so the daily cycle doesn't count.
- Gap-filled fluxes are used in scoring unless you add `--measured-only`.
- For multi-patch runs, CABLE writes a garbled `patchfrac` into its output. `combine_patches.py` takes the fractions from the input table instead.
