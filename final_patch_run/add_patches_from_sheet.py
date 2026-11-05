"""Add JULES-style vegetation patches to CABLE-ready met files.

Reads the files made by prepare_met_for_cable.py and writes NEW copies with
several vegetation patches per site. The input files are never changed.

    python add_patches_from_sheet.py MET_DIR SHEET_CSV OUT_DIR

    MET_DIR    folder of prepared files (e.g. /scratch/<project>/<user>/met_cable)
    SHEET_CSV  patchfracs_and_pfts.csv (your Google sheet: one row per site,
               column C<n> or C<n>-name (e.g. C2-EBF) = patchfrac of CABLE iveg n, empty = 0;
               sites with no C values are skipped)
    OUT_DIR    new folder for the patched copies (e.g. /scratch/<project>/<user>/met_cable_patches)

Rows with no site name are ignored. Every site with a prepared met file is written,
including single-patch sites (they then get one patch, MODIS LAI and their own hc).
For each one:
  iveg      -> one CABLE vegetation type per patch            (patch, y, x)
  patchfrac -> fraction of the site covered by each patch     (patch, y, x)
  LAI       -> same LAI on every vegetated patch, 0 on bare soil/ice/urban,
               scaled so the area-weighted site mean still equals MODIS
                                                              (time, patch, y, x)
  hc        -> site canopy height for tree patches, CABLE's default
               height for grass/shrub/bare patches            (patch, y, x)
Everything else (weather, CO2, za ...) is copied unchanged.
"""
import csv, glob, os, re, sys
from collections import defaultdict
import numpy as np
import netCDF4

met_dir, patch_csv, out_dir = sys.argv[1:4]
os.makedirs(out_dir, exist_ok=True)

# CABLE default canopy heights (vegin%hc in pft_params.nml) for non-tree types
DEFAULT_HC = {5: 0.6, 6: 0.567, 7: 0.567, 8: 0.567, 9: 0.55, 10: 0.55, 11: 0.567, 14: 0.2}
TREES = {1, 2, 3, 4}
# Patch types that get no leaves: permanent ice (12), urban (13), bare soil (14).
NO_LEAVES = {12, 13, 14}
# Sites CABLE can't start with several patches. AU-Otw is on the coast: with patches,
# CABLE takes starting soil temperature from an ocean grid cell and stops ("Soil temps nuts").
# Only applies if the site has more than one patch.
SKIP = {"AU-Otw": "coastal grid cell: CABLE stops at start-up (Soil temps nuts) with patches or a grass iveg; use the standard run"}

def cable_columns(row):
    """Map CABLE iveg -> column name, from headers like 'C2-EBF', 'C14' or 'C6'."""
    cols = {}
    for name in row:
        m = re.match(r"C(\d+)(?:-|$)", (name or "").strip())
        if m:
            cols[int(m.group(1))] = name
    return cols


table = defaultdict(list)
for r in csv.DictReader(open(patch_csv, encoding="utf-8-sig")):
    site = (r.get("site") or "").strip()
    if not site:
        continue                       # blank or stray rows
    for iv, col in sorted(cable_columns(r).items()):
        v = (r.get(col) or "").strip()
        if v and float(v) > 0:
            table[site].append((iv, float(v), 0.0 if iv in NO_LEAVES else 1.0, col))

report = []
# One output per prepared met file. Segments (AU-Cow_1_2017-2021_...) use their base site's row.
jobs = []
for src in sorted(glob.glob(os.path.join(met_dir, "*_Met.nc"))):
    seg = re.sub(r"_\d{4}-\d{4}_.*", "", os.path.basename(src))
    base = seg.split("_")[0]
    if base in SKIP:
        print(f"{seg}: skipped ({SKIP[base]}); keep its single-patch result")
    elif base not in table:
        print(f"{seg}: {base} not in {os.path.basename(patch_csv)}, skipped")
    else:
        jobs.append((seg, src, table[base]))
for site, src, patches in jobs:
    dst = os.path.join(out_dir, os.path.basename(src))
    iveg = np.array([p[0] for p in patches])
    frac = np.array([p[1] for p in patches])
    ratio = np.array([p[2] for p in patches])
    if (frac * ratio).sum() == 0:
        sys.exit(f"{site}: only bare-soil patches, nowhere to put the LAI")
    if abs(frac.sum() - 1) > 1e-6:
        sys.exit(f"{site}: patch fractions add up to {frac.sum()}, not 1")
    n = len(patches)

    with netCDF4.Dataset(src) as s, netCDF4.Dataset(dst, "w", format="NETCDF4") as d:
        d.setncatts(s.__dict__)
        for name, dim in s.dimensions.items():
            d.createDimension(name, None if dim.isunlimited() else len(dim))
        d.createDimension("patch", n)

        # copy everything except the variables we replace
        for name, v in s.variables.items():
            if name in ("iveg", "LAI", "hc"):
                continue
            o = d.createVariable(name, v.dtype, v.dimensions,
                                 fill_value=getattr(v, "_FillValue", None))
            o.setncatts({k: v.getncattr(k) for k in v.ncattrs() if k != "_FillValue"})
            o[:] = v[:]

        site_hc = float(s["hc"][:].ravel()[0])
        old_iveg = int(s["iveg"][:].ravel()[0])
        if n == 1:
            hc = np.array([site_hc])           # single patch: keep the Run 2 height
        else:
            hc = np.array([site_hc if iv in TREES else DEFAULT_HC.get(iv, site_hc) for iv in iveg])

        def patch_var(name, dtype, values, units, long_name):
            o = d.createVariable(name, dtype, ("patch", "y", "x"))
            o[:] = values.reshape(n, 1, 1)
            o.units, o.long_name = units, long_name

        patch_var("iveg", "i4", iveg, "-", "CABLE vegetation type per patch (from patchfracs_and_pfts.csv)")
        patch_var("patchfrac", "f4", frac, "-", "Fraction of site covered by each patch (from patchfracs_and_pfts.csv)")
        patch_var("hc", "f4", hc, "m", "Canopy height per patch")

        lai = s["LAI"][:].reshape(len(s.dimensions["time"]))
        top = lai / (frac * ratio).sum()          # LAI of each vegetated patch
        lai_p = top[:, None] * ratio[None, :]      # (time, patch)
        o = d.createVariable("LAI", "f4", ("time", "patch", "y", "x"))
        o[:] = lai_p[:, :, None, None]
        o.units = "-"
        o.long_name = "Leaf area index per patch (MODIS, same on every vegetated patch)"
        d.setncattr("cable_patches", f"add_patches.py from {os.path.basename(patch_csv)}")

        check = (lai_p * frac).sum(axis=1)
        err = float(np.abs(check - lai).max())
    # read the new file back and check every patch against the CSV column it came from
    with netCDF4.Dataset(dst) as chk:
        got = list(zip(chk["iveg"][:].ravel().tolist(), chk["patchfrac"][:].ravel().tolist()))
    shown = []
    for (iv_csv, f_csv, _, col), (iv_nc, f_nc) in zip(patches, got):
        if iv_csv != iv_nc or abs(f_csv - f_nc) > 1e-5:
            sys.exit(f"{site}: MISMATCH column {col}={f_csv} but file has iveg {iv_nc} frac {f_nc}")
        shown.append(f"{col}={f_csv:g} -> iveg {iv_nc}")
    print(f"{site} check OK: " + ", ".join(shown))
    note = "" if n > 1 or iveg[0] == old_iveg else f"iveg changed from {old_iveg}"
    report.append((site, n, " ".join(map(str, iveg)), " ".join(f"{f:g}" for f in frac), round(float(lai.mean()), 2), err, note))
    print(f"{site}: {n} patches, iveg {iveg.tolist()}, frac {frac.tolist()}, "
          f"site LAI mean {lai.mean():.2f} (max weighting error {err:.1e}) {note}")

with open(os.path.join(out_dir, "patch_report.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["site", "n_patches", "iveg", "patchfrac", "modis_lai_mean", "max_lai_error", "note"])
    w.writerows(report)
print(f"\n{len(report)} files written to {out_dir}")
missing = sorted(set(table) - {r[0].split("_")[0] for r in report} - set(SKIP))
if missing:
    print("In the sheet but no met file (probably keep = no):", " ".join(missing))
