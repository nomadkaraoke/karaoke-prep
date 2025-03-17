import asyncio
from typing import Dict, Any

from karaoke_prep.cli.parser import parse_args
from karaoke_prep.cli.commands import execute_command


def main() -> None:
    """
    Main entry point for the CLI.
    """
    args = parse_args()
    asyncio.run(execute_command(args))


if __name__ == "__main__":
    main()
