#!/usr/bin/env python
#
# Copyright (C) Citrix Systems Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation; version 2.1 only.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
#
# BTRFSSR: Based on local-file storage repository, mounts btrfs partition

import FileSR
import lvutil
import nfs
import util
import scsiutil
import SR
import SRCommand
import VDI

import os
import tempfile
import errno
import xs_errors
import vhdutil
from lock import Lock
import cleanup

CAPABILITIES = ["SR_PROBE", "SR_UPDATE", "SR_SUPPORTS_LOCAL_CACHING",
                "VDI_CREATE", "VDI_DELETE", "VDI_ATTACH", "VDI_DETACH",
                "VDI_UPDATE", "VDI_CLONE", "VDI_SNAPSHOT", "VDI_RESIZE",
                "VDI_RESET_ON_BOOT/2", "ATOMIC_PAUSE"]

CONFIGURATION = [['device', 'local device path (required) (e.g. /dev/sda3)']]

DRIVER_INFO = {
    'name': 'Local BTRFS',
    'description': 'SR plugin which represents disks as raw files stored on a'
                   'local BTRFS filesystem',
    'vendor': 'Citrix Systems Inc',
    'copyright': '(C) 2014 Citrix Systems Inc',
    'driver_version': '1.0',
    'required_api_version': '1.0',
    'capabilities': CAPABILITIES,
    'configuration': CONFIGURATION
}

BTRFS_PREFIX = 'XSLocalEXT-'


class BTRFSSR(FileSR.FileSR):

    """BTRFS Local file storage repository"""
    def handles(srtype):
        return srtype == 'btrfs'
    handles = staticmethod(handles)

    def load(self, sr_uuid):
        self.ops_exclusive = FileSR.OPS_EXCLUSIVE
        self.lock = Lock(vhdutil.LOCK_TYPE_SR, self.uuid)
        self.sr_vditype = vhdutil.VDI_TYPE_RAW
        if 'device' not in self.dconf or not self.dconf['device']:
            raise xs_errors.XenError('ConfigDeviceMissing')

        self.root = self.dconf['device']
        for dev in self.root.split(','):
            if not self._isvalidpathstring(dev):
                raise xs_errors.XenError('ConfigDeviceInvalid',
                                         opterr='path is %s' % dev)
        self.path = os.path.join(SR.MOUNT_BASE, sr_uuid)
        self.vgname = BTRFS_PREFIX + sr_uuid
        self.remotepath = os.path.join("/dev", self.vgname, sr_uuid)
        self.attached = self._checkmount()

        if self.dconf.has_key('SRmaster') and self.dconf['SRmaster'] == 'true':
           self.isMaster = True
        else:
           self.isMaster = False

    def delete(self, sr_uuid):
        super(BTRFSSR, self).delete(sr_uuid)

        # Check PVs match VG
        try:
            for dev in self.root.split(','):
                cmd = ["pvs", dev]
                txt = util.pread2(cmd)
                if txt.find(self.vgname) == -1:
                    raise xs_errors.XenError('VolNotFound',
                                             opterr='volume is %s' % self.vgname)
        except util.CommandException as inst:
            raise xs_errors.XenError('PVSfailed',
                                     opterr='error is %d' % inst.code)

        # Remove LV, VG and pv
        try:
            cmd = ["lvremove", "-f", self.remotepath]
            util.pread2(cmd)

            cmd = ["vgremove", self.vgname]
            util.pread2(cmd)

            for dev in self.root.split(','):
                cmd = ["pvremove", dev]
                util.pread2(cmd)
        except util.CommandException as inst:
            raise xs_errors.XenError('LVMDelete',
                                     opterr='errno is %d' % inst.code)

    def addExport(self, path, host):
        with open("/etc/exports", "a") as exportsfile:
            exportsfile.write("%s %s(rw,sync,no_root_squash)\n" % (path, host))
        util.doexec(['exportfs', '-a'])
        # TODO: THIS IS A NOGO
        util.doexec(['service', 'iptables', 'stop'])
        util.doexec(['service', 'nfs', 'start'])

    def removeExport(self, path):
        with open("/etc/exports", "rb") as exportsfiler:
            content = [line for line in exportsfiler if path not in line]
            with open('/etc/exports', 'wb') as exportsfilew:
                exportsfilew.writelines(content)
        util.doexec(['exportfs', '-a'])
        # This is quite forcefull but helps to avoid srinuse...
        util.doexec(['service', 'nfs', 'stop'])
        util.doexec(['service', 'nfs', 'start'])

    def attach(self, sr_uuid):
        if not self._checkmount():
            # make a mountpoint:
            if not os.path.isdir(self.path):
                os.makedirs(self.path)

            if not self.isMaster:
                connected = False
                for masterip in util.get_masterips(self.session):
                    if not connected:
                       try:
                           util.SMlog("Mounting %s" % (masterip))
                           nfs.soft_mount(self.path, masterip, self.path,
                                          "tcp")
                           connected = True
                       except:
                           pass
                if not connected:
                    raise util.SMException("bla")
                return

            try:
                # Activate LV
                cmd = ['lvchange', '-ay', self.remotepath]
                util.pread2(cmd)
            except util.CommandException as inst:
                raise xs_errors.XenError('LVMMount',
                                         opterr='Unable to activate LV. Errno is %d' % inst.code)

            """" There is BTRFSCK - but that's not quite ready yet. Rely on
            self healing capabilities for now.
            try:
                util.pread(["fsck", "-a", self.remotepath])
            except util.CommandException, inst:
                if inst.code == 1:
                    util.SMlog(
                        "FSCK detected and corrected FS errors. Not fatal.")
                else:
                    raise xs_errors.XenError('LVMMount',
                                             opterr='FSCK failed on %s. Errno is %d' % (self.remotepath, inst.code))
            """

            try:
                util.pread(["mount", self.remotepath, self.path])
            except util.CommandException as inst:
                raise xs_errors.XenError('LVMMount',
                                         opterr='Failed to mount FS. Errno is %d' % inst.code)

            self.addExport(self.path, "0.0.0.0/0.0.0.0")

        self.attached = True

        # Update SCSIid string
        scsiutil.add_serial_record(self.session, self.sr_ref,
                                   scsiutil.devlist_to_serialstring(self.root.split(',')))

        # Set the block scheduler
        for dev in self.root.split(','):
            self.block_setscheduler(dev)

    def detach(self, sr_uuid):
        if self.isMaster:
           self.removeExport(self.path)
        super(BTRFSSR, self).detach(sr_uuid)
        if not self.isMaster:
           return
        try:
            # deactivate SR
            cmd = ["lvchange", "-an", self.remotepath]
            util.pread2(cmd)
        except util.CommandException as inst:
            raise xs_errors.XenError('LVMUnMount',
                                     opterr='lvm -an failed errno is %d' % inst.code)

    def probe(self):
        return lvutil.srlist_toxml(lvutil.scan_srlist(BTRFS_PREFIX, self.root),
                                   BTRFS_PREFIX)

    def create(self, sr_uuid, size):
        if self._checkmount():
            raise xs_errors.XenError('SRExists')

        # Check none of the devices already in use by other PBDs
        if util.test_hostPBD_devs(self.session, sr_uuid, self.root):
            raise xs_errors.XenError('SRInUse')

        # Check serial number entry in SR records
        for dev in self.root.split(','):
            if util.test_scsiserial(self.session, dev):
                raise xs_errors.XenError('SRInUse')

        if not lvutil._checkVG(self.vgname):
            lvutil.createVG(self.root, self.vgname)

        if lvutil._checkLV(self.remotepath):
            raise xs_errors.XenError('SRExists')

        try:
            numdevs = len(self.root.split(','))
            cmd = ["lvcreate", "-n", sr_uuid]
            if numdevs > 1:
                lowest = -1
                for dev in self.root.split(','):
                    stats = lvutil._getPVstats(dev)
                    if lowest < 0 or stats['freespace'] < lowest:
                        lowest = stats['freespace']
                size_mb = (lowest / (1024 * 1024)) * numdevs

                # Add stripe parameter to command
                cmd += ["-i", str(numdevs), "-I", "2048"]
            else:
                stats = lvutil._getVGstats(self.vgname)
                size_mb = stats['freespace'] / (1024 * 1024)
            assert(size_mb > 0)
            cmd += ["-L", str(size_mb), self.vgname]
            text = util.pread(cmd)

            cmd = ["lvchange", "-ay", self.remotepath]
            text = util.pread(cmd)
        except util.CommandException as inst:
            raise xs_errors.XenError('LVMCreate',
                                     opterr='lv operation, error %d' % inst.code)
        except AssertionError:
            raise xs_errors.XenError('SRNoSpace',
                                     opterr='Insufficient space in VG %s' % self.vgname)

        try:
            util.pread2(["mkfs.btrfs", self.remotepath])
        except util.CommandException as inst:
            raise xs_errors.XenError('LVMFilesystem',
                                     opterr='mkfs failed error %d' % inst.code)

        # Update serial number string
        scsiutil.add_serial_record(self.session, self.sr_ref,
                                   scsiutil.devlist_to_serialstring(self.root.split(',')))

    def vdi(self, uuid, loadLocked=False):
        if not loadLocked:
            return BTRFSFileVDI(self, uuid)
        return BTRFSFileVDI(self, uuid)


class BTRFSFileVDI(FileSR.FileVDI):

    def attach(self, sr_uuid, vdi_uuid):
        if not hasattr(self, 'xenstore_data'):
            self.xenstore_data = {}

        self.xenstore_data["storage-type"] = "btrfs"

        return super(BTRFSFileVDI, self).attach(sr_uuid, vdi_uuid)

    def load(self, vdi_uuid):
        self.vdi_type = vhdutil.VDI_TYPE_RAW
        self.force_phy = False
        return super(BTRFSFileVDI, self).load(vdi_uuid)

    def clone(self, sr_uuid, vdi_uuid):
        src = self.path
        if not self._checkpath(src):
            raise xs_errors.XenError('VDIUnavailable',
                                     opterr='VDI %s unavailable %s'
                                            % (self.uuid, src))
        dstuuid = util.gen_uuid()
        dst = os.path.join(self.sr.path, "%s.%s" % (dstuuid, self.PARAM_RAW))
        util.SMlog("Creating clone of %s at %s" % (src, dst))
        util.doexec(['cp', '--reflink=always', src, dst])
        vdi = VDI.VDI(self.sr, dstuuid)
        vdi.read_only = False
        vdi.location = dstuuid
        vdi.size = self.size
        vdi.utilisation = self.utilisation
        vdi.sm_config = {}
        vdi_ref = vdi._db_introduce()
        self.session.xenapi.VDI.set_managed(vdi_ref, True)
        return vdi.get_params()

    def snapshot(self, sr_uuid, vdi_uuid):
        return self.clone(sr_uuid, vdi_uuid)

if __name__ == '__main__':
    SRCommand.run(BTRFSSR, DRIVER_INFO)
else:
    SR.registerSR(BTRFSSR)
