"""Entry point for the local WiZ desktop controller."""
import argparse
import logging
from logging.handlers import RotatingFileHandler

from wiz_controller.storage import Storage


def main():
    parser = argparse.ArgumentParser(description="WiZ Controller · Gaming & Streaming")
    parser.add_argument("--smoke-test", action="store_true", help="Open and close the UI without contacting bulbs")
    args = parser.parse_args()
    storage = Storage()
    storage.directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[RotatingFileHandler(storage.directory / "controller.log", maxBytes=500_000,
                                      backupCount=2, encoding="utf-8")],
    )
    from wiz_controller.ui import WizController
    app = WizController(storage, network_enabled=not args.smoke_test)
    if args.smoke_test:
        app.after(1200, app.close_app)
    app.mainloop()
    if app.runtime is not None:
        app.runtime.thread.join(timeout=2)


if __name__ == "__main__":
    main()
