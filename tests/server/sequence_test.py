#!/usr/bin/env python3

import unittest

from lifxdev.server import logs

# from lifxdev.server import sequence


class SequenceTest(unittest.TestCase):
    def test_sequence(self):
        pass


if __name__ == "__main__":
    logs.setup()
    unittest.main()
