"""
Backward-compatibility shim for fetcher.py.
The actual implementation lives in the fetcher/ package.

Use `from fetcher import main` or `python -m fetcher` instead.
This file exists solely to keep `python fetcher.py --loop` working on the VPS.
"""
from fetcher import main, main_loop

if __name__ == "__main__":
    import sys
    if "--loop" in sys.argv:
        main_loop()
    else:
        main()
