import sys, os
# Ensure project root (containing 'backend') is on sys.path when tests executed from arbitrary CWD
root = os.path.abspath(os.path.dirname(__file__) + '/..')
if root not in sys.path:
    sys.path.insert(0, root)
