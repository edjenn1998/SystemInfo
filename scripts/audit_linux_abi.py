#!/usr/bin/env python3
"""Compatibility entry point for the maintained payload audit."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.audit_bundle import audit as audit, main

if __name__ == '__main__': raise SystemExit(main())
