#!/bin/bash

# Set test environment variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
export PYTHONPATH="$PROJECT_ROOT"
export PYTEST_ADDOPTS="--tb=short --override-ini=addopts= --import-mode=importlib"
export PYTHONUNBUFFERED=1
cd "$PROJECT_ROOT"  # Ensure we're in project root

# Set up results directory with forward slashes for Windows compatibility
BASE_DIR="tests/results"
mkdir -p "$BASE_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="$BASE_DIR/$TIMESTAMP"
export RESULTS_DIR

# Create results directory and subdirectories (using forward slashes)
for dir in "" "/logs" "/reports" "/assets"; do
    mkdir -p "${RESULTS_DIR}${dir}"
done

# Clean old test results (keep last 5 to prevent disk space issues)
# Use dir /B for Windows compatibility
ls -t "$BASE_DIR" | grep -v "archives" | tail -n +6 | while read -r dir; do
    rm -rf "$BASE_DIR/$dir"
done

# Add note about test directory
echo "Test run started at $(date)" > "$RESULTS_DIR/test_info.txt"

# Run ResourcePool tests first since other components depend on it
echo "Running ResourcePool tests..."
python -m pytest "$SCRIPT_DIR/core/test_resource_pool.py" \
    -v --html="$RESULTS_DIR/resource_pool_report.html" \
    2>&1 | tee "$RESULTS_DIR/resource_pool_output.log"

if [ $? -ne 0 ]; then
    echo "❌ ResourcePool tests failed - fix these before running other tests"
    exit 1
fi

# Run remaining core tests
echo "Running core tests in $RESULTS_DIR..."
python -m pytest \
    "$SCRIPT_DIR/core/test_resource_pool.py" \
    "$SCRIPT_DIR/core/test_"{alert_system,signal_processor,buffer_manager,speaker_isolation,whisper_transcriber,windows_manager}.py \
    "$SCRIPT_DIR/core/test_"{component_coordinator,monitoring,cleanup,state_machine}.py \
    "$SCRIPT_DIR/core/test_"{thread_safety,buffer_manager_atomic,signal_processor_memory}.py \
    "$SCRIPT_DIR/core/test_"{audio_capture,audio_capture_advanced,analysis,transcription_formatter,transcription_manager,storage_manager}.py \
    "$SCRIPT_DIR/core/test_"{config,alert_system_dynamic}.py \
    -n auto --timeout=120 --timeout-method=thread \
    --html="$RESULTS_DIR/core_tests_report.html" \
    2>&1 | grep -v "^DEBUG\|^INFO\|^WARNING\|^collecting\|^platform\|^rootdir\|^plugins\|^bringing\|^Test:\|^Result:\|^Duration:\|^Error:\|^Stack trace:\|^The above\|^During\|^E \|^_\|^===\|^worker\|^Traceback\|^  \|^[.F]\{1,\}$\|^Running\|^Docs:\|^-\|^Checking\|^Core Tests\|^=\{3,\}\|^$\|;Cwd=.*$" | grep -v "^tests.*::.*" | tee "$RESULTS_DIR/test_output.log" >/dev/null

# Check for deadlocks and timeouts
{
    grep -i "deadlock" "$RESULTS_DIR/test_output.log" > "$RESULTS_DIR/deadlock_check.log"
    grep -i "timeout.*items processed\|Thread errors occurred" "$RESULTS_DIR/test_output.log" >> "$RESULTS_DIR/deadlock_check.log"
} 2>/dev/null

# Generate summary
echo
echo
echo "Core Tests Summary"
echo "================="
echo
echo "Test Results:"
echo "------------"
results=$(grep ".*[0-9]* passed.* [0-9]* failed.* [0-9]* skipped" "$RESULTS_DIR/test_output.log" | tail -n1 | sed 's/^[[:space:]]*//')
[ ! -z "$results" ] && echo "$results" || echo "No test results found"

echo
echo "Failed Tests by Component:"
echo "-----------------------"
echo "ResourcePool Tests:"
grep "FAILED" "$RESULTS_DIR/resource_pool_output.log" 2>/dev/null | grep "^FAILED" | sed -E 's/FAILED (tests\/core\/[^:]+).*/❌ \1/' | sort -u || echo "✅ Passed"

echo
echo "Component Tests:"
grep "FAILED" "$RESULTS_DIR/test_output.log" | grep "^FAILED" | sed -E 's/FAILED (tests\/core\/[^:]+).*/❌ \1/' | sort -u || echo "None"

echo
echo "Memory Usage:"
echo "------------"
ps -o rss,command | grep "python.*pytest" | grep -v grep | awk '{print $1/1024 " MB"}' || echo "Unable to get memory usage"

echo
echo "Deadlock & Timeout Check:"
echo "----------------------"
if [ -s "$RESULTS_DIR/deadlock_check.log" ]; then
    echo "⚠️  Issues detected:"
    grep -v "^$" "$RESULTS_DIR/deadlock_check.log" | sed 's/^/  /'
else
    echo "✅ No issues detected"
fi

echo
echo "📊 Detailed reports saved to: $RESULTS_DIR"

# Check exit status
echo
if grep -q "FAILED" "$RESULTS_DIR"/*.log; then
    echo "❌ Tests failed - check HTML reports for details"
    exit 1
else 
    echo "✅ All tests passed successfully"
    exit 0
fi
