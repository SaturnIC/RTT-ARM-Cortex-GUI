import pylink
import threading
import queue
import re
import time
from libs.jlink.rtt_handler_interface import RTTHandlerInterface

class RTTHandler(RTTHandlerInterface):
    def __init__(self, log_processing_input_queue):
        self._jlink = pylink.JLink()
        self._supported_mcu_list = [self._jlink.supported_device(i).name.upper() for i in range(self._jlink.num_supported_devices())]
        self._log_queue = log_processing_input_queue
        self._connected = False
        self._rtt_thread = None
        self._buffer = ""
        self._ansi_pattern = re.compile(rb'\x1b\[[0-9;]*[a-zA-Z]')

    def connect(self, mcu_name, interface='SWD', block_address=None):
        """
        Connect to the specified MCU and start RTT.

        Args:
            mcu_name (str): Name of the MCU to connect to.
            interface (str): Interface to use ('SWD' or 'JTAG').
            block_address (int, optional): Address of the RTT control block.

        Returns:
            bool: True if connection was successful, False otherwise.
        """
        try:
            self._jlink.open()
            line = "connecting to %s via %s...\n" % (mcu_name, interface)
            self._log_queue.put({"line" : line  + '\n'})
            if interface == 'SWD':
                self._jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
            elif interface == 'JTAG':
                self._jlink.set_tif(pylink.enums.JLinkInterfaces.JTAG)
            else:
                raise ValueError(f"Unsupported interface: {interface}")
            self._jlink.connect(mcu_name)
            self._log_queue.put({"line" : "connected, starting RTT...\n"})
            self._jlink.rtt_start(block_address)
            self._connected = True

            # Start RTT read thread
            self._rtt_thread = threading.Thread(
                target=self._read_rtt,
                daemon=True
            )
            self._rtt_thread.start()

            return True
        except pylink.JLinkException as e:
            self.disconnect()
            raise Exception(f'Connection failed: {str(e)}')

    def disconnect(self):
        """
        Disconnect from the MCU and stop RTT.
        """
        if self._connected:
            self._jlink.close()
            self._connected = False

    def remove_ansi_bytes(self, byte_str: bytes) -> bytes:
        """
        Remove ANSI escape sequences from a byte string.

        Args:
            byte_str (bytes): Input byte string containing ANSI codes.

        Returns:
            bytes: Cleaned byte string without ANSI sequences.
        """
        cleaned = self._ansi_pattern.sub(b'', byte_str)
        return cleaned

    def _insert_lines_in_log_processing_queue(self, lines):
        for line in lines:
            if line:  # Skip empty lines
                self._log_queue.put({"line" : line  + '\n'})

    def _read_rtt(self):
        """
        Continuously read RTT data, parse into lines, and put each line into the log queue.
        """
        while self._connected:
            try:
                data = self._jlink.rtt_read(0, 4096)
                if data:
                    byte_string = bytes(data)
                    ansi_clean_string = self.remove_ansi_bytes(byte_string)
                    ff_clean_string = ansi_clean_string.replace(b'\n\xff0', b'\n').replace(b'\n\xff', b'\n')
                    latin_string = ff_clean_string.decode('utf-8', errors='ignore') # first two bytes used in header?
                    full_string = self._buffer + latin_string

                    # parse lines
                    lines = full_string.replace('\r', '').split('\n')
                    lines = [line.lstrip('01') for line in lines]
                    if full_string.endswith('\n'):
                        # Complete data, forward all lines
                        self._insert_lines_in_log_processing_queue(lines)
                        self._buffer = ""
                    else:
                        # Incomplete data, accumulate in buffer
                        self._insert_lines_in_log_processing_queue(lines[:-1])
                        self._buffer = lines[-1]

            except pylink.JLinkException:
                break
            time.sleep(0.1)

    def get_supported_mcus(self):
        """
        Get the list of supported MCUs.

        Returns:
            List of MCU strings.
        """
        return self._supported_mcu_list

    @property
    def is_connected(self):
        """
        Check if currently connected to an MCU.

        Returns:
            bool: True if connected, False otherwise.
        """
        return self._connected

    @property
    def log_queue(self):
        """
        Get the queue containing RTT log data.

        Returns:
            queue.Queue: Queue with RTT data.
        """
        return self._log_queue
