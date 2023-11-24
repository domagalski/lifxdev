#!/usr/bin/env python3

from __future__ import annotations

import pathlib


class Sequence:
    """Command Sequences.

    Command sequences are series of commands that are executed serially.

    Sequence syntax:
        - Any command that can be sent to the lifx server is valid sequence syntax.
        - Delays can be inserted: sleep <amount>
            - <amount> has units of seconds and can be an int or a float
        - Simple loops are supported where a sequence is repeated a predefined amount.
            - Basic loop: loop <amount>
                - <amount> is either a non-zero into or inf for infinite loops
            - Infinite loops are predicated as: loop inf
            -
        - Loop example:
            loop inf {
                command1
                command2
                ...
                loop 20 {
                    more commands
                    ...
                }
            }
        - Sequences are meant to be simple. For more complex interactions, scripts are better.
    """

    def __init__(self, commands: list[str], repeat: bool = False):
        self.check_syntax(commands)
        self._commands = commands
        self._repeat = repeat

    @staticmethod
    def check_syntax(commands: list[str]) -> None:
        pass

    @property
    def commands(self) -> list[str]:
        return self._commands

    @classmethod
    def from_file(cls, filename: pathlib.Path) -> Sequence:
        with filename.open() as f:
            lines = [ll.strip() for ll in f.readlines()]
        return cls(lines)
