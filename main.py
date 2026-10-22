"""Entry point for the local WiZ desktop controller."""
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from wiz_controller.instance import SingleInstance
from wiz_controller.storage import Storage


def main():
    parser = argparse.ArgumentParser(description="WiZ Controller 2.1 · Desktop Gaming Edition")
    parser.add_argument("--smoke-test", action="store_true", help="Open and close the UI without contacting bulbs")
    parser.add_argument("--desktop-check", action="store_true", help="With --smoke-test, verify real tray/hotkeys and write smoke-result.json")
    parser.add_argument("--background", action="store_true", help="Hide once the tray icon is ready")
    parser.add_argument("--data-dir", type=Path, help="Explicit data directory for diagnostics/portable testing")
    parser.add_argument("--migrate-from", type=Path, help="Import missing config/scenes from an old data directory")
    args = parser.parse_args()
    if args.desktop_check and not args.smoke_test:
        parser.error("--desktop-check requiere --smoke-test")
    instance = SingleInstance()
    app = None
    status = 0
    smoke_result = {}
    try:
        if not args.smoke_test and not instance.acquire():
            return 0
        storage = Storage(args.data_dir)
        storage.directory.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            handlers=[RotatingFileHandler(storage.directory / "controller.log", maxBytes=500_000,
                                          backupCount=2, encoding="utf-8")],
        )
        if not args.smoke_test and (args.migrate_from is not None or args.data_dir is None):
            storage.migrate_legacy(args.migrate_from)
        from wiz_controller.ui import WizController
        app = WizController(storage, network_enabled=not args.smoke_test,
                            desktop_enabled=not args.smoke_test or args.desktop_check,
                            instance=instance, background=args.background)
        if args.smoke_test:
            def finish_check():
                nonlocal status
                if args.desktop_check:
                    from wiz_controller.paths import frozen
                    registered = len(app.desktop.hotkeys.registered) if app.desktop and app.desktop.hotkeys else 0
                    expected = len(app.config_data.hotkeys) if app.config_data.hotkeys_enabled else 0
                    tray_ok = bool(app.desktop and app.desktop.tray_ready)
                    smoke_result.update(frozen=frozen(), tray_ready=tray_ok,
                                        hotkeys_registered=registered, hotkeys_expected=expected)
                    status = 0 if (tray_ok or not app.config_data.tray_enabled) and registered == expected else 1
                app.close_app()
            app.schedule(2500 if args.desktop_check else 1200, finish_check)
        app.mainloop()
    except Exception as error:
        logging.exception("Application startup failed")
        import ctypes
        import sys
        if sys.platform == "win32":
            ctypes.windll.user32.MessageBoxW(None, f"No se pudo iniciar WiZ Controller:\n{error}", "WiZ Controller", 0x10)
        status = 1
    finally:
        if app is not None:
            if not app.closing:
                app.close_app()
            if app.desktop is not None and not app.desktop.wait():
                logging.error("Desktop supervisor did not stop in time")
                status = 1
            if args.desktop_check and app.desktop is not None:
                smoke_result["desktop_stopped"] = not app.desktop.thread.is_alive()
            if app.runtime is not None:
                app.runtime.thread.join(timeout=3)
                if app.runtime.thread.is_alive():
                    logging.error("Network worker did not stop in time")
                    status = 1
            if args.desktop_check:
                (app.storage.directory / "smoke-result.json").write_text(json.dumps(smoke_result, indent=2), encoding="utf-8")
        instance.close()
    return status


if __name__ == "__main__":
    raise SystemExit(main())
