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

import SR, VDI, SRCommand, util, lvutil
import errno
import os, sys, time
import xml.dom.minidom
import xmlrpclib
import xs_errors

import traceback

CAPABILITIES = ["SR_PROBE","VDI_CREATE","VDI_DELETE","VDI_ATTACH","VDI_DETACH",
                "VDI_ACTIVATE","VDI_DEACTIVATE","VDI_CLONE","VDI_SNAPSHOT","VDI_RESIZE",
                "VDI_INTRODUCE"]

CONFIGURATION = [ ]

DRIVER_INFO = {
    'name': 'dummy',
    'description': 'SR plugin which manages fake data',
    'vendor': 'Citrix Systems Inc',
    'copyright': '(C) 2008 Citrix Systems Inc',
    'driver_version': '1.0',
    'required_api_version': '1.1',
    'capabilities': CAPABILITIES,
    'configuration': CONFIGURATION
    }

TYPE = 'dummy'

class DummySR(SR.SR):
    """dummy storage repository"""
    def handles(type):
        if type == TYPE:
            return True
        return False
    handles = staticmethod(handles)

    def load(self, sr_uuid):
        self.sr_vditype = 'phy'

    def content_type(self, sr_uuid):
        return super(DummySR, self).content_type(sr_uuid)

    def create(self, sr_uuid, size):
        self._assertValues(['sr_uuid','args','host_ref','session_ref','device_config','command','sr_ref'])
        assert(len(self.srcmd.params['args'])==1)

    def delete(self, sr_uuid):
        self._assertValues(['sr_uuid','args','host_ref','session_ref','device_config','command','sr_ref'])
        assert(len(self.srcmd.params['args'])==0)

    def attach(self, sr_uuid):
        self._assertValues(['sr_uuid','args','host_ref','session_ref','device_config','command','sr_ref'])
        assert(len(self.srcmd.params['args'])==0)

    def detach(self, sr_uuid):
        self._assertValues(['sr_uuid','args','host_ref','session_ref','device_config','command','sr_ref'])
        assert(len(self.srcmd.params['args'])==0)

    def probe(self):
        # N.B. There are no SR references
        self._assertValues(['args','host_ref','session_ref','device_config','command'])
        assert(len(self.srcmd.params['args'])==0)
        
        # Create some Dummy SR records
        entry = {}
        entry['size'] = 1024
        SRlist = {}
        SRlist[util.gen_uuid()] = entry

        # Return the Probe XML
        return util.SRtoXML(SRlist)

    def vdi(self, uuid):
        return DummyVDI(self, uuid)
    
    def scan(self, sr_uuid):
        self._assertValues(['sr_uuid','args','host_ref','session_ref','device_config','command','sr_ref'])
        assert(len(self.srcmd.params['args'])==0)
            
        # The list of VDIs comes from the XenAPI - we have no state
        for v in self._getallVDIrecords():
            x = DummyVDI(self, v['uuid'])
            x.size = v['virtual_size']
            x.utilisation = v['physical_utilisation']
            self.vdis[x.uuid] = x
        
        self.physical_size = 2000000000000L
        self.physical_utilisation = 0L
        self.virtual_allocation = 0L
        return super(DummySR, self).scan(sr_uuid)

    def _assertValues(self, vals):
        for attr in vals:
            assert(self.srcmd.params.has_key(attr))
            util.SMlog("%s param %s: [%s]" % (self.cmd,attr,self.srcmd.params[attr]))
            
        # Iterate through the device_config dictionary
        for key in self.dconf.iterkeys():
            util.SMlog("\tdevice_config: [%s:%s]" % (key,self.dconf[key]))        
            
        # Query the sm_config; parameters can be set at Create time. Iterate through keys
        self.sm_config = self.session.xenapi.SR.get_sm_config(self.sr_ref)
        for key in self.sm_config.iterkeys():
            util.SMlog("\tsm_config: [%s:%s]" % (key,self.sm_config[key]))

    def _getallVDIrecords(self):
        """Helper function which returns a list of all VDI records for this SR
        stored in the XenAPI server"""
        # Returns a list of (reference, record) pairs: we only need the records
        vdis = self.session.VDI.get_all_records(self.session_ref)['Value'].values()
        # We only need the VDIs corresponding to this SR
        return filter(lambda v: v['SR'] == self.sr_ref, vdis)


class DummyVDI(VDI.VDI):
    def load(self, vdi_uuid):
        self.path = "/dev/null" # returned on attach
        self.uuid = vdi_uuid
        self.size = 0
        self.utilisation = 0
        self.location = vdi_uuid
        self.sm_config = {}

    def create(self, sr_uuid, vdi_uuid, size):
        self.sr._assertValues(['sr_uuid','args','host_ref','device_config','command','sr_ref','vdi_sm_config'])
        assert(len(self.sr.srcmd.params['args']) == 8)

        self.vdi_sm_config = self.sr.srcmd.params['vdi_sm_config']
        for key in self.vdi_sm_config.iterkeys():
            util.SMlog("\tvdi_sm_config: [%s:%s]" % (key,self.vdi_sm_config[key]))

        for v in self.sr._getallVDIrecords():
            if v['uuid'] == vdi_uuid:
                raise xs_errors.XenError('VDIExists')
        
        self.size = size
        self.utilisation = size
        self.sm_config['samplekey'] = "This is a dummy SR VDI"
        self._db_introduce()
        self.run_corner_cases_tests()
        return self.get_params()

    def delete(self, sr_uuid, vdi_uuid):
        self.sr._assertValues(['sr_uuid','args','host_ref','device_config','command','sr_ref','vdi_ref','vdi_location','vdi_uuid'])
        assert(len(self.sr.srcmd.params['args'])==0)

        # Assert that the VDI record exists
        self.session.VDI.get_record(self.sr.session_ref)
        self.run_corner_cases_tests()
        self._db_forget()

    def introduce(self, sr_uuid, vdi_uuid):
        self.sr._assertValues(['sr_uuid','args','host_ref','device_config','command','sr_ref','vdi_sm_config','new_uuid'])
        assert(len(self.sr.srcmd.params['args'])==0)
        self.vdi_sm_config = self.sr.srcmd.params['vdi_sm_config']
        for key in self.vdi_sm_config.iterkeys():
            util.SMlog("\tvdi_sm_config: [%s:%s]" % (key,self.vdi_sm_config[key]))

        for v in self.sr._getallVDIrecords():
            if v['uuid'] == vdi_uuid:
                raise xs_errors.XenError('VDIExists')
        self.uuid = vdi_uuid
        self.location = self.sr.srcmd.params['vdi_location']
        self._db_introduce()
        self.run_corner_cases_tests()
        return  super(DummyVDI, self).get_params()

    def attach(self, sr_uuid, vdi_uuid):
        self.sr._assertValues(['sr_uuid','args','host_ref','device_config','command','sr_ref','vdi_ref','vdi_location','vdi_uuid'])
        assert(len(self.sr.srcmd.params['args'])==1)
        vdi = super(DummyVDI, self).attach(sr_uuid, vdi_uuid)
        self.run_corner_cases_tests()
        return vdi

    def detach(self, sr_uuid, vdi_uuid):
        self.sr._assertValues(['sr_uuid','args','host_ref','device_config','command','sr_ref','vdi_ref','vdi_location','vdi_uuid'])
        self.run_corner_cases_tests()
        assert(len(self.sr.srcmd.params['args'])==0)

    def activate(self, sr_uuid, vdi_uuid):
        self.sr._assertValues(['sr_uuid','args','host_ref','device_config','command','sr_ref','vdi_ref','vdi_location','vdi_uuid'])
        assert(len(self.sr.srcmd.params['args'])==1)
        self.vdi_ref = self.sr.srcmd.params['vdi_ref']
        self.other_config = self.session.xenapi.VDI.get_other_config(self.vdi_ref)
        self.run_corner_cases_tests()
        for key in self.other_config.iterkeys():
            util.SMlog("\tvdi_other_config: [%s:%s]" % (key,self.other_config[key]))

    def deactivate(self, sr_uuid, vdi_uuid):
        self.sr._assertValues(['sr_uuid','args','host_ref','device_config','command','sr_ref','vdi_ref','vdi_location','vdi_uuid'])
        self.run_corner_cases_tests()
        assert(len(self.sr.srcmd.params['args'])==0)

    def resize(self, sr_uuid, vdi_uuid, size):
        self.sr._assertValues(['sr_uuid','args','host_ref','device_config','command','sr_ref','vdi_ref','vdi_location','vdi_uuid'])
        assert(len(self.sr.srcmd.params['args'])==1)

        self.size = size
        self.utilisation = size
        self._db_update()
        self.run_corner_cases_tests()
        return super(DummyVDI, self).get_params()

    def snapshot(self, sr_uuid, vdi_uuid):
        self.sr._assertValues(['sr_uuid','args','host_ref','device_config','command','sr_ref'])
        assert(len(self.sr.srcmd.params['args'])==0)

        dest = util.gen_uuid()
        vdi = VDI.VDI(self.sr, dest)
        vdi.read_only = True
        vdi.location = dest
        vdi.size = 0
        vdi.utilisation = 0
        vdi._db_introduce()
        self.run_corner_cases_tests()
        return vdi.get_params()

    def clone(self, sr_uuid, vdi_uuid):
        self.sr._assertValues(['sr_uuid','args','host_ref','device_config','command','sr_ref'])
        assert(len(self.sr.srcmd.params['args'])==0)

        dest = util.gen_uuid()
        vdi = VDI.VDI(self.sr, dest)
        vdi.read_only = False
        vdi.location = dest
        vdi.size = 0
        vdi.utilisation = 0
        vdi._db_introduce()
        self.run_corner_cases_tests()
        return vdi.get_params()

    def check_no_other_vdi_operation_in_progress(self):
        vdis = util.list_VDI_records_in_sr(self.sr)
        vdi_ref = self.session.xenapi.VDI.get_by_uuid(self.uuid)
        del vdis[vdi_ref]
        active_vdis = filter(lambda v: v['current_operations'] != {}, vdis.values())
        if len(active_vdis) != 0:
            msg = "LVHDRT: found other operations in progress for VDI: %s" % active_vdis[0]['uuid']
            util.SMlog(msg)
            raise xs_errors.XenError('OtherVDIOperationInProgress')

    def get_attached_vbds(self):
        vdi_ref = self.session.xenapi.VDI.get_by_uuid(self.uuid)
        vbds = self.session.xenapi.VBD.get_all_records_where("field \"VDI\" = \"%s\"" % vdi_ref)
        return filter(lambda v: v['currently_attached'] == "true", vbds.values())

    def check_vbd_list_is_stable(self, attached_vbds):
        newly_attached_vbds = self.get_attached_vbds()
        old_set = set(attached_vbds)
        new_set = set(newly_attached_vbds)
        diff_set = old_set.difference(new_set) | new_set.difference(old_set)
        if len(diff_set) != 0:
            msg = "LVHDRT: found a non-stable VBD: %s" % (diff_set.pop())
            util.SMlog(msg)
            raise xs_errors.XenError('VBDListNotStable')

    def run_corner_cases_tests(self):

        def fn():
            attached_vbds = self.get_attached_vbds()
            for i in range(0,10):
                time.sleep(2)
                self.check_no_other_vdi_operation_in_progress()
                self.check_vbd_list_is_stable(attached_vbds)

        util.fistpoint.activate_custom_fn("LVHDRT_xapiSM_serialization_tests", fn)

if __name__ == '__main__':
    SRCommand.run(DummySR, DRIVER_INFO)
else:
    SR.registerSR(DummySR)

class SR:
    def create(self, dbg, uri, configuration):
        return
    def destroy(self, dbg, uri):
        return

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

if __name__ == '__main__':
    try:
        if len(sys.argv) <> 2:
            util.SMlog("Failed to parse commandline; wrong number of arguments; argv = %s" % (repr(sys.argv)))
            raise xs_errors.XenError('BadRequest')

        # Debug logging of the actual incoming command from the caller.
        util.SMlog( "" )
        util.SMlog( "SM.parse: DEBUG: args = %s,\n%s" % \
                    ( sys.argv[0], \
                      util.splitXmlText( util.hideMemberValuesInXmlParams( \
                                         sys.argv[1] ), showContd=True ) ), \
                                         priority=syslog.LOG_DEBUG )

        try:
            params, methodname = xmlrpclib.loads(sys.argv[1])
            cmd = methodname
            params = params[0] # expect a single struct
            params = params

            # params is a dictionary
            dconf = params['device_config']
            if params.has_key('sr_uuid'):
                sr_uuid = params['sr_uuid']
            if params.has_key('vdi_uuid'):
                vdi_uuid = params['vdi_uuid']

            dbg = "Dummy"
            import XenAPI

            session = XenAPI.xapi_local()
            session.xenapi.login_with_password('root', '')

            def db_introduce(v, uuid):
                sm_config = { }
                ty = "user"
                is_a_snapshot = False
                metadata_of_pool = "OpaqueRef:NULL"
                snapshot_time = "19700101T00:00:00Z"
                snapshot_of = "OpaqueRef:NULL"
                sharable = True
                sr_ref = session.xenapi.SR.get_by_uuid(sr_uuid)
                read_only = False
                managed = True
                session.xenapi.VDI.db_introduce(uuid, v.name, v.description, sr_ref, ty, shareable, read_only, {}, v.key, {}, sm_config, managed, str(v.size), str(v.size), metadata_of_pool, is_a_snapshot, xmlrpclib.DateTime(snapshot_time), snapshot_of)

            def gen_uuid():
                return subprocess.Popen(["uuidgen", "-r"], stdout=subprocess.PIPE).communicate()[0].strip()

            if cmd == 'sr_create':
                sr = SR().create(dbg, sr_uuid, dconf)
                util.SMlog("SM.Print = ", xmlrpclib.dumps((None,), "", True, allow_none=True))
            elif cmd == 'sr_delete':
                sr = SR().destroy(dbg, sr_uuid)
                util.SMlog("SM.Print = ", xmlrpclib.dumps((None,), "", True, allow_none=True))
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
                util.SMlog("SM.Print = ", xmlrpclib.dumps((struct,), "", True))
            elif cmd == 'vdi_delete':
                Volume().destroy(dbg, sr_uuid, vdi_uuid)
                util.SMlog("SM.Print = ", xmlrpclib.dumps((None,), "", True, allow_none=True))
            elif cmd == 'vdi_clone':
                v = Volume().clone(dbg, sr_uuid, vdi_uuid)
                uuid = gen_uuid()
                db_introduce(v, uuid)
                struct = {
                    'location': v.uri,
                    'uuid': uuid
                }
                util.SMlog("SM.Print = ", xmlrpclib.dumps((struct,), "", True))
            elif cmd == 'vdi_snapshot':
                v = Volume().snapshot(dbg, sr_uuid, vdi_uuid)
                uuid = gen_uuid()
                db_introduce(v, uuid)
                struct = {
                    'location': v.uri,
                    'uuid': uuid
                }
                util.SMlog("SM.Print = ", xmlrpclib.dumps((struct,), "", True))

        except Exception, e:
            util.SMlog("Failed to parse commandline; exception = %s argv = %s" % (str(e), repr(sys.argv)))
            raise xs_errors.XenError('BadRequest')
    except:
        traceback.print_tb()
