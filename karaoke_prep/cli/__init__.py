"""
Command-line interface module for the karaoke_prep package.

This module provides the command-line interface for the karaoke generator.
"""

import asyncio
from typing import Dict, Any

from karaoke_prep.cli.parser import parse_args, create_parser
from karaoke_prep.cli.commands import execute_command, get_command, Command, ProcessCommand, TestEmailTemplateCommand, BulkProcessCommand

__all__ = [
    "main",
    "parse_args",
    "create_parser",
    "execute_command",
    "get_command",
    "Command",
    "ProcessCommand",
    "TestEmailTemplateCommand",
    "BulkProcessCommand",
]


def main() -> None:
    """
    Main entry point for the CLI.
    """
    args = parse_args()
    asyncio.run(execute_command(args))


if __name__ == "__main__":
    main()
