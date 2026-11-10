# Extending the PLUMBER2-style flux site data: CABLE at the Australian flux sites

This repo turns the FLUXNET Shuttle data for the 42 Australian flux sites (as downloaded from the FLUXNET data portal) into PLUMBER2-style NetCDF met and flux files. It adds MODIS and BoM LAI to them, runs the CABLE land surface model offline at every site on NCI's Gadi supercomputer, and compares CABLE with the observations.

The processing follows the PLUMBER2 workflow ([PLUMBER2 Github](https://github.com/aukkola/PLUMBER2), [FluxnetLSM Github](https://github.com/aukkola/FluxnetLSM)). The paths and a few steps are adapted for the newer FLUXNET Shuttle files.

The work happens in two places:
- **Local computer** (Windows, Mac or Linux) does the data processing in R and the plotting in Python.
- **Gadi** runs CABLE. You need an NCI account and membership of an NCI project.

## The pipeline in one picture

```
 LOCAL COMPUTER                                                                    GADI
 FLUXNET zips ─► process_fluxnet_step1.R ─► Nc_files/Met + Flux                    
 MODIS LAI ─► get_modis_lai.R ─► add_modis_lai_to_met.R ─┐
 BoM LAI ──────────────────────► add_bom_lai_to_met.R  ──┴► Nc_files/Met_with_LAI ──scp──► met_raw/
                                                                                     │ prepare_met_for_cable.py
                                                                                     │   + site_periods.csv
                                                                                     ▼
                                                                    met_cable/ ─► run_sites.pbs (CABLE)
                                                                                     │
 plot_cable_vs_obs.py ◄────────────── cable_results/ ◄────────────scp──────────── cable_runs/AU-xxx/
```

## Folder structure

Some files are large or downloaded, so they aren't in the Github, but their respective folders (marked 'not in git') are kept via .gitkeep. [First-time setup](#first-time-setup) explains how to get them.

```
extending-plumber2-flux-sites/
├── README.md
├── site_periods.csv            Years used at each site (site,start_year,end_year,keep,notes)
├── scripts/                    Processing and plotting scripts, run on local computer (described below)
├── gadi/                       Everything that gets copied to Gadi to run CABLE
├── final_patch_run/            Extra files for the multi-patch (4D LAI) CABLE run
├── FLUXNET/                    (not in git) TERN_AU-xxx_FLUXNET_..._v1.3_r1.zip, one per site
├── BOM_LAI/                    (not in git) lai_bom_<year>_Jul2025.nc, BoM 5 km monthly LAI
├── FluxnetLSM/                 (not in git) FluxnetLSM R package (functions used by Step1)
├── PLUMBER2/                   (not in git) Original PLUMBER2 scripts; scripts/ uses its functions/
├── cable_results/              (not in git) CABLE output copied back from Gadi, one folder per site
└── processed/                  (not in git) Everything the scripts make
    ├── FLUXNET_Original_data/      CSVs taken out of the zips by Step1 (made by Step1)
    ├── step1_fluxnet_summary.csv   Step1 result per site (ok / FAILED and why)
    ├── FLUXNET2015_sites/
    │   ├── Logs/                   Step1 log per site (warnings and errors)
    │   ├── Nc_files/Met/           Met forcing, AU-xxx_YYYY-YYYY_FLUXNET2015_Met.nc
    │   ├── Nc_files/Met_with_LAI/  Same, plus LAI_MODIS and LAI_BOM (the files CABLE uses)
    │   ├── Nc_files/Flux/          Observed fluxes (Rnet, Qle, Qh, GPP, NEE, with _qc flags)
    │   └── Figures/                Per-site figures, including CABLE vs obs
    ├── MODIS_LAI_time_series/      Raw MODIS downloads (Raw_data/, yearly_chunks/)
    ├── diagnose_LAI_figures/       MODIS and BoM LAI processing-step figures
    └── site_selection_figs/        One quick-look figure per site: met, flux and LAI time series
```

## Scripts

### `scripts/` (run locally in this order)

| Script | Language | What it does |
|---|---|---|
| `process_fluxnet_step1.R` | R | The FLUXNET2015 part of PLUMBER2 Step1. It takes the FLUXMET_HH and ERA5_HH files out of each zip in `FLUXNET/`, renames them as FluxnetLSM expects, and writes `Nc_files/Met` and `Nc_files/Flux`. |
| `get_modis_lai.R` | R | Downloads MODIS MCD15A2H LAI for each site, one year at a time and with retries, into `MODIS_LAI_time_series/`. If it stops, run it again and it carries on. |
| `add_modis_lai_to_met.R` | R | PLUMBER2 Step2. Cleans and smooths MODIS LAI, then writes it as `LAI_MODIS` into copies of the met files in `Nc_files/Met_with_LAI`. |
| `add_bom_lai_to_met.R` | R | PLUMBER2 Step3, using BoM LAI instead of Copernicus. Adds `LAI_BOM` to the files in `Met_with_LAI`. |
| `diagnose_modis.R`, `diagnose_bom.R` | R | Optional. For each site, a figure of the LAI after each processing step, saved in `diagnose_LAI_figures/`. |
| `plot_diagnostics.R` | R | Site-selection figures: met, flux and LAI time series per site, with gap-filled data in grey. Saved in `site_selection_figs/`. |
| `plot_cable_vs_obs.py` | Python | Plots observed vs CABLE daily Rnet, Qle, Qh, GPP and NEE at each site and prints bias, r and RMSE. Set `CABLE_DIR` and `OUT_DIR` at the top. |

### `gadi/` (copied to Gadi)

| File | What it does |
|---|---|
| `prepare_met_for_cable.py` | Makes CABLE-ready met files from `Met_with_LAI`. It trims each site to the years in `site_periods.csv` (1 Jan of the start year to 31 Dec of the end year) and skips sites with `keep=no`. It uses MODIS LAI and replaces CO2 with NOAA Mauna Loa annual means. It also repairs bad Psurf spikes and impossible Qair, and sets the vegetation type. It writes `prep_report.csv`. |
| `co2_annmean_mlo.txt` | NOAA Mauna Loa annual mean CO2. |
| `cable_template.nml` | CABLE settings: Leuning stomatal conductance, spin-up on, CASA off. |
| `run_sites.pbs` | PBS job that runs CABLE at every site in parallel, one folder per site. |

### `final_patch_run/` (optional multi-patch run with 4D LAI)

| File | What it does |
|---|---|
| `patchfracs_and_pfts.csv` | For each site, column `C<n>` is the fraction of CABLE vegetation type `n`. Column order doesn't matter. |
| `add_patches_from_sheet.py` | Makes a patched copy of each prepared met file, with `iveg`, `patchfrac` and `hc` per patch and `LAI(time, patch, y, x)`. Every vegetated patch gets the same LAI and bare soil gets 0, so the site mean still equals MODIS. It prints a `check OK` line per site. AU-Otw is skipped if it has more than one patch, because CABLE crashes at coastal multi-patch sites. |
| `run_pft_batch.sh` | Run on Gadi. Builds `met_cable_<name>/` and `cable_runs_<name>/`, then submits the job. |
| `combine_patches.py` | Run on local computer afterwards. Averages each site's patches, weighted by their fractions, so the plotting script works unchanged. |

## First-time setup

### 1. Download the inputs

| What | Where from | Put it in |
|---|---|---|
| Flux site data (FLUXNET Shuttle) | FLUXNET data portal, https://data.fluxnet.org/data/ (the AU sites) | `FLUXNET/`, left zipped |
| PLUMBER2 scripts | https://github.com/aukkola/PLUMBER2 | `PLUMBER2/` |
| FluxnetLSM R package | https://github.com/aukkola/FluxnetLSM | `FluxnetLSM/` |
| MODIS LAI (MCD15A2H) | Downloaded for you by `scripts/get_modis_lai.R` | `processed/MODIS_LAI_time_series/` |
| BoM LAI (5 km monthly, `lai_bom_<year>_Jul2025.nc`) | Bureau of Meteorology | `BOM_LAI/` |
| CABLE source code | https://github.com/CABLE-LSM/CABLE | Gadi (see step 3) |

`gadi/co2_annmean_mlo.txt` is already in the repo. To update it, download the annual mean file from https://gml.noaa.gov/ccgg/trends/data.html.

### 2. Point the scripts at your copy of the repo

The scripts contain the full path of the original author's folder (`C:/Users/jamie/extending-plumber2-flux-sites`). Replace it with the path of your own copy. It's set near the top of each script:

| Script | Variable(s) |
|---|---|
| `process_fluxnet_step1.R` | `zip_path`, `out_path` |
| `get_modis_lai.R`, `add_modis_lai_to_met.R`, `diagnose_modis.R` | `path` |
| `add_bom_lai_to_met.R`, `diagnose_bom.R` | `path`, `lai_path` |
| `plot_diagnostics.R` | `path` and the `source(...)` line |
| `plot_cable_vs_obs.py` | `ROOT` |

### 3. Set up Gadi (once)

You need an NCI account (https://my.nci.org.au) and membership of an NCI project. Below, `<user>` is your NCI username and `<project>` is your project code. The scripts work them out for themselves on Gadi, from `$USER` and `$PROJECT`. To log in:

```
ssh <user>@gadi.nci.org.au
```

**Build CABLE in your home folder:**
```
cd ~
git clone https://github.com/CABLE-LSM/CABLE.git
cd CABLE && ./build.bash          # makes ~/CABLE/bin/cable
```
Clone it on Gadi rather than copying it from Windows, because Windows line endings break the build.

**Make the working folder:**
```
mkdir -p /scratch/<project>/<user>/{met_raw,cable_runs,tmp}
```
Keep `tmp/` even though it stays empty. If your login sets `TMPDIR` to a folder that doesn't exist, `qsub` fails with a `mkstemp` error.

**Edit `gadi/run_sites.pbs`:** change the two lines that say `dt6` (`#PBS -P` and `#PBS -l storage`) to your project code. PBS can't read these from your environment.

**Copy the files over** from the repo root on your computer:
```
scp gadi/* site_periods.csv <user>@gadi.nci.org.au:/scratch/<project>/<user>/cable_runs/
scp processed/FLUXNET2015_sites/Nc_files/Met_with_LAI/*.nc <user>@gadi.nci.org.au:/scratch/<project>/<user>/met_raw/
```
Then, on Gadi, move `site_periods.csv` up one level:
```
cd /scratch/<project>/<user> && mv cable_runs/site_periods.csv .
```

The working folder on Gadi should then look like this:
```
/scratch/<project>/<user>/
├── met_raw/            Met_with_LAI files from local computer (never edited)
├── site_periods.csv
├── met_cable/          made by prepare_met_for_cable.py
├── cable_runs/         the gadi/ files; results appear here as AU-xxx/AU-xxx_out.nc
└── tmp/
```

## Usage

### 1. Make the met and flux files (local computer)

Run these in R from the repo root, in this order:
```
source("scripts/process_fluxnet_step1.R")   # makes Nc_files/Met and Nc_files/Flux
source("scripts/get_modis_lai.R")           # MODIS download (slow; resumable)
source("scripts/add_modis_lai_to_met.R")    # makes Nc_files/Met_with_LAI with LAI_MODIS
source("scripts/add_bom_lai_to_met.R")      # adds LAI_BOM
source("scripts/plot_diagnostics.R")        # site_selection_figs, to check the data
```
Step1 prints a summary table at the end (also saved as `processed/step1_fluxnet_summary.csv`). Every site should say `ok`. The many "Could not find QC flag" messages are normal. To redo only some sites, set `only_site <- c("AU-Wac")` near the top of `process_fluxnet_step1.R`, and set it back to `c()` afterwards.

Look through `processed/site_selection_figs/` for bad data before running CABLE.

### 2. Run CABLE (Gadi)

```
cd /scratch/$PROJECT/$USER
module load python3/3.11.7        # a Python with netCDF4
rm -rf met_cable
python3 cable_runs/prepare_met_for_cable.py met_raw met_cable --co2-file cable_runs/co2_annmean_mlo.txt --periods site_periods.csv
rm -rf cable_runs/AU-* cable_runs/cable_sites.o*      # clear any old results
cd cable_runs && qsub run_sites.pbs
```

`qstat -u $USER` shows the job and prints nothing once it has finished, usually within an hour. Then:
```
grep -c OK cable_sites.o*      # should equal the number of sites
grep FAILED cable_sites.o*     # should print nothing
```
If a site failed, look at `cable_runs/AU-xxx/stdout.txt`.

### 3. Copy back and plot (local computer)

```
scp -r <user>@gadi.nci.org.au:/scratch/<project>/<user>/cable_runs cable_results
python scripts/plot_cable_vs_obs.py        # with CABLE_DIR = cable_results
```

### Optional: multi-patch run (4D LAI)

Edit `final_patch_run/patchfracs_and_pfts.csv` and do the standard run above first, so that `met_cable/` exists. Then:
```
scp final_patch_run/add_patches_from_sheet.py final_patch_run/run_pft_batch.sh final_patch_run/patchfracs_and_pfts.csv <user>@gadi.nci.org.au:/scratch/<project>/<user>/

# on Gadi
cd /scratch/$PROJECT/$USER && rm -rf met_cable_patches cable_runs_patches
bash run_pft_batch.sh patches patchfracs_and_pfts.csv

# back on your computer, when the job has finished
scp -r <user>@gadi.nci.org.au:/scratch/<project>/<user>/cable_runs_patches cable_results_patches_raw
python final_patch_run/combine_patches.py cable_results_patches_raw final_patch_run/patchfracs_and_pfts.csv cable_results_patches
```
Then plot with `CABLE_DIR = cable_results_patches`.

## `site_periods.csv`

There is one row per site: `site,start_year,end_year,keep,notes`. `keep=no` drops a site; for example, AU-Lox and AU-MvB are irrigated, and CABLE has no irrigation. After changing the file, copy it to Gadi and redo the prep step and the run.

## Known data issues

- **AU-DaS, 9 Apr 2022, 03:00–04:00:** bad Psurf readings make Qair spike. `prepare_met_for_cable.py` repairs this on Gadi. 
- **Rain is entirely ERA5 gap-fill** at AU-Fog, AU-APL, AU-Col and AU-Wac.
