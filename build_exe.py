import subprocess
import sys
import os

def build():
    print("Building standalone P7MViewer.exe using PyInstaller...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name=P7MViewer",
        "--icon=app_icon.ico",
        "--add-data=app_icon.png;.",
        "--collect-all=cryptography",
        "--collect-all=asn1crypto",
        "--collect-all=pyhanko_certvalidator",
        "--collect-all=oscrypto",
        "main.py"
    ]
    res = subprocess.run(cmd)
    if res.returncode == 0:
        exe_path = os.path.abspath("dist/P7MViewer/P7MViewer.exe")
        print(f"\nBuild completato con successo!\nCartella applicazione generata in: {os.path.abspath('dist/P7MViewer')}\nEseguibile: {exe_path}")
    else:
        print("\nErrore durante la compilazione PyInstaller.")
        sys.exit(res.returncode)

if __name__ == "__main__":
    build()

