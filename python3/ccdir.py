#!/usr/bin/env python3

# ccdir.py - checksum & compare directories
#
# Copyright (c) 2005-2020 Fpemud <fpemud@sina.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""
ccdir
===========

ccdir.Store is a squashfs image, which contains a directory structure
identical to the original directory.

File content is replaced by the MD5 checksum of the orignal file,
metadata such as the owner, mode, mtime and xattr can also be
stored in the image file in the most straight-forward manner.

We provide only getdir and cmpfile methods, which are building blocks
for a full-fledged file/directory compare algorithm, since it
varies on what should the compare result be.

@author: Fpemud
@license: GPLv3 License
@contact: fpemud@sina.com
"""

import os
import hashlib
import struct
import tempfile
import shutil
import subprocess
import fnmatch


__author__ = "fpemud@sina.com (Fpemud)"
__version__ = "0.0.1"


class InitError(Exception):
    pass


class ArgumentError(Exception):
    pass


class SaveError(Exception):
    pass


class Store:

    def __init__(self, store_file, mount_point=None):
        if mount_point is None:
            self.mount_point = tempfile.mkdtemp()
            self.btmpdir = True
        else:
            self.mount_point = mount_point
            self.btmpdir = False

        try:
            ret = _exec("/usr/bin/squashfuse \"%s\" \"%s\"" % (store_file, self.mount_point))
            if ret != 0:
                raise InitError("Mounting failed (%s)." % (ret[1]))
        except Exception:
            if self.btmpdir:
                os.rmdir(self.mount_point)
            raise

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def close(self):
        ret = _exec("/usr/bin/fusermount -u \"%s\"" % (self.mount_point))
        assert ret == 0

        if self.btmpdir:
            os.rmdir(self.mount_point)

    def getdir(self):
        return self.mount_point

    def cmpfile(self, srcfile, dstfile):
        if not os.path.lexists(srcfile):
            raise ArgumentError("Parameter \"srcfile\" does not exist.")
        if os.path.isdir(srcfile):
            raise ArgumentError("Parameter \"srcfile\" is a directory.")

        dstfile = os.path.abspath(dstfile)
        if not dstfile.startswith(self.mount_point + "/"):
            raise ArgumentError("Parameter \"dstfile\" must be in store file directory.")

        if not os.path.lexists(dstfile) or os.path.isdir(dstfile):
            return False

        if os.path.islink(srcfile):
            if not os.path.islink(dstfile):
                return False
            if os.readlink(srcfile) != os.readlink(dstfile):
                return False
        else:
            if os.path.islink(dstfile):
                return False
            if _get_file_size(dstfile) < _minsz:
                with open(dstfile, "rb") as f:
                    with open(srcfile, "rb") as f2:
                        if f.read() != f2.read():
                            return False
            else:
                with open(dstfile, "rb") as f:
                    sz, md5 = struct.unpack(_fmt, f.read())
                    if sz != _get_file_size(srcfile):
                        return False
                    if md5 != _get_file_md5(srcfile):
                        return False

        return True


def create_store(srcdir, store_file, including_patterns=["*"], excluding_patterns=[], tmpdir=None):
    if tmpdir is None:
        tmpdir = tempfile.mkdtemp()
        btmpdir = True
    else:
        btmpdir = False

    try:
        srcdir = os.path.abspath(srcdir)
        if srcdir == "/":
            plen = 1
        else:
            plen = len(srcdir) + 1

        for dirpath, dirnames, filenames in os.walk(srcdir):
            st = os.lstat(dirpath)
            dirpath = dirpath[plen:]

            # filter
            for d in dirnames:
                fullpath = os.path.join(dirpath, d)
                if _in_patterns(fullpath, excluding_patterns) or not _in_patterns(fullpath, including_patterns):
                    dirnames.remove(d)
            for f in filenames:
                fullpath = os.path.join(dirpath, f)
                if _in_patterns(fullpath, excluding_patterns) or not _in_patterns(fullpath, including_patterns):
                    filenames.remove(f)

            if dirpath == "":
                dirpath2 = tmpdir
            else:
                dirpath2 = os.path.join(tmpdir, dirpath)
                os.mkdir(dirpath2)
                os.chmod(dirpath2, st.st_mode)
                os.chown(dirpath2, st.st_uid, st.st_gid)

            for fn in filenames:
                fn = os.path.join(dirpath, fn)
                fullfn = os.path.join(srcdir, fn)
                st = os.lstat(fullfn)

                fn2 = os.path.join(tmpdir, fn)
                if os.path.islink(fullfn):
                    linkto = os.readlink(fullfn)
                    os.symlink(linkto, fn2)
                    os.lchown(fn2, st.st_uid, st.st_gid)
                else:
                    if st.st_size < _minsz:
                        shutil.copy2(fullfn, fn2)
                        os.chown(fn2, st.st_uid, st.st_gid)
                    else:
                        md5 = _get_file_md5(fullfn)
                        with open(fn2, "wb") as f:
                            f.write(struct.pack(_fmt, st.st_size, md5))
                            os.fchmod(f.fileno(), st.st_mode)
                            os.fchown(f.fileno(), st.st_uid, st.st_gid)
                        shutil.copystat(fullfn, fn2)

        ret = _mksquashfs(tmpdir, store_file)
        if ret != 0:
            raise SaveError("Creating store file failed (%s)." % (ret[1]))
    finally:
        if btmpdir:
            shutil.rmtree(tmpdir)


# content format for hashed file
_fmt = ">Q%ds" % (hashlib.md5(b'').digest_size)


# minimal size for hashed file
_minsz = struct.calcsize(_fmt)


def _remove_directory_content(dirpath):
    for dn in os.listdir(dirpath):
        dn = os.path.join(dirpath, dn)
        if os.path.isdir(dn) and not os.path.islink(dn):
            shutil.rmtree(dn)
        else:
            os.unlink(dn)


def _exec(cmd):
    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = proc.communicate()
    if proc.returncode == 0:
        return 0
    else:
        return (proc.returncode, err.decode("iso-8859-1"))


def _mksquashfs(srcdir, dstfile):
    # use minimum block size, disable any compression, to make squash/unsquash as fast as possible
    return _exec("/usr/bin/mksquashfs \"%s\" \"%s\" -b 4096 -noI -noD -noF -noX -noappend" % (srcdir, dstfile))


def _get_file_size(filepath):
    return os.lstat(filepath).st_size


def _get_file_md5(filepath):
    # some files are big, so we need to feed data in this way
    hash = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash.update(chunk)
    return hash.digest()


def _in_patterns(s, patterns):
    for pat in patterns:
        if fnmatch.fnmatch(s, pat):
            return True
    return False
