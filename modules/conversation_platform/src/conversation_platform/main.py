import argparse

import uvicorn

from .api import create_app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run conversation agent platform API server.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8010, help="Bind port.")
    parser.add_argument("--reload", action="store_true", help="Enable auto reload.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
