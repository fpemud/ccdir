#!/usr/bin/env python3

# dirchecksum.py - checksum and metadata store for a whole directory
#
# Copyright (c) 2005-2016 Fpemud <fpemud@sina.com>
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
dirchecksum

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

    """
    dirchecksum.Store creates an EXT4 image file, and establishes a
    directory structure identical to the original directory.

    File content is replaced by the MD5 checksum of the orignal file,
    metadata such as the owner, mode, mtime and xattr can also be
    stored in the image file in the most straight-forward manner.

    EXT4 has the fullest capabilities so we choose it as our file system.

    Unfortunately it must be used by root user since mount is a
    priviledged operation.
    What a great world it would be if mount can be used by non-root!

    We provide only getdir and cmpfile methods, which are building blocks
    for a full-fledged file/directory compare algorithm, since it
    varies on what should the result be.

    NOTE: There's a read-only implementation of ext4 for FUSE (https://github.com/gerard/ext4fuse),
    we may use it to eliminate the root user requirement when doing read
    operations in future.

    TODO: 1. dynamically enlarge store file when save
          2. shrink store file to the initial size when save
    """

    def __init__(self, store_file, mode, mount_point=None):
        self.fmt = ">Q%ds" % (hashlib.md5(b'').digest_size)
        self.minsz = struct.calcsize(self.fmt)

        if mount_point is None:
            self.mount_point = tempfile.mkdtemp()
            self.btmpdir = True
        else:
            self.mount_point = mount_point
            self.btmpdir = False

        self.mode = mode
        try:
            if self.mode == "r":
                ret = _exec("/bin/mount -t ext4 -o ro \"%s\" \"%s\"" % (store_file, self.mount_point))
            elif self.mode == "w":
                if not os.path.exists(store_file):
                    _create_store_file(store_file)
                ret = _exec("/bin/mount -t ext4 \"%s\" \"%s\"" % (store_file, self.mount_point))
            else:
                assert False
            if ret != 0:
                raise InitError("Mouting failed (%s)." % (ret[1]))
        except:
            if self.btmpdir:
                os.rmdir(self.mount_point)
            raise

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()

    def close(self):
        ret = _exec("/bin/umount \"%s\"" % (self.mount_point))
        assert ret == 0

        if self.btmpdir:
            os.rmdir(self.mount_point)

    def save(self, srcdir, including_patterns=None, excluding_patterns=None):
        if self.mode == "r":
            raise ArgumentError("Operation \"save\" is not allowed for a read-only store.")

        _remove_directory_content(self.mount_point)

        srcdir = os.path.realpath(srcdir)
        if srcdir == "/":
            plen = 1
        else:
            plen = len(srcdir) + 1

        for dirpath, dirnames, filenames in os.walk(srcdir):
            dirpath = dirpath[plen:]

            if excluding_patterns is not None:
                for d in dirnames:
                    if _in_patterns(os.path.join(dirpath, d), excluding_patterns):
                        dirnames.remove(d)
                for f in filenames:
                    if _in_patterns(os.path.join(dirpath, f), excluding_patterns):
                        filenames.remove(f)
            if including_patterns is not None:
                for d in dirnames:
                    if not _in_patterns(os.path.join(dirpath, d), including_patterns):
                        dirnames.remove(d)
                for f in filenames:
                    if not _in_patterns(os.path.join(dirpath, f), including_patterns):
                        filenames.remove(f)

            if dirpath == "":
                dirpath2 = self.mount_point
            else:
                dirpath2 = os.path.join(self.mount_point, dirpath)
                os.mkdir(dirpath2)

            for fn in filenames:
                fn = os.path.join(dirpath, fn)
                fullfn = os.path.join(srcdir, fn)
                st = os.lstat(fullfn)

                fn2 = os.path.join(self.mount_point, fn)
                if st.st_size < self.minsz:
                    shutil.copy2(fullfn, fn2)
                    os.chown(fn2, st.st_uid, st.st_gid)
                else:
                    md5 = _get_file_md5(fullfn)
                    with open(fn2, "wb") as f:
                        f.write(struct.pack(self.fmt, st.st_size, md5))
                        os.fchown(f.fileno(), st.st_uid, st.st_gid)
                    shutil.copymode(fullfn, fn2)
                    shutil.copystat(fullfn, fn2)

    def getdir(self):
        if self.mode == "w":
            raise ArgumentError("Operation \"getdir\" is not allowed for a write-only store.")

        return self.mount_point

    def cmpfile(self, srcfile, dstfile):
        if self.mode == "w":
            raise ArgumentError("Operation \"cmpfile\" is not allowed for a write-only store.")

        if not os.path.exists(srcfile):
            raise ArgumentError("Parameter \"srcfile\" does not exist.")
        if os.path.isdir(srcfile):
            raise ArgumentError("Parameter \"srcfile\" is a directory.")

        dstfile = os.path.realpath(dstfile)
        if not dstfile.startswith(self.mount_point + "/"):
            raise ArgumentError("Parameter \"dstfile\" must be in store file directory.")

        if not os.path.exists(dstfile) or os.path.isdir(dstfile):
            return False
        if _get_file_size(dstfile) < self.minsz:
            with open(dstfile, "rb") as f:
                with open(srcfile, "rb") as f2:
                    if f.read() != f2.read():
                        return False
        else:
            with open(dstfile, "rb") as f:
                sz, md5 = struct.unpack(self.fmt, f.read())
                if sz != _get_file_size(srcfile):
                    return False
                if md5 != _get_file_md5(srcfile):
                    return False
        return True


def _create_store_file(store_file):
    data = bytearray(1024)
    with open(store_file, "wb") as f:
        for i in range(0, 3000 * 1024):
            f.write(data)

#   ret = _exec("/sbin/mkfs.ext4 -O ^has_journal \"%s\"" % (store_file))
    ret = _exec("/sbin/mkfs.ext2 -b 1024 \"%s\"" % (store_file))
    if ret != 0:
        raise InitError("Failed to create store file.")


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
