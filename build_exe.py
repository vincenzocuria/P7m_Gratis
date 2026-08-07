import subprocess
import sys
import os

def build():
    print("Building standalone P7MViewer.exe using PyInstaller...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name=P7MViewer",
        "--icon=app_icon.ico",
        "--add-data=app_icon.png;.",
        "main.py"
    ]
    res = subprocess.run(cmd)
    if res.returncode == 0:
        exe_path = os.path.abspath("dist/P7MViewer.exe")
        print(f"\nBuild completato con successo!\nEseguibile generato in: {exe_path}")
    else:
        print("\nErrore durante la compilazione PyInstaller.")

if __name__ == "__main__":
    build()

