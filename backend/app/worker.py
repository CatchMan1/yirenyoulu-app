"""One durable planning worker; graceful shutdown between bounded jobs."""

import argparse
import signal
import threading

from sqlalchemy.orm import sessionmaker

from .db import make_engine
from .planning import run_once
from .settings import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    engine = make_engine(settings)
    sessions = sessionmaker(engine, expire_on_commit=False)
    stop = threading.Event()

    def shutdown(signum, frame):
        stop.set()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        while not stop.is_set():
            worked = run_once(settings, sessions)
            if args.once:
                break
            if not worked:
                stop.wait(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
