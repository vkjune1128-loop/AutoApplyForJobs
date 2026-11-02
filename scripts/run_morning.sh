#!/usr/bin/env bash
# ==============================================================================
# AutoApply Mac Automation Runner
# Runs locally on macOS, discovers jobs, generates HTML + PDFs, pushes to Git
# ==============================================================================

set -o pipefail

REPO_DIR="/Users/vikaskumar/Documents/Projects/AutoApplyForJobs"
LOG_FILE="${REPO_DIR}/data/morning_run.log"

cd "${REPO_DIR}"
mkdir -p data/generated_resumes

# Timestamp header
echo "" >> "${LOG_FILE}"
echo "========================================================" >> "${LOG_FILE}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting AutoApply Morning Run on Mac" >> "${LOG_FILE}"

# Export environment paths for macOS background daemon
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_FALLBACK_LIBRARY_PATH"

# Run the morning job discovery, tailoring, HTML digest, and git push
"${REPO_DIR}/.venv/bin/python" -m autoapply.cli morning-run --min-score 70 --max-jobs 10 >> "${LOG_FILE}" 2>&1
EXIT_CODE=$?

if [ ${EXIT_CODE} -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Morning Run finished successfully." >> "${LOG_FILE}"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Morning Run exited with code ${EXIT_CODE}. Check errors above." >> "${LOG_FILE}"
fi

exit ${EXIT_CODE}
