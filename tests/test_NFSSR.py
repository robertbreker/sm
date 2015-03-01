import mock
import nfs
import NFSSR
import unittest
import XenAPI


class FakeNFSSR(NFSSR.NFSSR):
    uuid = None
    sr_ref = None
    session = None
    srcmd = None

    def __init__(self, srcmd, none):
        self.dconf = srcmd.dconf
        self.srcmd = srcmd


class TestNFSSR(unittest.TestCase):

    def create_nfssr(self, server='aServer', serverpath='/aServerpath',
                     sr_uuid='asr_uuid', nfsversion=None, options=None):
        srcmd = mock.Mock()
        srcmd.dconf = {
            'server': server,
            'serverpath': serverpath
        }
        if nfsversion:
            srcmd.dconf.update({'nfsversion': nfsversion})
        if options:
            srcmd.dconf.update({'options': options})
        srcmd.params = {
            'command': 'some_command',
            'device_config': {}
        }
        nfssr = FakeNFSSR(srcmd, None)
        nfssr.load(sr_uuid)
        return nfssr

    @mock.patch('NFSSR.Lock')
    def test_load(self, Lock):
        self.create_nfssr()

    @mock.patch('NFSSR.Lock')
    @mock.patch('nfs.validate_nfsversion')
    def test_load_validate_nfsversion_called(self, validate_nfsversion, Lock):
        nfssr = self.create_nfssr(nfsversion='aNfsversion')

        validate_nfsversion.assert_called_once_with('aNfsversion')

    @mock.patch('NFSSR.Lock')
    @mock.patch('nfs.validate_nfsversion')
    def test_load_validate_nfsversion_returnused(self, validate_nfsversion,
                                                 Lock):
        validate_nfsversion.return_value = 'aNfsversion'

        self.assertEquals(self.create_nfssr().nfsversion, "aNfsversion")

    @mock.patch('NFSSR.Lock')
    @mock.patch('nfs.validate_nfsversion')
    def test_load_validate_nfsversion_exceptionraised(self,
                                                      validate_nfsversion,
                                                      Lock):
        validate_nfsversion.side_effect = nfs.NfsException('aNfsException')

        self.assertRaises(nfs.NfsException, self.create_nfssr)

    @mock.patch('NFSSR.NFSSR.is_hardmount_configured')
    @mock.patch('util.makedirs')
    @mock.patch('NFSSR.Lock')
    @mock.patch('nfs.mount')
    @mock.patch('util._testHost')
    @mock.patch('nfs.check_server_tcp')
    @mock.patch('nfs.validate_nfsversion')
    def test_attach(self, validate_nfsversion, check_server_tcp, _testhost,
                    mount, Lock, makedirs, is_hardmount_configured):
        validate_nfsversion.return_value = "aNfsversionChanged"
        is_hardmount_configured.return_value = 'aHardMountOption'
        nfssr = self.create_nfssr(server='aServer', serverpath='/aServerpath',
                                  sr_uuid='UUID')

        nfssr.attach(None)

        check_server_tcp.assert_called_once_with('aServer',
                                                 'aNfsversionChanged')
        mount.assert_called_once_with('/var/run/sr-mount/UUID',
                                           'aServer',
                                           '/aServerpath/UUID',
                                           'tcp',
                                           timeout=0,
                                           nfsversion='aNfsversionChanged',
                                           hardmount='aHardMountOption')


    def test_is_hardmount_configured_options_standalone(self):
        nfssr = self.create_nfssr(options="hardmount")

        hardmount = nfssr.is_hardmount_configured()

        self.assertEqual(hardmount, True)

    def test_is_hardmount_configured_options_one_in_many(self):
        nfssr = self.create_nfssr(options="I, like, using, hardmount, really")

        hardmount = nfssr.is_hardmount_configured()

        self.assertEqual(hardmount, True)

    def test_is_hardmount_configured_options_other_config(self):
        nfssr = self.create_nfssr()
        nfssr.session = mock.Mock(spec=XenAPI.Session)
        nfssr.session.xenapi = mock.Mock()
        nfssr.session.xenapi.SR = mock.Mock()
        nfssr.session.xenapi.SR.get_other_config = mock.Mock()
        nfssr.session.xenapi.SR.get_other_config.return_value = {'hardmount':
                                                                 'tRuE'}

        hardmount = nfssr.is_hardmount_configured()

        nfssr.session.xenapi.SR.get_other_config.assert_called_once()
        self.assertEqual(hardmount, True)

    def test_is_hardmount_configured_default_False(self):
        nfssr = self.create_nfssr()

        hardmount = nfssr.is_hardmount_configured()

        self.assertEqual(hardmount, False)
