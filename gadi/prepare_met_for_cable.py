#!/usr/bin/env python3
"""Make CABLE-ready copies of the FLUXNET2015 *_Met.nc site files.

The originals are never modified. For each input file this writes a copy to
OUT_DIR and then:
  1. adds the site parameters CABLE looks for by name:
       za   <- reference_height   (measurement height, m)
       hc   <- canopy_height      (m)
       iveg <- CABLE PFT from the site's IGBP class (see IGBP_TO_IVEG / SITE_IVEG)
  2. adds LAI (time, y, x) from LAI_MODIS (default) or LAI_BOM, clipped at 0
  3. CO2air: replaces it with NOAA Mauna Loa annual-mean CO2 (default, --co2 global), or
     only fills the -9999 gaps with it (--co2 fill). CABLE has no missing-value
     handling, so a -9999 left in CO2air is used as -9999 ppm.
  4. repairs isolated spikes that would break the model: Psurf more than 10 kPa
     away from its 1-day running median, Qair < 0 or > 1.5 x saturation,
     LWdown < 100 W/m2. Bad points are linearly interpolated.
  5. checks that no -9999 remains in any variable CABLE reads.

  0. (optional, --periods site_periods.csv) cuts each file to whole years
     start_year..end_year, and skips sites whose keep column is "no".

Usage:
    python3 prepare_met_for_cable.py IN_DIR OUT_DIR --co2-file co2_annmean_mlo.txt [--periods site_periods.csv] [--lai MODIS|BOM] [--co2 global|fill]
Writes OUT_DIR/prep_report.csv with what was changed in each file.
"""
import argparse
import csv
import glob
import os
import shutil

import netCDF4
import numpy as np

FILL = -9999.0

# CABLE PFTs (src/offline/pft_params.nml): 1 ENF, 2 EBF, 3 DNF, 4 DBF, 5 shrub,
# 6 C3 grass, 7 C4 grass, 8 tundra, 9 C3 crop, 10 C4 crop, 11 wetland
IGBP_TO_IVEG = {
    "ENF": 1, "EBF": 2, "DNF": 3, "DBF": 4, "MF": 4,
    "CSH": 5, "OSH": 5, "WSA": 2, "SAV": 2,
    "GRA": 6,  # C3; tropical grasslands are switched to C4 below
    "CRO": 9, "WET": 11,
}
C4_GRASS_NORTH_OF_LAT = -25.0  # GRA sites north of this get iveg 7 (C4 grass)
# Per-site overrides go here, e.g. {"AU-APL": 11}. Empty by default.
SITE_IVEG = {"AU-APL": 11}  # alpine peatland: file says EBF but canopy is 0.3 m

# Annual mean CO2 (ppm) from NOAA Mauna Loa, read from the file given with --co2-file:
# https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_annmean_mlo.txt
GLOBAL_CO2 = {}


def load_co2(path):
    """Parse NOAA co2_annmean_mlo.txt (lines: year mean unc; '#' comments)."""
    out = {}
    with open(path) as f:
        for line in f:
            parts = line.split()
            if not parts or line.startswith("#"):
                continue
            out[int(parts[0])] = float(parts[1])
    return out

CABLE_VARS = ["SWdown", "LWdown", "Tair", "Qair", "Psurf", "Precip", "Wind", "CO2air"]


def interp_bad(x, bad):
    """Linearly interpolate x over the points flagged in bad."""
    if not bad.any():
        return x, 0
    idx = np.arange(x.size)
    x = x.copy()
    x[bad] = np.interp(idx[bad], idx[~bad], x[~bad])
    return x, int(bad.sum())


def running_median(x, n):
    pad = n // 2
    xp = np.pad(x, pad, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(xp, n)
    return np.median(windows, axis=1)[: x.size]


def igbp_class(ds):
    raw = ds["IGBP_veg_short"][:]
    return b"".join(raw.tolist()).decode("latin1").strip("\x00 ")


def load_periods(path):
    """site_periods.csv -> {base site: [(name, start_year, end_year, keep, lai), ...]}

    A site can have several rows (segments). Extra segments are named <site>_1, <site>_2, ...
    e.g. AU-Cow (2010-2015), AU-Cow_1 (2017-2021). Each segment becomes its own met file,
    read from the base site's file (AU-Cow). Rows with keep=no need no years.
    The optional lai column (MODIS or BOM) overrides --lai for that row."""
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            name = (r.get("site") or "").strip()
            if not name:
                continue
            keep = (r.get("keep") or "yes").strip().lower()
            lai = (r.get("lai") or "").strip().upper() or None
            if keep == "no":
                y0 = y1 = None
            else:
                y0, y1 = int(r["start_year"]), int(r["end_year"])
            out.setdefault(name.split("_")[0], []).append((name, y0, y1, keep, lai))
    return out


def trim_copy(src, dst, y0, y1):
    """Write src to dst keeping only 1 Jan y0 .. 31 Dec y1, with time re-based to the new start."""
    with netCDF4.Dataset(src) as a, netCDF4.Dataset(dst, "w", format=a.data_model) as b:
        t = a["time"]
        dates = netCDF4.num2date(t[:], t.units, getattr(t, "calendar", "standard"),
                                 only_use_cftime_datetimes=False)
        years = np.array([d.year for d in dates])
        keep = np.where((years >= y0) & (years <= y1))[0]
        if keep.size == 0:
            raise SystemExit(f"{src}: no data in {y0}-{y1}")
        i0, i1 = keep[0], keep[-1] + 1
        b.setncatts({k: a.getncattr(k) for k in a.ncattrs()})
        b.setncattr("cable_prep_trim", f"kept {y0}-{y1} of original {years[0]}-{years[-1]}")
        for name, dim in a.dimensions.items():
            b.createDimension(name, None if dim.isunlimited() else len(dim))
        new_units = f"seconds since {y0}-01-01 00:00:00"
        for name, v in a.variables.items():
            fill = v.getncattr("_FillValue") if "_FillValue" in v.ncattrs() else None
            w = b.createVariable(name, v.dtype, v.dimensions, fill_value=fill)
            w.setncatts({k: v.getncattr(k) for k in v.ncattrs() if k != "_FillValue"})
            v.set_auto_maskandscale(False)
            w.set_auto_maskandscale(False)
            if name == "time":
                w[:] = netCDF4.date2num(dates[i0:i1], new_units, getattr(t, "calendar", "standard"))
                w.units = new_units
            elif "time" in v.dimensions:
                ax = v.dimensions.index("time")
                sl = [slice(None)] * v.ndim
                sl[ax] = slice(i0, i1)
                w[:] = v[tuple(sl)]
            else:
                w[:] = v[:]


def prepare(src, dst, lai_source, co2_mode, period=None):
    if period:
        trim_copy(src, dst, period[0], period[1])
    else:
        shutil.copy2(src, dst)
    rep = {"file": os.path.basename(src)}
    with netCDF4.Dataset(dst, "a") as ds:
        ds.set_auto_mask(False)
        site = ds.getncattr("site_code")
        lat = float(ds["latitude"][:].ravel()[0])
        igbp = igbp_class(ds)
        iveg = IGBP_TO_IVEG[igbp]
        if igbp == "GRA" and lat > C4_GRASS_NORTH_OF_LAT:
            iveg = 7
        iveg = SITE_IVEG.get(site, iveg)
        rep.update(site=site, igbp=igbp, iveg=iveg)

        step = float(ds["time"][1] - ds["time"][0])
        steps_per_day = int(round(86400 / step))

        # 1. site parameters
        for name, src_name, long_name in [
            ("za", "reference_height", "Reference height (from reference_height)"),
            ("hc", "canopy_height", "Vegetation height (from canopy_height)"),
        ]:
            v = ds.createVariable(name, "f4", ("y", "x"))
            v[:] = ds[src_name][:]
            v.units = "m"
            v.long_name = long_name
        v = ds.createVariable("iveg", "f4", ("y", "x"))
        v[:] = iveg
        v.units = "-"
        v.long_name = f"CABLE vegetation type (mapped from IGBP {igbp})"
        rep.update(za=float(ds["za"][:].ravel()[0]), hc=float(ds["hc"][:].ravel()[0]))

        # 2. LAI
        lai = ds[f"LAI_{lai_source}"][:].astype("f8")
        lai_shape = lai.shape
        lai = lai.ravel()
        lai, n_lai_gap = interp_bad(lai, lai == FILL)
        n_lai_neg = int((lai < 0).sum())
        lai = np.clip(lai, 0.0, None)
        v = ds.createVariable("LAI", "f4", ("time", "y", "x"))
        v[:] = lai.reshape(lai_shape)
        v.units = "-"
        v.long_name = f"Leaf area index (from LAI_{lai_source})"
        rep.update(lai_source=lai_source, lai_mean=round(float(lai.mean()), 2),
                   lai_gaps_filled=n_lai_gap, lai_neg_clipped=n_lai_neg)

        # 3. CO2
        dates = netCDF4.num2date(ds["time"][:], ds["time"].units,
                                 only_use_cftime_datetimes=False)
        years = np.array([d.year for d in dates])
        missing_years = sorted(set(years) - set(GLOBAL_CO2))
        if missing_years:
            raise SystemExit(f"{site}: no NOAA CO2 value for {missing_years}; download the latest file")
        global_co2 = np.array([GLOBAL_CO2[y] for y in years])
        co2 = ds["CO2air"][:].astype("f8").ravel()
        n_co2_missing = int((co2 == FILL).sum())
        if co2_mode == "global":
            tower = ds.createVariable("CO2air_tower", "f4", ds["CO2air"].dimensions,
                                      fill_value=FILL)
            tower[:] = ds["CO2air"][:]
            tower.units = "ppm"
            tower.long_name = "Original tower CO2 (not read by CABLE)"
            new = global_co2
        else:
            new = np.where(co2 == FILL, global_co2, co2)
        ds["CO2air"][:] = new.reshape(ds["CO2air"].shape)
        ds["CO2air"].setncattr("cable_prep", f"mode={co2_mode}; annual global-mean CO2 used "
                               + ("for all steps" if co2_mode == "global" else "for gaps"))
        rep.update(co2_mode=co2_mode, co2_missing_steps=n_co2_missing,
                   co2_tower_mean=round(float(co2[co2 != FILL].mean()), 1) if (co2 != FILL).any() else "")

        # 4. spikes
        ps = ds["Psurf"][:].astype("f8").ravel()
        med = running_median(ps, steps_per_day)
        ps_new, n_ps = interp_bad(ps, np.abs(ps - med) > 10000.0)
        ds["Psurf"][:] = ps_new.reshape(ds["Psurf"].shape)

        t = ds["Tair"][:].astype("f8").ravel()
        q = ds["Qair"][:].astype("f8").ravel()
        es = 611.2 * np.exp(17.67 * (t - 273.15) / (t - 29.65))
        qsat = 0.622 * es / (ps_new - 0.378 * es)
        q_new, n_q = interp_bad(q, (q < 0) | (q > 1.5 * qsat))
        ds["Qair"][:] = q_new.reshape(ds["Qair"].shape)

        lw = ds["LWdown"][:].astype("f8").ravel()
        lw_new, n_lw = interp_bad(lw, lw < 100.0)
        ds["LWdown"][:] = lw_new.reshape(ds["LWdown"].shape)
        rep.update(psurf_fixed=n_ps, qair_fixed=n_q, lwdown_fixed=n_lw)

        # 5. no fill values left in anything CABLE reads
        for name in CABLE_VARS + ["za", "hc", "iveg", "LAI"]:
            if (ds[name][:] == FILL).any():
                raise SystemExit(f"{site}: {name} still contains {FILL}")

        ds.setncattr("cable_prep", f"prepare_met_for_cable.py lai={lai_source} co2={co2_mode}")
    return rep


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("in_dir")
    p.add_argument("out_dir")
    p.add_argument("--lai", choices=["MODIS", "BOM"], default="MODIS")
    p.add_argument("--co2", choices=["global", "fill"], default="global")
    p.add_argument("--co2-file", required=True, help="NOAA co2_annmean_mlo.txt")
    p.add_argument("--periods", help="site_periods.csv (site,start_year,end_year,keep[,notes,lai]); one row per segment")
    a = p.parse_args()
    GLOBAL_CO2.update(load_co2(a.co2_file))
    os.makedirs(a.out_dir, exist_ok=True)
    rows = []
    periods = load_periods(a.periods) if a.periods else {}
    for src in sorted(glob.glob(os.path.join(a.in_dir, "*_Met.nc"))):
        name = os.path.basename(src)
        site = name.split("_")[0]
        if periods:
            if site not in periods:
                print(f"{site}: not in {a.periods}, skipped")
                continue
            jobs = []
            for seg, y0, y1, keep, lai in periods[site]:
                if keep == "no":
                    print(f"{seg}: keep = no, skipped")
                    continue
                out = f"{seg}_{y0}-{y1}_" + "_".join(name.split("_")[2:])
                jobs.append((seg, out, (y0, y1), lai or a.lai))
        else:
            jobs = [(site, name, None, a.lai)]
        for seg, out, period, lai in jobs:
            rep = prepare(src, os.path.join(a.out_dir, out), lai, a.co2, period)
            rep["site"] = seg
            rep["years"] = f"{period[0]}-{period[1]}" if period else "all"
            print(f"{seg}: IGBP {rep['igbp']} -> iveg {rep['iveg']}, LAI {lai}, "
                  f"CO2 gaps {rep['co2_missing_steps']}, spikes fixed "
                  f"Psurf {rep['psurf_fixed']} Qair {rep['qair_fixed']} LWdown {rep['lwdown_fixed']}")
            rows.append(rep)
    with open(os.path.join(a.out_dir, "prep_report.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
