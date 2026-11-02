#!/usr/bin/env bash
# ==============================================================================
# Helper to manage macOS launchd background scheduler for AutoApply
# ==============================================================================

set -e

PLIST_NAME="com.vikas.autoapply.plist"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_PLIST="${SCRIPT_DIR}/${PLIST_NAME}"
TARGET_DIR="${HOME}/Library/LaunchAgents"
TARGET_PLIST="${TARGET_DIR}/${PLIST_NAME}"

action="${1:-install}"

case "$action" in
    install)
        mkdir -p "${TARGET_DIR}"
        # Unload existing if present
        launchctl unload "${TARGET_PLIST}" 2>/dev/null || true
        cp "${SOURCE_PLIST}" "${TARGET_PLIST}"
        launchctl load "${TARGET_PLIST}"
        echo "✓ AutoApply scheduler installed to macOS launchd!"
        echo "  - Scheduled for: Every day at 05:30 AM IST and 02:30 PM IST"
        echo "  - Sleep behavior: If Mac is asleep, it runs automatically upon waking up"
        echo "  - Script: ${SCRIPT_DIR}/run_morning.sh"
        echo "  - Logs: data/morning_run.log"
        ;;
    uninstall)
        if [ -f "${TARGET_PLIST}" ]; then
            launchctl unload "${TARGET_PLIST}" 2>/dev/null || true
            rm -f "${TARGET_PLIST}"
            echo "✓ AutoApply scheduler uninstalled from macOS launchd."
        else
            echo "No active scheduler plist found at ${TARGET_PLIST}."
        fi
        ;;
    status)
        echo "Checking launchd status for com.vikas.autoapply:"
        launchctl list | grep "com.vikas.autoapply" || echo "Not currently loaded in launchd."
        ;;
    test)
        echo "Triggering immediate test run of ${SCRIPT_DIR}/run_morning.sh..."
        "${SCRIPT_DIR}/run_morning.sh"
        ;;
    *)
        echo "Usage: $0 {install|uninstall|status|test}"
        exit 1
        ;;
esac
