"""CLI 명령 구현."""

from commit_agent.cli.commands.generate import generate
from commit_agent.cli.commands.init import init
from commit_agent.cli.commands.install import install
from commit_agent.cli.commands.uninstall import uninstall

__all__ = ["generate", "init", "install", "uninstall"]
