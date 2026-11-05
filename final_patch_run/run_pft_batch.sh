#!/bin/bash
# Make patched met files from one PFT CSV and submit a CABLE run for them (on Gadi).
#
#   bash run_pft_batch.sh NAME CSV
#   e.g. bash run_pft_batch.sh barren     pfts_with_bare.csv
#        bash run_pft_batch.sh nonbarren  pfts_without_bare.csv
#
# Creates  met_cable_NAME/   (patched copies of met_cable/, with patch_report.csv)
#          cable_runs_NAME/  (run folder; results end up here)
# Never touches met_cable/ or cable_runs/. Stops if either new folder already exists.
set -e
NAME=$1; CSV=$2
BASE=/scratch/$PROJECT/$USER   # your Gadi working folder
cd $BASE
[ -n "$NAME" ] && [ -f "$CSV" ] || { echo "usage: bash run_pft_batch.sh NAME CSV"; exit 1; }
for d in met_cable_$NAME cable_runs_$NAME; do
  [ -e $d ] && { echo "$d already exists; delete it or pick another NAME"; exit 1; }
done

module unload python3 2>/dev/null || true
module load python3/3.11.7
python3 add_patches_from_sheet.py met_cable "$CSV" met_cable_$NAME
cp "$CSV" met_cable_$NAME/pfts_used.csv          # keep a copy of exactly what was used

mkdir cable_runs_$NAME
cp cable_runs/cable_template.nml cable_runs_$NAME/
sed -e "s#/cable_runs #/cable_runs_$NAME #" -e "s#/met_cable #/met_cable_$NAME #" \
    -e "s#walltime=01:00:00#walltime=03:00:00#" cable_runs/run_sites.pbs > cable_runs_$NAME/run_sites.pbs
echo; echo "Run script settings (should say cable_runs_$NAME, met_cable_$NAME, 03:00:00):"
grep -E "RUN_DIR=|MET_DIR=|walltime" cable_runs_$NAME/run_sites.pbs
grep -q "cable_runs_$NAME" cable_runs_$NAME/run_sites.pbs && grep -q "met_cable_$NAME" cable_runs_$NAME/run_sites.pbs \
  || { echo "sed did not update the paths; not submitting"; exit 1; }

cd cable_runs_$NAME
qsub run_sites.pbs
echo "Submitted. Check with: qstat -u $USER"
