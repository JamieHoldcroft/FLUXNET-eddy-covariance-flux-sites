"""Turn multi-patch CABLE output into site averages so plot_cable_vs_obs.py works unchanged.

    python combine_patches.py RESULTS_DIR PATCH_CSV OUT_DIR

    RESULTS_DIR  folder with one sub-folder per site (AU-xxx/AU-xxx_out.nc), e.g. cable_results_run4
    PATCH_CSV    jules_patches_22_sites.csv (the patch fractions used for the run)
    OUT_DIR      new folder, same layout, e.g. cable_results_run4_combined

Every variable with a patch dimension is replaced by the fraction-weighted average
over patches (patch dimension kept, length 1). The fractions come from PATCH_CSV,
because CABLE writes a garbled patchfrac into its output file.
The original output files are not changed.
"""
import csv, re, glob, os, sys
from collections import defaultdict
import numpy as np
import netCDF4

results_dir, patch_csv, out_dir = sys.argv[1:4]

def cable_columns(row):
    """Map CABLE iveg -> column name, from headers like 'C2-EBF', 'C14' or 'C6'."""
    cols = {}
    for name in row:
        m = re.match(r"C(\d+)(?:-|$)", (name or "").strip())
        if m:
            cols[int(m.group(1))] = name
    return cols


fracs = defaultdict(list)
for r in csv.DictReader(open(patch_csv, encoding="utf-8-sig")):
    site = (r.get("site") or "").strip()
    if not site:
        continue
    if "patchfrac" in r:                       # old long table (one row per patch)
        fracs[site].append(float(r["patchfrac"]))
    else:                                      # patchfracs_and_pfts.csv: C1..C14, same order as add_patches_from_sheet.py
        f = [float(r[c]) for _, c in sorted(cable_columns(r).items()) if (r.get(c) or "").strip() and float(r[c]) > 0]
        if f:
            fracs[site] = f

for src in sorted(glob.glob(os.path.join(results_dir, "AU-*", "AU-*_out.nc"))):
    site = os.path.basename(os.path.dirname(src))    # folder name, e.g. AU-Cow or AU-Cow_1
    dst_dir = os.path.join(out_dir, site)
    base = site.split("_")[0]                         # segments use their base site's fractions
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, os.path.basename(src))
    with netCDF4.Dataset(src) as s, netCDF4.Dataset(dst, "w", format="NETCDF4") as d:
        n = len(s.dimensions["patch"]) if "patch" in s.dimensions else 1
        if n > 1 and len(fracs[base]) != n:
            sys.exit(f"{site}: output has {n} patches but the CSV lists {len(fracs[base])}")
        w = np.array(fracs[base]) if n > 1 else np.ones(1)
        d.setncatts(s.__dict__)
        for name, dim in s.dimensions.items():
            # fixed sizes (no unlimited time): writing to an unlimited dimension is very slow
            size = 1 if name == "patch" else len(dim)
            d.createDimension(name, size)
        for name, v in s.variables.items():
            o = d.createVariable(name, v.dtype, v.dimensions, zlib=True, complevel=1,
                                 fill_value=getattr(v, "_FillValue", None))
            o.setncatts({k: v.getncattr(k) for k in v.ncattrs() if k != "_FillValue"})
            x = v[:]
            if "patch" in v.dimensions:
                ax = v.dimensions.index("patch")
                if name == "patchfrac":
                    x = np.ones([1 if i == ax else x.shape[i] for i in range(x.ndim)])
                elif np.issubdtype(v.dtype, np.integer):   # e.g. iveg: keep the largest patch
                    x = np.take(x, [int(np.argmax(w))], axis=ax)
                else:
                    shape = [1] * x.ndim
                    shape[ax] = n
                    x = (np.ma.filled(x.astype("f8"), np.nan) * w.reshape(shape)).sum(axis=ax, keepdims=True)
            o[:] = x
    print(f"{site}: {n} patch(es) -> site average written to {dst}")
