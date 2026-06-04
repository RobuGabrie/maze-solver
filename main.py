"""
main.py - Entry point for the CoppeliaSim Robot GUI.

Usage:
    python main.py
"""
import sys
from pathlib import Path

# Ensure project root is on the path so `core` and `gui` are importable
sys.path.insert(0, str(Path(__file__).parent))

from gui.app import App


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
