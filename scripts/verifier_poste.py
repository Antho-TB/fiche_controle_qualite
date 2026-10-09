"""
[PREFLIGHT] Lanceur du controle des prerequis, hors executable.

La logique vit dans `src/preflight.py` pour etre embarquee dans l executable
PyInstaller. Ce fichier n existe que pour un lancement depuis les sources.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.preflight import main

if __name__ == "__main__":
    sys.exit(main())
