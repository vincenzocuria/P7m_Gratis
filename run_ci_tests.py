"""Run the unit suite and abort with a traceback if a test stalls."""
import faulthandler
import os
import sys
import threading
import unittest

TIMEOUT_SECONDS = 180


def main():
    faulthandler.enable()
    timer = threading.Timer(TIMEOUT_SECONDS, _abort)
    timer.daemon = True
    timer.start()
    suite = unittest.defaultTestLoader.discover(os.path.dirname(os.path.abspath(__file__)) or ".")
    result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
    timer.cancel()
    return 0 if result.wasSuccessful() else 1


def _abort():
    sys.stderr.write("\nI test non sono terminati entro il tempo previsto.\n")
    sys.stderr.flush()
    faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
    os._exit(2)


if __name__ == "__main__":
    sys.exit(main())
