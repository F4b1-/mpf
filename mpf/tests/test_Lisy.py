import time

from mpf.tests.MpfTestCase import MpfTestCase
from mpf.tests.loop import MockSerial, MockSocket


class MockLisySocket(MockSerial, MockSocket):

    def read(self, length):
        del length
        if not self.queue:
            return b""
        msg = self.queue.pop()
        return msg

    def read_ready(self):
        return bool(self.queue)

    def write_ready(self):
        return True

    def write(self, msg):
        if msg in self.permanent_commands and msg not in self.expected_commands:
            self.queue.append(self.permanent_commands[msg])
            return len(msg)

        # print("Serial received: " + "".join("\\x%02x" % b for b in msg) + " len: " + str(len(msg)))
        if msg not in self.expected_commands:
            self.crashed = True
            print("Unexpected command: " + "".join("\\x%02x" % b for b in msg) + " len: " + str(len(msg)))
            raise AssertionError("Unexpected command: " + "".join("\\x%02x" % b for b in msg) +
                                 " len: " + str(len(msg)))

        if self.expected_commands[msg] is not False:
            self.queue.append(self.expected_commands[msg])

        del self.expected_commands[msg]
        return len(msg)

    def send(self, data):
        return self.write(data)

    def recv(self, size):
        return self.read(size)

    def __init__(self):
        super().__init__()
        self.name = "SerialMock"
        self.expected_commands = {}
        self.queue = []
        self.permanent_commands = {}
        self.crashed = False


class TestLisy(MpfTestCase):

    def getConfigFile(self):
        return 'config.yaml'

    def getMachinePath(self):
        return 'tests/machine_files/lisy/'

    def _mock_loop(self):
        self.clock.mock_serial("com1", self.serialMock)
        self.clock.mock_socket("localhost", 1234, self.serialMock)

    def tearDown(self):
        self.assertFalse(self.serialMock.crashed)
        super().tearDown()

    def get_platform(self):
        return 'lisy'

    def _wait_for_processing(self):
        start = time.time()
        while self.serialMock.expected_commands and not self.serialMock.crashed and time.time() < start + 10:
            self.advance_time_and_run(.01)

    def setUp(self):
        self.expected_duration = 1.5
        self.serialMock = MockLisySocket()

        self.serialMock.permanent_commands = {
            b'\x29': b'\x7F'            # changed switches? -> no
        }

        self.serialMock.expected_commands = {
            b'\x64': b'\x00',           # reset -> ok
            b'\x03': b'\x28',           # get number of lamps -> 40
            b'\x04': b'\x09',           # get number of solenoids -> 9
            b'\x06': b'\x05',           # get number of displays -> 5
        }

        for row in range(8):
            for col in range(8):
                self.serialMock.expected_commands[bytes([40, row * 10 + col])] = b'\x00'\
                    if row * 10 + col != 37 else b'\x01'

        super().setUp()

        self._wait_for_processing()
        self.assertFalse(self.serialMock.expected_commands)

    def test_platform(self):
        # test initial switch state
        self.assertSwitchState("s_test00", False)
        self.assertSwitchState("s_test37", True)
        self.assertSwitchState("s_test77_nc", True)

        self.serialMock.expected_commands = {
            b'\x29': b'\x25'        # 37 turned inactive
        }
        self.advance_time_and_run(.1)
        # turns inactive
        self.assertSwitchState("s_test37", False)

        self.serialMock.expected_commands = {
            b'\x29': b'\xA5'        # 37 turned active (again)
        }
        self.advance_time_and_run(.1)
        # turns active
        self.assertSwitchState("s_test37", True)

        self.serialMock.expected_commands = {
            b'\x29': b'\xCD'        # 77 turned active
        }
        self.advance_time_and_run(.1)
        # turns inactive (because of NC)
        self.assertSwitchState("s_test77_nc", False)

        # pulse coil
        self.serialMock.expected_commands = {
            b'\x17\x00': None
        }
        self.machine.coils.c_test.pulse()
        self._wait_for_processing()
        self.assertFalse(self.serialMock.expected_commands)

        # enable coil
        self.serialMock.expected_commands = {
            b'\x15\x01': None
        }
        self.machine.coils.c_test_allow_enable.enable()
        self._wait_for_processing()
        self.assertFalse(self.serialMock.expected_commands)

        # disable coil
        self.serialMock.expected_commands = {
            b'\x16\x01': None
        }
        self.machine.coils.c_test_allow_enable.disable()
        self._wait_for_processing()
        self.assertFalse(self.serialMock.expected_commands)

        # enable flipper (using light 1)
        self.serialMock.expected_commands = {
            b'\x0b\x01': None
        }
        self.machine.lights.game_over_relay.on()
        self._wait_for_processing()
        self.assertFalse(self.serialMock.expected_commands)

        # disable flipper (using light 1)
        self.serialMock.expected_commands = {
            b'\x0c\x01': None
        }
        self.machine.lights.game_over_relay.off()
        self._wait_for_processing()
        self.assertFalse(self.serialMock.expected_commands)

        # set info display to TEST
        self.serialMock.expected_commands = {
            b'\x1ETEST\x00': None
        }
        self.machine.segment_displays.info_display.set_text("TEST")
        self._wait_for_processing()
        self.assertFalse(self.serialMock.expected_commands)

        # set player 1 display to 42000
        self.serialMock.expected_commands = {
            b'\x1F42000\x00': None
        }
        self.machine.segment_displays.player1_display.set_text("42000")
        self._wait_for_processing()
        self.assertFalse(self.serialMock.expected_commands)