#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo "1. Testing Python ticket-api (pytest)..."
echo "========================================"
python -m pytest tests -v

if [ -f "frontend/package.json" ]; then
    echo ""
    echo "========================================"
    echo "2. Testing Frontend (Vitest & tsc)..."
    echo "========================================"
    (
        cd frontend
        npm test -- --run
        npm run build
    )
fi

echo ""
echo "========================================"
echo "VERIFICATION SUCCESS: All tests passed!"
echo "========================================"
