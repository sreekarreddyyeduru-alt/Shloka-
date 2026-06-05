"""SHLOKA — run.py"""
import sys, socket

# Check Python version
if sys.version_info < (3, 8):
    print("ERROR: Need Python 3.8+. You have:", sys.version)
    sys.exit(1)

# Check packages
missing = []
for mod, pkg in [("flask","flask"),("flask_sqlalchemy","flask-sqlalchemy"),
                  ("flask_login","flask-login"),("slugify","python-slugify")]:
    try: __import__(mod)
    except ImportError: missing.append(pkg)

if missing:
    print("\nERROR: Missing packages. Run this in Terminal:\n")
    print("  pip3 install " + " ".join(missing))
    print("\nThen run:  python3 run.py\n")
    sys.exit(1)

# Find free port
def free_port():
    for p in range(5000, 5020):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try: s.bind(("", p)); return p
            except OSError: continue
    return 5000

from app import create_app
application = create_app()

if __name__ == "__main__":
    port = free_port()
    print("\n" + "="*45)
    print("  SHLOKA — Ancient words. Timeless practice.")
    print("="*45)
    print(f"  Open:     http://localhost:{port}")
    print(f"  Creator:  admin@shloka.app / admin123")
    print(f"  Learner:  demo@shloka.app  / demo123")
    print("="*45)
    print("  CTRL+C to stop\n")
    application.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
