#!/bin/sh
# Re-run every completed run's hidden tests against the *current* accrete engine
# (engine upgrades are not covered by the change pipeline; see docs/REVISIONS.md C1).
# usage: harness/compat_check.sh SET   (run from the accrete/ directory)
SET=${1:-dev}
RUNS=${ACCRETE_RUNS:-/tmp/claude-0/-home-user-Journeymandigital/d6243dbf-52d7-59df-a403-d35a058b8748/scratchpad/runs}
for d in challenges/$SET/*/; do
  id=$(basename "$d")
  app="$RUNS/$SET/$id/accrete/app"
  [ -d "$app" ] || continue
  echo "$id $(PYTHONPATH=harness python harness/run_acceptance.py "$app" "$d/test_$id.py" | tail -1)"
done
