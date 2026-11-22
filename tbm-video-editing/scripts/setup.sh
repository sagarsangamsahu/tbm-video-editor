#!/bin/bash
# Kept for older instructions: the real setup (Mac + Windows) is setup.py.
exec python3 "$(cd "$(dirname "$0")" && pwd)/setup.py"
