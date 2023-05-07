#!/usr/bin/env python3

from __future__ import annotations


class Sequence:
    """Command Sequences.

    Command sequences are series of commands that are executed serially.
    """

    def __init__(self, commands: list[str], repeat: bool = False):
        self._commands = commands
        self._repeat = repeat

    @property
    def commands(self) -> list[str]:
        return self._commands
