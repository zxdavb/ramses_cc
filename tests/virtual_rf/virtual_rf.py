#!/usr/bin/env python3
#
"""A virtual RF network useful for testing."""

# NOTE: does not rely on ramses_rf library

import asyncio
from collections import deque
from contextlib import ExitStack
from io import FileIO
import logging
import os
import pty
from selectors import EVENT_READ, DefaultSelector
import signal
import tty
from typing import TypeAlias

from serial import Serial, serial_for_url  # type: ignore[import]

from .const import HgiFwTypes

_FD: TypeAlias = int  # file descriptor
_PN: TypeAlias = str  # port name

# _FILEOBJ: TypeAlias = int | Any  # int | HasFileno


_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)

DEFAULT_GWY_ID = bytes("18:000730", "ascii")
DEVICE_ID = "device_id"
DEVICE_ID_BYTES = "device_id_bytes"
FW_VERSION = "fw_version"

MAX_NUM_PORTS = 6


_GWY_ATTRS: dict[str, int | str | None] = {
    HgiFwTypes.HGI_80: {
        "manufacturer": "Texas Instruments",
        "product": "TUSB3410 Boot Device",
        "vid": 0x10AC,  # Honeywell, Inc.
        "pid": 0x0102,  # HGI80
        "description": "TUSB3410 Boot Device",
        "interface": None,
        "serial_number": "TUSB3410",
        "subsystem": "usb",
        #
        "_dev_path": "/dev/ttyUSB0",
        "_dev_by-id": "/dev/serial/by-id/usb-Texas_Instruments_TUSB3410_Boot_Device_TUSB3410-if00-port0",
    },
    HgiFwTypes.EVOFW3: {
        "manufacturer": "SparkFun",
        "product": "evofw3 atmega32u4",
        "vid": 0x1B4F,  # SparkFun Electronics
        "pid": 0x9206,  #
        "description": "evofw3 atmega32u4",
        "interface": None,
        "serial_number": None,
        "subsystem": "usb-serial",
        #
        "_dev_path": "/dev/ttyACM0",
        "_dev_by-id": "/dev/serial/by-id/usb-SparkFun_evofw3_atmega32u4-if00",
    },
    f"{HgiFwTypes.EVOFW3}_alt": {
        "manufacturer": "FTDI",
        "product": "FT232R USB UART",
        "vid": 0x0403,  # FTDI
        "pid": 0x6001,  # SSM-D2
        "description": "FT232R USB UART - FT232R USB UART",
        "interface": "FT232R USB UART",
        "serial_number": "A50285BI",
        "subsystem": "usb-serial",
        #
        "_dev_path": "/dev/ttyUSB0",
        "_dev_by-id": "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A50285BI-if00-port0",
    },
    # .                /dev/serial/by-id/usb-SHK_NANO_CUL_868-if00-port0
    # .                /dev/serial/by-id/usb-1a86_USB2.0-Serial-if00-port0
}


class VirtualComPortInfo:
    """A container for emulating pyserial's PortInfo (SysFS) objects."""

    manufacturer: str
    product: str

    vid: int
    pid: int

    description: str
    interface: None | str
    serial_number: None | str
    subsystem: str

    def __init__(self, port_name: _PN, dev_type: HgiFwTypes | None) -> None:
        """Supplies a useful subset of PortInfo attrs according to gateway type."""

        self.device = port_name  # # e.g. /dev/pts/2 (a la /dev/ttyUSB0)
        self.name = port_name[5:]  # e.g.      pts/2 (a la      ttyUSB0)

        self._set_attrs(_GWY_ATTRS[dev_type or HgiFwTypes.EVOFW3])

    def _set_attrs(self, gwy_attrs: dict[str, int | str | None]) -> None:
        """Set the USB attributes according to the gateway type."""

        self.manufacturer = gwy_attrs["manufacturer"]
        self.product = gwy_attrs["product"]

        self.vid = gwy_attrs["vid"]
        self.pid = gwy_attrs["pid"]

        self.description = gwy_attrs["description"]
        self.interface = gwy_attrs["interface"]
        self.serial_number = gwy_attrs["serial_number"]
        self.subsystem = gwy_attrs["subsystem"]


class VirtualRfBase:
    """A virtual many-to-many network of serial port (a la RF network).

    Creates a collection of serial ports. When data frames are received from any one
    port, they are sent to all the other ports.

    The data frames are in the RAMSES_II format, terminated by `\\r\\n`.
    """

    def __init__(self, num_ports: int, log_size: int = 100) -> None:
        """Create `num_ports` virtual serial ports."""

        if os.name != "posix":
            raise RuntimeError(f"Unsupported OS: {os.name} (requires termios)")

        if 1 > num_ports > MAX_NUM_PORTS:
            raise ValueError(f"Port limit exceeded: {num_ports}")

        self._port_info_list: dict[_PN, VirtualComPortInfo] = {}

        self._loop = asyncio.get_running_loop()

        self._file_objs: dict[_FD, FileIO] = {}  # master fd to port object, for I/O
        self._pty_names: dict[_FD, _PN] = {}  # master fd to slave port name, for logger
        self._tty_names: dict[_PN, _FD] = {}  # slave port name to slave fd, for cleanup

        # self._setup_event_handlers()  # TODO: needs fixing/testing
        for idx in range(num_ports):
            self._create_port(idx)

        self._log: list[tuple[str, str, bytes]] = deque([], log_size)
        self._task: asyncio.Task = None  # type: ignore[assignment]

    def _create_port(self, port_idx: int, dev_type: None | HgiFwTypes = None) -> None:
        """Create a port without a HGI80 attached."""
        master_fd, slave_fd = pty.openpty()  # pty, tty

        tty.setraw(master_fd)  # requires termios module, so: works only on *nix
        os.set_blocking(master_fd, False)  # make non-blocking

        self._file_objs[master_fd] = open(master_fd, "rb+", buffering=0)
        self._pty_names[master_fd] = os.ttyname(slave_fd)
        self._tty_names[os.ttyname(slave_fd)] = slave_fd

        self._set_comport_info(self._pty_names[master_fd], dev_type=dev_type)

    def comports(self, include_links=False) -> list[VirtualComPortInfo]:  # unsorted
        """Use this method to monkey patch serial.tools.list_ports.comports()."""
        return list(self._port_info_list.values())

    def _set_comport_info(
        self, port_name: _PN, dev_type: None | HgiFwTypes = None
    ) -> VirtualComPortInfo:
        """Add comport info to the list (wont fail if the entry already exists)"""
        self._port_info_list.pop(port_name, None)
        self._port_info_list[port_name] = VirtualComPortInfo(port_name, dev_type)
        return self._port_info_list[port_name]

    @property
    def ports(self) -> list[_PN]:
        """Return a list of the names of the serial ports."""
        return list(self._tty_names)  # [p.name for p in self.comports]

    async def stop(self) -> None:
        """Stop polling ports and distributing data."""

        if not self._task or self._task.done():
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

        self._cleanup()

    def _cleanup(self):
        """Destroy file objects and file descriptors."""

        for f in self._file_objs.values():
            f.close()  # also closes corresponding master fd
        for fd in self._tty_names.values():
            os.close(fd)  # else this slave fd will persist

    def start(self) -> asyncio.Task:
        """Start polling ports and distributing data, calls `pull_data_from_port()`."""

        self._task = self._loop.create_task(self._poll_ports_for_data())
        return self._task

    async def _poll_ports_for_data(self) -> None:
        """Send data received from any one port (as .write(data)) to all other ports."""

        with DefaultSelector() as selector, ExitStack() as stack:
            for fd, f in self._file_objs.items():
                stack.enter_context(f)
                selector.register(fd, EVENT_READ)

            while True:
                for key, event_mask in selector.select(timeout=0):
                    if not event_mask & EVENT_READ:
                        continue
                    self._pull_data_from_src_port(key.fileobj)  # type: ignore[arg-type]  # fileobj type is int | HasFileno
                    await asyncio.sleep(0)
                else:
                    await asyncio.sleep(0.0001)

    def _pull_data_from_src_port(self, master: _FD) -> None:
        """Pull the data from the sending port and process any frames."""

        data = self._file_objs[master].read()  # read the Tx'd data
        self._log.append((self._pty_names[master], "SENT", data))

        # this assumes all .write(data) are 1+ whole frames terminated with \r\n
        for frame in (d + b"\r\n" for d in data.split(b"\r\n") if d):  # ignore b""
            if f := self._proc_before_tx(frame, master):
                self._cast_frame_to_all_ports(f, master)  # can cast (is not echo only)

    def _cast_frame_to_all_ports(self, frame: bytes, master: _FD) -> None:
        """Pull the frame from the sending port and cast it to the RF."""

        _LOGGER.info(f"{self._pty_names[master]:<11} cast:  {frame!r}")
        for fd in self._file_objs:
            self._push_frame_to_dst_port(frame, fd)

    def _push_frame_to_dst_port(self, frame: bytes, master: _FD) -> None:
        """Push the frame to a single destination port."""

        if data := self._proc_after_rx(frame, master):
            self._log.append((self._pty_names[master], "RCVD", data))
            self._file_objs[master].write(data)

    def _proc_after_rx(self, frame: bytes, master: _FD) -> None | bytes:
        """Allow the device to modify the frame after receiving (e.g. adding RSSI)."""
        return frame

    def _proc_before_tx(self, frame: bytes, master: _FD) -> None | bytes:
        """Allow the device to modify the frame before sending (e.g. changing addr0)."""
        return frame

    def _setup_event_handlers(self) -> None:
        def handle_exception(loop, context: dict):
            """Handle exceptions on any platform."""
            _LOGGER.error("Caught an exception: %s, cleaning up...", context["message"])
            self._cleanup()
            err = context.get("exception")
            if err:
                raise err

        async def handle_sig_posix(sig) -> None:
            """Handle signals on posix platform."""
            _LOGGER.error("Received a signal: %s, cleaning up...", sig.name)
            self._cleanup()
            signal.raise_signal(sig)

        _LOGGER.debug("Creating exception handler...")
        self._loop.set_exception_handler(handle_exception)

        _LOGGER.debug("Creating signal handlers...")
        if os.name == "posix":  # signal.SIGKILL people?
            for sig in (signal.SIGABRT, signal.SIGINT, signal.SIGTERM):
                self._loop.add_signal_handler(
                    sig, lambda sig=sig: self._loop.create_task(handle_sig_posix(sig))
                )
        else:  # unsupported OS
            raise RuntimeError(f"Unsupported OS for this module: {os.name} (termios)")


class VirtualRf(VirtualRfBase):
    """A virtual network of serial ports, each with an optional HGI80s or compatible.

    Frames are modified/dropped according to the expected behaviours of the gateway that
    is transmitting (addr0) / receiving (RSSI) it.
    """

    def __init__(self, num_ports: int, log_size: int = 100, start: bool = True) -> None:
        """Create a number of virtual serial ports.

        Each port has the option of a HGI80 or evofw3-based gateway device.
        """

        self._gateways: dict[_PN, dict] = {}

        super().__init__(num_ports, log_size)

        if start:
            self.start()

    @property
    def gateways(self) -> dict[str, _PN]:
        return {v[DEVICE_ID]: k for k, v in self._gateways.items()}

    def set_gateway(
        self,
        port_name: _PN,
        device_id: str,
        fw_type: HgiFwTypes = HgiFwTypes.EVOFW3,
    ) -> None:
        """Attach a gateway with a given device_id and FW type to a port.

        Raise an exception if the device_id is already attached to another port.
        """

        if port_name not in self.ports:
            raise LookupError(f"Port does not exist: {port_name}")

        if [v for k, v in self.gateways.items() if k != port_name and v == device_id]:
            raise LookupError(f"Gateway exists on another port: {device_id}")

        if fw_type not in HgiFwTypes:
            raise LookupError(f"Unknown FW specified for gateway: {fw_type}")

        self._gateways[port_name] = {
            DEVICE_ID: device_id,
            FW_VERSION: fw_type,
            DEVICE_ID_BYTES: bytes(device_id, "ascii"),
        }

        self._set_comport_info(port_name, dev_type=fw_type)

    def _proc_after_rx(self, frame: bytes, master: _FD) -> None | bytes:
        """Return the frame as it would have been modified by a gateway after Rx.

        Return None if the bytes are not to be Rx by this device.

        Both FW types will prepend an RSSI to the frame.
        """

        if frame[:1] != b"!":
            return b"000 " + frame

        # The type of Gateway will inform next steps...
        gwy = self._gateways.get(self._pty_names[master], {})  # not a ramses_rf gwy

        if gwy.get(FW_VERSION) != HgiFwTypes.EVOFW3:
            return None

        if frame == b"!V":
            return b"# evofw3 0.7.1\r\n"  # self._file_objs[master].write(data)
        return None  # TODO: return the ! response

    def _proc_before_tx(self, frame: bytes, master: _FD) -> None | bytes:
        """Return the frame as it would have been modified by a gateway before Tx.

        Return None if the bytes are not to be Tx to the RF ether (e.g. to echo only).

        Both FW types will convert addr0 (only) from 18:000730 to its actual device_id.
        HGI80-based gateways will silently drop frames with addr0 other than 18:000730.
        """

        # The type of Gateway will inform next steps...
        gwy = self._gateways.get(self._pty_names[master], {})  # not a ramses_rf gwy

        # Handle trace flags (evofw3 only)
        if frame[:1] == b"!":  # never to be cast, but may be echo'd, or other response
            if gwy.get(FW_VERSION) == HgiFwTypes.EVOFW3:
                self._push_frame_to_dst_port(frame, master)
            return None  # do not Tx the frame

        if not gwy:  # TODO: ?should raise: but is probably from test suite
            return frame

        # Real HGI80s will silently drop cmds if addr0 is not the 18:000730 sentinel
        if gwy[FW_VERSION] == HgiFwTypes.HGI_80 and frame[7:16] != DEFAULT_GWY_ID:
            return None

        # Both (HGI80 & evofw3) will swap out addr0 (and only addr0)
        if frame[7:16] == DEFAULT_GWY_ID:
            frame = frame[:7] + gwy[DEVICE_ID_BYTES] + frame[16:]

        return frame


async def main():
    """ "Demonstrate the class functionality."""

    num_ports = 3

    rf = VirtualRf(num_ports)
    print(f"Ports are: {rf.ports}")

    sers: list[Serial] = [serial_for_url(rf.ports[i]) for i in range(num_ports)]  # type: ignore[annotation-unchecked]

    for i in range(num_ports):
        sers[i].write(bytes(f"Hello World {i}! ", "utf-8"))
        await asyncio.sleep(0.005)  # give the write a chance to effect

        print(f"{sers[i].name}: {sers[i].read(sers[i].in_waiting)}")
        sers[i].close()

    await rf.stop()


if __name__ == "__main__":
    asyncio.run(main())
