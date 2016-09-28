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
        dirchecksum.create_store(self.srcdir, self.storeFile)

    def tearDown(self):
        if os.path.exists(self.storeFile):
            os.unlink(self.storeFile)


class TestCmpFile(unittest.TestCase):
    def setUp(self):
        self.srcdir = os.path.join(curDir, "example")
        self.storeFile = os.path.join(curDir, "store.dat")

    def runTest(self):
        dirchecksum.create_store(self.srcdir, self.storeFile)

        with dirchecksum.Store(self.storeFile) as f:
            srcfile = os.path.join(self.srcdir, "a/b/short.txt")
            dstfile = os.path.join(f.getdir(), "a/b/short.txt")
            self.assertTrue(f.cmpfile(srcfile, dstfile))

            srcfile = os.path.join(self.srcdir, "a/b/long.txt")
            dstfile = os.path.join(f.getdir(), "a/b/long.txt")
            self.assertTrue(f.cmpfile(srcfile, dstfile))

            srcfile = os.path.join(self.srcdir, "c/symlink1")
            dstfile = os.path.join(f.getdir(), "c/symlink1")
            self.assertTrue(f.cmpfile(srcfile, dstfile))

            srcfile = os.path.join(self.srcdir, "c/symlink2")
            dstfile = os.path.join(f.getdir(), "c/symlink2")
            self.assertTrue(f.cmpfile(srcfile, dstfile))

    def tearDown(self):
        if os.path.exists(self.storeFile):
            os.unlink(self.storeFile)


def suite():
    suite = unittest.TestSuite()
    #suite.addTest(TestSave())
    suite.addTest(TestCmpFile())
    return suite


if __name__ == "__main__":
    unittest.main(defaultTest = 'suite')