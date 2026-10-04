#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BC_SCRIPT = os.path.join(ROOT, "tools", "boundary_check.py")

class TestBoundaryCheck(unittest.TestCase):
    def test_exit3_on_boundary_defect(self):
        cmd = [sys.executable, BC_SCRIPT, "--defect-report", "红队报告: docstring 中写死数字与行号 L228 腐烂"]
        res = subprocess.run(cmd, capture_output=True, encoding="utf-8")
        self.assertEqual(res.returncode, 3)
        self.assertIn("[BOUNDARY CHECK]", res.stdout)
        self.assertIn("B7", res.stdout)

    def test_exit4_on_consecutive_rounds(self):
        cmd = [sys.executable, BC_SCRIPT]
        res = subprocess.run(cmd, capture_output=True, encoding="utf-8")
        self.assertEqual(res.returncode, 4)
        self.assertIn("exit 4", res.stdout)

if __name__ == "__main__":
    unittest.main()
