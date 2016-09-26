#!/usr/bin/env python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import shutil
import unittest
curDir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(curDir, "../python3"))
import dirchecksum


class TestSave(unittest.TestCase):
    def setUp(self):
        self.srcdir = os.path.join(curDir, "example")
        self.storeFile = os.path.join(curDir, "store.dat")

    def runTest(self):
        with dirchecksum.Store(self.storeFile, "w") as f:
            f.save(self.srcdir)

    def tearDown(self):
        os.unlink(self.storeFile)


class TestSaveBig(unittest.TestCase):
    def setUp(self):
        self.srcdir = os.path.join(curDir, "example")
        self.storeFile = os.path.join(curDir, "store.dat")
        self.bigFile = self._createBigFile()

    def runTest(self):
        with dirchecksum.Store(self.storeFile, "w") as f:
            f.save(self.srcdir)

    def tearDown(self):
        os.unlink(self.bigFile)
        os.unlink(self.storeFile)

    def _createBigFile(self):
        return None


class TestCmpFile(unittest.TestCase):
    def setUp(self):
        self.srcdir = os.path.join(curDir, "example")
        self.storeFile = os.path.join(curDir, "store.dat")

    def runTest(self):
        with dirchecksum.Store(self.storeFile, "rw") as f:
            f.save(self.srcdir)
        with dirchecksum.Store(self.storeFile, "r") as f:
            self.assertTrue(f.cmpfile(self.srcdir, "a/a/short.txt"))
            self.assertTrue(f.cmpfile(self.srcdir, "a/a/long.txt"))

    def tearDown(self):
        os.unlink(self.storeFile)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(TestSave())
#    suite.addTest(TestSaveBig())
    suite.addTest(TestCmpFile())
    return suite


if __name__ == "__main__":
    unittest.main(defaultTest = 'suite')