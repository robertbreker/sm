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
# DummySR: an example dummy SR for the SDK

import os, sys, time, syslog, errno, traceback, subprocess, exceptions
import xmlrpclib, XenAPI

def log(message):
    syslog.syslog(syslog.LOG_INFO, message)

class SR:
    def create(self, dbg, uri, configuration):
        return
    def destroy(self, dbg, uri):
        return
    def attach(self, dbg, uri):
        return "some sr"
    def detach(self, dbg, sr):
        return
    def ls(self, dbg, sr):
        return [ {
            "key": "unknown-volume",
            "name": "unknown-volume",
            "description": "",
            "read_write": True,
            "virtual_size": 1,
            "uri": ["file:\/\/\/secondary\/sr\/unknown-volume"]
        } ]

class Volume:
    def create(self, dbg, sr, name, description, size):
        u = urlparse.urlparse(sr)
        return {
            "key": "unknown-volume",
            "name": "unknown-volume",
            "description": "",
            "read_write": True,
            "virtual_size": 1,
            "uri": ["file:\/\/\/secondary\/sr\/unknown-volume"]
            }
    def destroy(self, dbg, sr, key):
        return
    def clone(self, dbg, sr, key):
        return {
            "key": "unknown-volume",
            "name": "unknown-volume",
            "description": "",
            "read_write": True,
            "virtual_size": 1,
            "uri": ["file:\/\/\/secondary\/sr\/unknown-volume"]
            }
    def snapshot(self, dbg, sr, key):
        return {
            "key": "unknown-volume",
            "name": "unknown-volume",
            "description": "",
            "read_write": True,
            "virtual_size": 1,
            "uri": ["file:\/\/\/secondary\/sr\/unknown-volume"]
            }

class Datapath:
    def attach(self, dbg, uri, domain):
        return {
            'domain_uuid': '0',
            'implementation': [ 'Blkback', "/dev/loop0" ],
        }
    def activate(self, dbg, uri, domain):
        return
    def deactivate(self, dbg, uri, domain):
        return
    def detach(self, dbg, uri, domain):
        return

# Everything beneath here is SMAPIv1 boilerplate:
CAPABILITIES = ["SR_PROBE","VDI_CREATE","VDI_DELETE","VDI_ATTACH","VDI_DETACH",
                "VDI_ACTIVATE","VDI_DEACTIVATE","VDI_CLONE","VDI_SNAPSHOT","VDI_RESIZE",
                "VDI_INTRODUCE"]

CONFIGURATION = [ ['uri', 'storage target (required) (e.g. iscsi://target)'] ]

DRIVER_INFO = {
    'name': 'dummy',
    'description': 'SR plugin which manages fake data',
    'vendor': 'Citrix Systems Inc',
    'copyright': '(C) 2015 Citrix Systems Inc',
    'driver_version': '1.0',
    'required_api_version': '1.1',
    'capabilities': CAPABILITIES,
    'configuration': CONFIGURATION
    }

if __name__ == '__main__':
    try:
        params, cmd = xmlrpclib.loads(sys.argv[1])

        if cmd == 'sr_get_driver_info':
            results = {}
            for key in [ 'name', 'description', 'vendor', 'copyright', \
                         'driver_version', 'required_api_version', 'capabilities' ]:
                results[key] = DRIVER_INFO[key]
            options = []
            for option in DRIVER_INFO['configuration']:
                options.append({ 'key': option[0], 'description': option[1] })
            results['configuration'] = options
            print xmlrpclib.dumps((results,), "", True)
            sys.exit(0)

        params = params[0]
        dconf = params['device_config']
        if params.has_key('sr_uuid'):
            sr_uuid = params['sr_uuid']
        if params.has_key('vdi_uuid'):
            vdi_uuid = params['vdi_uuid']
        if params.has_key('vdi_location'):
            vdi_location = params['vdi_location']

        dbg = "Dummy"
        session = XenAPI.xapi_local()
        session._session = params['session_ref']

        def db_introduce(v, uuid):
            sm_config = { }
            ty = "user"
            is_a_snapshot = False
            metadata_of_pool = "OpaqueRef:NULL"
            snapshot_time = "19700101T00:00:00Z"
            snapshot_of = "OpaqueRef:NULL"
            shareable = True
            sr_ref = session.xenapi.SR.get_by_uuid(sr_uuid)
            read_only = False
            managed = True
            session.xenapi.VDI.db_introduce(uuid, v['name'], v['description'], sr_ref, ty, shareable, read_only, {}, v['uri'][0], {}, sm_config, managed, str(v['virtual_size']), str(v['virtual_size']), metadata_of_pool, is_a_snapshot, xmlrpclib.DateTime(snapshot_time), snapshot_of)
        def db_forget(uuid):
            vdi = session.xenapi.VDI.get_by_uuid(uuid)
            session.xenapi.VDI.db_forget(vdi)
        def gen_uuid():
            return subprocess.Popen(["uuidgen", "-r"], stdout=subprocess.PIPE).communicate()[0].strip()
        nil = xmlrpclib.dumps((None,), "", True, allow_none=True)
        if cmd == 'sr_create':
            sr = SR().create(dbg, sr_uuid, dconf)
            print nil
        elif cmd == 'sr_delete':
            sr = SR().destroy(dbg, sr_uuid)
            db_forget(vdi_uuid)
            print nil
        elif cmd == 'sr_scan':
            sr_ref = session.xenapi.SR.get_by_uuid(sr_uuid)
            vdis = session.xenapi.VDI.get_all_records_where("field \"SR\" = \"%s\"" % sr_ref)
            xenapi_location_map = {}
            for vdi in vdis.keys():
                xenapi_location_map[vdis[vdi]['location']] = vdis[vdi]
            volumes = SR().ls(dbg, sr_uuid)
            volume_location_map = {}
            for volume in volumes:
                volume_location_map[volume['uri'][0]] = volume
            xenapi_locations = set(xenapi_location_map.keys())
            volume_locations = set(volume_location_map.keys())
            log("xenapi_locations = %s" % str(xenapi_locations))
            log("volume_locations = %s" % str(volume_locations))

            for new in volume_locations.difference(xenapi_locations):
                db_introduce(volume_location_map[new], gen_uuid())
            for gone in xenapi_locations.difference(volume_locations):
                db_forget(xenapi_location_map[gone]['uuid'])
            for existing in volume_locations.intersection(xenapi_locations):
                pass
            print nil
        elif cmd == 'sr_attach':
            SR().attach(dbg, sr_uuid)
            print nil
        elif cmd == 'sr_detach':
            SR().detach(dbg, sr_uuid)
            print nil
        elif cmd == 'vdi_create':
            size = long(params['args'][0])
            label = params['args'][1]
            description = params['args'][2]
            read_only = params['args'][7] == "true"
            v = Volume().create(dbg, sr_uuid, label, description, size)
            uuid = gen_uuid()
            db_introduce(v, uuid)
            struct = {
                'location': v.uri,
                'uuid': uuid
            }
            print xmlrpclib.dumps((struct,), "", True)
        elif cmd == 'vdi_delete':
            Volume().destroy(dbg, sr_uuid, vdi_location)
            print nil
        elif cmd == 'vdi_clone':
            v = Volume().clone(dbg, sr_uuid, vdi_location)
            uuid = gen_uuid()
            db_introduce(v, uuid)
            struct = {
                'location': v.uri,
                'uuid': uuid
            }
            print xmlrpclib.dumps((struct,), "", True)
        elif cmd == 'vdi_snapshot':
            v = Volume().snapshot(dbg, sr_uuid, vdi_location)
            uuid = gen_uuid()
            db_introduce(v, uuid)
            struct = {
                'location': v.uri,
                'uuid': uuid
            }
            print xmlrpclib.dumps((struct,), "", True)
        elif cmd == 'vdi_attach':
            writable = params['args'][0] == 'true'
            attach = Datapath().attach(dbg, vdi_location, 0)
            path = attach['implementation'][1]
            struct = { 'params': path, 'xenstore_data': {}}
            print xmlrpclib.dumps((struct,), "", True)
        elif cmd == 'vdi_detach':
            Datapath().detach(dbg, vdi_location, 0)
            print nil
        elif cmd == 'vdi_activate':
            writable = params['args'][0] == 'true'
            Datapath().activate(dbg, vdi_location, 0)
            print nil
        elif cmd == 'vdi_deactivate':
            Datapath().deactivate(dbg, vdi_location, 0)
            print nil
        else:
            print xmlrpclib.dumps(xmlrpclib.Fault(int(errno.EINVAL), "Unimplemented command: %s" % cmd, "", True))
    except Exception, e:
        info = sys.exc_info()
        if info[0] == exceptions.SystemExit:
            sys.exit(0)
        tb = "\n".join(traceback.format_tb(info[2]))
        print xmlrpclib.dumps(xmlrpclib.Fault(int(errno.EINVAL), str(e) + "\n" + tb), "", True)
