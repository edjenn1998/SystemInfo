"""GUI, headless CLI and disposable-fixture self-test entry point."""
import sys


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if '--version' in args:
        from system_info.version import VERSION
        print(f'System Info {VERSION}')
        return 0
    if '--cli' in args:
        args.remove('--cli')
        from system_info.main import main as cli
        return cli(args)
    if '--self-test' in args:
        from system_info.selftest import run
        return run(args)
    from system_info.gui import main as gui
    return gui()


if __name__ == '__main__':
    raise SystemExit(main())
