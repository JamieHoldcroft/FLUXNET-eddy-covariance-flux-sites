#!/usr/bin/env python3
"""Compare two or more CABLE runs against the flux tower observations, site by site.

    python scripts/compare_runs.py cable_results cable_results_test
    python scripts/compare_runs.py cable_results cable_results_test --measured-only
    python scripts/compare_runs.py cable_results_a cable_results_b cable_results_c --out compare_abc.csv

Each RUN_DIR has one folder per site (AU-xxx/AU-xxx_out.nc), as copied back from Gadi.
Only sites that are in every run are compared, and every run is scored on the same
days (days where the obs and all runs have a valid daily mean), so differences come
from the runs and not from different samples.

Scores use the same rules as plot_cable_vs_obs.py, and its ROOT setting: daily means (a day needs at least
50% valid steps), then bias = mean(CABLE - obs), r, and RMSE, for Rnet, Qle, Qh,
GPP and NEE.

Writes one CSV (default: compare_<run1>_<run2>....csv in the current folder) with
one row per site and variable, and a MEDIAN row per variable at the end:
    site, variable, n_days, <run>_bias, <run>_r, <run>_rmse   (for each run)
"""
import argparse
import csv
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plot_cable_vs_obs import FLUX_DIR, VARS, daily_mean, read_series, stats  # same scoring rules


def run_name(path):
    return os.path.basename(os.path.normpath(path))


def sites_in(run_dir):
    return {os.path.basename(d) for d in glob.glob(os.path.join(run_dir, "AU-*"))
            if os.path.exists(os.path.join(d, f"{os.path.basename(d)}_out.nc"))}


def check_one_patch(path):
    """Multi-patch output must be averaged with combine_patches.py first, or only patch 1 is read."""
    import netCDF4
    with netCDF4.Dataset(path) as ds:
        if "patch" in ds.dimensions and ds.dimensions["patch"].size > 1:
            sys.exit(f"{path} has {ds.dimensions['patch'].size} patches. Average them first with\n"
                     "  python final_patch_run/combine_patches.py RAW_DIR PATCH_CSV COMBINED_DIR\n"
                     "and compare the combined folder.")


def daily(times, x, keep):
    """Daily means of x on the timestamps in keep."""
    _, i, _ = np.intersect1d(times, keep, return_indices=True)
    return daily_mean(keep, x[np.sort(i)])


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("run_dirs", nargs="+", help="two or more CABLE result folders")
    p.add_argument("--measured-only", action="store_true",
                   help="use only measured and good gap-filled obs (qc <= 1)")
    p.add_argument("--out", help="output CSV")
    a = p.parse_args()
    if len(a.run_dirs) < 2:
        p.error("give at least two run folders")

    names = [run_name(d) for d in a.run_dirs]
    if len(set(names)) < len(names):
        p.error(f"run folders need different names, got {names}")
    out = a.out or "compare_" + "_".join(names) + ("_measured" if a.measured_only else "") + ".csv"
    qc_max = 1 if a.measured_only else None

    common_sites = sorted(set.intersection(*(sites_in(d) for d in a.run_dirs)))
    for d in a.run_dirs:
        extra = sorted(sites_in(d) - set(common_sites))
        if extra:
            print(f"{run_name(d)}: not in every run, skipped: {' '.join(extra)}")
    if not common_sites:
        sys.exit("no site is in every run")

    for d in a.run_dirs:
        for site in common_sites:
            check_one_patch(os.path.join(d, site, f"{site}_out.nc"))

    rows = []
    for site in common_sites:
        flux = glob.glob(os.path.join(FLUX_DIR, f"{site.split('_')[0]}_*_Flux.nc"))  # AU-Cow_1 -> AU-Cow
        if not flux:
            print(f"{site}: no Flux file, skipped")
            continue
        for var, _, _ in VARS:
            try:
                t_obs, obs = read_series(flux[0], var, qc_max)
                mods = [read_series(os.path.join(d, site, f"{site}_out.nc"), var) for d in a.run_dirs]
            except (KeyError, IndexError):
                continue  # variable missing from a file
            keep = t_obs
            for t_mod, _ in mods:
                keep = np.intersect1d(keep, t_mod)
            if keep.size == 0:
                continue
            _, obs_d = daily(t_obs, obs, keep)
            mod_d = [daily(t, x, keep)[1] for t, x in mods]
            ok = ~np.isnan(obs_d)
            for m in mod_d:
                ok &= ~np.isnan(m)
            row = dict(site=site, variable=var, n_days=int(ok.sum()))
            for name, m in zip(names, mod_d):
                s = stats(obs_d[ok], m[ok])
                for k in ("bias", "r", "rmse"):
                    row[f"{name}_{k}"] = round(s[k], 3)
            rows.append(row)
        print(f"{site}: done")

    cols = ["site", "variable", "n_days"] + [f"{n}_{k}" for n in names for k in ("bias", "r", "rmse")]
    for var, _, _ in VARS:
        sub = [r for r in rows if r["variable"] == var]
        if sub:
            med = dict(site="MEDIAN", variable=var, n_days=int(np.median([r["n_days"] for r in sub])))
            for c in cols[3:]:
                med[c] = round(float(np.nanmedian([r[c] for r in sub])), 3)
            rows.append(med)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"\n{len(common_sites)} sites compared. Written to {out}")


if __name__ == "__main__":
    main()
