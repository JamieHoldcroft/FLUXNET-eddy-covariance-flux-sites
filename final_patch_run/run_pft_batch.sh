#!/bin/bash
# Make patched met files from one PFT CSV and submit a CABLE run for them (on Gadi).
#
#   bash run_pft_batch.sh NAME CSV
#   e.g. bash run_pft_batch.sh jules  patchfracs_jules.csv
#        bash run_pft_batch.sh anna   patchfracs_anna.csv
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
cp cable_runs/cable_template.nml cable_runs/run_sites.pbs cable_runs_$NAME/
cd cable_runs_$NAME
# Multi-patch runs are slower, so ask for 3 hours instead of 1.
qsub -v MET_DIR=$BASE/met_cable_$NAME -l walltime=03:00:00 run_sites.pbs
echo "Submitted. Check with: qstat -u $USER"
