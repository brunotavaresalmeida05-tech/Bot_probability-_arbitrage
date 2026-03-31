"""
setup_dashboard.py
Installs dependencies and creates dashboard_v2/ folder structure.
Run once before starting flask_dashboard.py
"""
import os
import sys
import subprocess
import shutil


def install(pkg):
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg])


def ensure_dirs():
    dirs = [
        'data',
        'dashboard_v2',
        'dashboard_v2/css',
        'dashboard_v2/js',
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"  [ok] {d}/")


def copy_existing():
    """Copy existing dashboard files into dashboard_v2/ if present."""
    copies = [
        ('dashboard/index.html',  'dashboard_v2/index.html'),
        ('dashboard/css/main.css', 'dashboard_v2/css/main.css'),
        ('dashboard/js/app.js',    'dashboard_v2/js/app.js'),
    ]
    for src, dst in copies:
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
            print(f"  [copied] {src} → {dst}")


def main():
    print("=" * 50)
    print("  Trading Bot V6 - Dashboard Setup")
    print("=" * 50)

    print("\n[1/3] Installing Python dependencies...")
    for pkg in ('flask', 'flask-sock'):
        try:
            install(pkg)
            print(f"  [ok] {pkg}")
        except Exception as e:
            print(f"  [WARN] Could not install {pkg}: {e}")

    print("\n[2/3] Creating folder structure...")
    ensure_dirs()

    print("\n[3/3] Copying existing dashboard files...")
    copy_existing()

    print("\n[done] Setup complete!")
    print("  Start bot:       python run_live.py")
    print("  Start dashboard: python flask_dashboard.py")
    print("  Open browser:    http://localhost:5000")


if __name__ == '__main__':
    main()
