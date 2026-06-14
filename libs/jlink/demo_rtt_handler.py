import threading
import queue
import time
import sys
import os
from libs.jlink.rtt_handler_interface import RTTHandlerInterface

class DemoRTTHandler(RTTHandlerInterface):
    def __init__(self, log_processing_input_queue):
        self._log_queue = log_processing_input_queue
        self._connected = True  # Demo mode is always "connected"
        self._demo_thread = None
        self._stop_demo = threading.Event()

    def connect(self, mcu_name, interface='SWD', block_address=None, print_function=None):
        """
        In demo mode, this method does nothing as we don't actually connect to hardware.
        The demo thread is started automatically.
        
        Args:
            mcu_name (str): Name of the MCU (not used in demo mode)
            interface (str): Interface to use (not used in demo mode)
            block_address (int, optional): Address of the RTT control block (not used in demo mode)
            print_function: Function to print messages (not used in demo mode)

        Returns:
            bool: Always returns True in demo mode
        """
        # Start the demo thread when connect is called
        self._start_demo_thread()
        return True

    def disconnect(self):
        """
        Stop the demo thread and mark as disconnected.
        """
        self._stop_demo.set()
        if self._demo_thread and self._demo_thread.is_alive():
            self._demo_thread.join(timeout=1)
        self._connected = False

    def _start_demo_thread(self):
        """
        Start the demo thread that generates sample messages.
        """
        if self._demo_thread is None or not self._demo_thread.is_alive():
            self._stop_demo.clear()
            self._demo_thread = threading.Thread(
                target=self._demo_loop,
                daemon=True
            )
            self._demo_thread.start()

    def _demo_loop(self):
        demo_messages = []
        try:
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                base_path = os.path.dirname(os.path.abspath(__file__))
                base_path = os.path.join(base_path, '..', '..')
            log_path = os.path.join(base_path, 'debug', 'demo_log.txt')
            with open(log_path, 'r') as f:
                demo_messages = [line.rstrip('\n') for line in f]
        except FileNotFoundError:
            demo_messages = ["[ERROR] demo_log.txt not found. Using default messages."]

        while not self._stop_demo.is_set():
            for msg in demo_messages:
                self._log_queue.put({"line": msg + '\n'})
                if self._stop_demo.wait(timeout=0.01):  # Match original 0.03s interval
                    break
            #if self._stop_demo.wait(timeout=0.001):  # Match original 0.01s cycle pause
            #    break

    def _simple_demo_loop(self):
        """
        Generate demo messages at regular intervals.
        """
        demo_messages = [
            "1 [INFO] System initialized. lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor",
            "2 [DEBUG] Connecting to peripherals. lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor",
            "3 [WARN] Low battery detected. lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor",
            "4 [ERROR] Failed to read sensor data. lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor",
            "5 [INFO] Processing data. lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor",
            "6 [DEBUG] Update complete. lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor, lorem ipsum dolor",
        ]
        while not self._stop_demo.is_set():
            for msg in demo_messages:
                self._log_queue.put({"line" : msg + '\n'})
                if self._stop_demo.wait(timeout=0.001):
                    break
            # Wait a bit between message cycles
            if self._stop_demo.wait(timeout=0.03):
                break

    def get_supported_mcus(self):
        """
        Get a list of supported MCUs for demo mode.
        In demo mode, this returns a sample list.

        Returns:
            List of MCU strings.
        """
        return ['STM32F427II', 'STM32F769NI', 'NRF52840', 'ESP32', 'PIC32MX', 'DEMO_MCU']

    @property
    def is_connected(self):
        """
        Check if currently "connected" (always True in demo mode).

        Returns:
            bool: Always True in demo mode.
        """
        return self._connected

    @property
    def log_queue(self):
        """
        Get the queue containing demo log data.

        Returns:
            queue.Queue: Queue with demo data.
        """
        return self._log_queue
