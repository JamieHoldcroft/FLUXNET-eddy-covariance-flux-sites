# Doing a comparison run

A comparison run is the standard run with one thing changed: a CABLE setting, a different CABLE version, different LAI, or different vegetation patches. This page shows how to do one without overwriting the standard run, and how to compare the two.

**The rule: change one thing, give the run its own folder, and write down what you changed.**

Before you start, do the standard run once (README, "Usage" steps 1–3). You then have `met_cable/` and `cable_runs/` on Gadi to compare against.

## 1. Make a run folder

Every run lives in its own folder under your Gadi working folder. Name it after what's different, for example `cable_runs_medlyn`:

```
cd /scratch/$PROJECT/$USER
mkdir cable_runs_medlyn
cp cable_runs/cable_template.nml cable_runs/run_sites.pbs cable_runs_medlyn/
```

Then add a `README.txt` to that folder, with one or two lines saying what you changed and why. You'll need it in three months.

## 2. Change one thing

| To compare… | Change | Notes |
|---|---|---|
| A CABLE setting (e.g. stomatal conductance, soil water stress) | Edit `cable_runs_medlyn/cable_template.nml` | Change only the line you're testing. Keep `@MET@`, `@SITE@` and `@GRIDINFO@` as they are, because the run script fills them in. |
| A different CABLE version or branch | Clone and build it in its own folder, e.g. `~/CABLE_mybranch`, then submit with `qsub -v CABLE_DIR=$HOME/CABLE_mybranch run_sites.pbs` | Don't rebuild `~/CABLE` in place, or you lose the standard version. |
| LAI source (MODIS vs BoM) | Make a second met folder: `python3 cable_runs/prepare_met_for_cable.py met_raw met_cable_bom --co2-file cable_runs/co2_annmean_mlo.txt --periods site_periods.csv --lai BOM`, then submit with `qsub -v MET_DIR=/scratch/$PROJECT/$USER/met_cable_bom run_sites.pbs` | You can also set LAI per site in the `lai` column of `site_periods.csv`. |
| Vegetation patches | Use `final_patch_run/run_pft_batch.sh NAME CSV` (see README). It makes `met_cable_NAME/` and `cable_runs_NAME/` and submits the job for you. | Average the patches with `combine_patches.py` before you compare. |
| Which years or sites | Copy `site_periods.csv`, edit the copy, and make a new met folder with `--periods your_copy.csv` | Keep in mind that the two runs then cover different days. The comparison script only scores days that are in both. |

## 3. Run it

```
cd /scratch/$PROJECT/$USER/cable_runs_medlyn
qsub run_sites.pbs                 # add -v MET_DIR=... or -v CABLE_DIR=... if you changed those
```

Check it as for the standard run (`grep -c OK cable_sites.o*`, `grep FAILED cable_sites.o*`).

The script also writes two files into the run folder that record what was used:
- `run_info.txt`: the date, the met folder, the CABLE folder and its git commit, and whether the CABLE source was edited since that commit.
- `cable_template_used.nml`: the exact settings.

## 4. Copy back and compare (local computer)

From the repo root, copy both runs back:
```
scp -r <user>@gadi.nci.org.au:/scratch/<project>/<user>/cable_runs        cable_results_standard
scp -r <user>@gadi.nci.org.au:/scratch/<project>/<user>/cable_runs_medlyn cable_results_medlyn
```

Then score them side by side:
```
python scripts/compare_runs.py cable_results_standard cable_results_medlyn
python scripts/compare_runs.py cable_results_standard cable_results_medlyn --measured-only
```

This writes `compare_cable_results_standard_cable_results_medlyn.csv`, with one row per site and variable: the number of days, then bias, r and RMSE for each run, plus a `MEDIAN` row per variable at the end. Both runs are scored on exactly the same days, so any difference comes from the change you made. You can give more than two runs.

For figures of each run against the observations, set `CABLE_DIR` and `OUT_DIR` at the top of `scripts/plot_cable_vs_obs.py` to the run's folder and run it. `compare_runs.py` reads the Flux files from the same `ROOT` as that script, so set `ROOT` there first (README, First-time setup step 2).

## Things that catch people out

- **Multi-patch output must be averaged first.** `compare_runs.py` stops if a file has more than one patch. Run `combine_patches.py` and compare the combined folder.
- **Different CABLE versions can write different output variables.** If a variable is missing from one run, that variable is skipped for that site.
- **Spin-up is on.** Each run spins up from scratch, so two runs differ in their spin-up as well as in the setting you changed. That's intended: it's what a user of each version would get.
