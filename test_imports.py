try:
    import tkinter
    print("✓ tkinter available")
except ImportError as e:
    print(f"✗ tkinter: {e}")

try:
    import sqlite3
    print("✓ sqlite3 available")
except ImportError as e:
    print(f"✗ sqlite3: {e}")

try:
    from reportlab.lib.pagesizes import letter
    print("✓ reportlab available")
except ImportError as e:
    print(f"✗ reportlab: {e}")
    print("\nInstalling reportlab...")
    import subprocess
    subprocess.run(["pip", "install", "reportlab"])
