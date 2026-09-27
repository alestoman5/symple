"""Entry point for the frozen (PyInstaller) build."""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()   # must run first: the engine is a child process
    from symple.app import main
    sys.exit(main())
