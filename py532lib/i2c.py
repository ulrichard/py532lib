"""@package py532lib.i2c
This module contains classes and functions related to I2C communication for the PN532 NFC Chip.

@author:  DanyO <me@danyo.ca>
@license: The source code within this file is licensed under the BSD 2 Clause license.
          See LICENSE file for more information.

"""

import os, sys, signal
lib_path = os.path.abspath('../')
sys.path.append(lib_path)

from time import sleep
import logging
if sys.version_info > (3, 0):
	from quick2wire.i2c import I2CMaster, reading, writing
else:
	import smbus
from py532lib.i2c import *
from py532lib.frame import *
from py532lib.constants import *


LOGGING_ENABLED = True
LOG_LEVEL = logging.DEBUG
DEFAULT_DELAY = 0.005


class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException()


class Pn532_i2c:
    """Pn532_i2c abstracts away the details related to
    I2C communication with the PN532.

    """
    PN532 = None
    address = None
    i2c_channel = None
    logger = None

    def __init__(self, address=PN532_I2C_SLAVE_ADDRESS, i2c_channel=RPI_DEFAULT_I2C_NEW):
        """Constructor for the Pn532_i2c class.

        Arguments:
        @param[in]  address     I2C slave address for the PN532
                                (default = PN532_FRAME_TYPE_DATA)

        @param[in]  i2c_channel I2C channel to use.
                                (default = RPI_DEFAULT_I2C_NEW)

        """
        self.logger = logging.getLogger()
        self.logger.propagate = LOGGING_ENABLED
        if self.logger.propagate:
            self.logger.setLevel("DEBUG")

        self.address = address
        self.i2c_channel = i2c_channel
        if sys.version_info > (3, 0):
            self.PN532 = I2CMaster(self.i2c_channel)
        else:
            self.PN532 = smbus.SMBus(self.i2c_channel)

    def send_command_check_ack(self, frame, timeout = 3600):
        """Sends a command frame, and waits for an ACK frame.

        Arguments:
        @param[in]  frame   Pn532Frame to send.

        """
        self.send_command(frame)
        if self.read_ack(timeout):
            return True
        else:
            return False

    def read_response(self, timeout = 3600):
        """Wait, then read for a response from the PN532."""
        logging.debug("readResponse...")
        response = [b'\x00\x00\x00\x00\x00\x00\x00']

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout)

        try:	
            while True:

                try:
                    logging.debug("readResponse..............Reading.")
    
                    sleep(DEFAULT_DELAY)
                    if sys.version_info > (3, 0):
                        response = self.PN532.transaction(
                            reading(self.address, 255))
                    else:
                        response = self.PN532.read_i2c_block_data(self.address, 255)
                    logging.debug(response)
                    logging.debug("readResponse..............Read.")
                except TimeoutException:
                    return 'no nfc tag in range'
                except Exception:
                    pass
                else:
                    try:
                        frame = Pn532Frame.from_response(response)

                        # Acknowledge Data frames coming from the PN532
                        if frame.get_frame_type() == PN532_FRAME_TYPE_DATA:
                            self.send_command(Pn532Frame(
                                frame_type=PN532_FRAME_TYPE_ACK))

                    except TimeoutException:
                        return 'no nfc tag in range'
                    except Exception as ex:
                        logging.debug(ex)
                        logging.debug(ex.args)
                        pass
                    else:
                        signal.alarm(0)
                        return frame
        except TimeoutException:
            return 'no nfc tag in range'
        finally:
            signal.signal(signal.SIGALRM, old_handler)
        
    def send_command(self, frame):
        """Sends a command frame to the PN532.

        Arguments:
        @param[in]  frame   Pn532Frame to send.

        """
        logging.debug("send_command...")

        while True:
            try:
                logging.debug("send_command...........Sending.")

                sleep(DEFAULT_DELAY)
                data = frame.to_tuple()
                logging.debug(data)

                if sys.version_info > (3, 0):
                    self.PN532.transaction(
                        writing(self.address, data))
                else:
                    cmd = data[0]
                    data[0] = len(data) - 1
                    ldata = []
                    for byte in data:
                        ldata.append(int(byte))
                    logging.debug(len(ldata[1:]))
                    self.PN532.write_i2c_block_data(self.address, data[0], ldata[1:])

                logging.debug("send_command...........Sent.")
            except Exception as ex:
                logging.debug(ex)

                self.reset_i2c()
                sleep(DEFAULT_DELAY)
            else:
                return True

    def read_ack(self, timeout):
        """Wait for a valid ACK frame to be returned."""
        logging.debug("read_ack...")

        def timeout_handler(signum, frame):
            raise TimeoutException()

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout)

        try:
            while True:
                sleep(DEFAULT_DELAY)
                response_frame = self.read_response()

                if response_frame.get_frame_type() == PN532_FRAME_TYPE_ACK:
                    signal.alarm(0)
                    return True
                else:
                    pass
        except TimeoutException:
         	return 'no nfc tag in range'
        finally:
        	signal.signal(signal.SIGALRM, old_handler)

    def read_mifare(self, timeout = 3600):
        """Wait for a MiFARE card to be in the PN532's field, and read it's UID."""
        frame = Pn532Frame(frame_type=PN532_FRAME_TYPE_DATA, data=bytearray([PN532_COMMAND_INLISTPASSIVETARGET, 0x01, 0x00]))
        self.send_command_check_ack(frame, timeout)

        return self.read_response(timeout)

    def reset_i2c(self):
        """Reset the I2C communication connection."""
        logging.debug("I2C Reset...")

        if sys.version_info > (3, 0):
            self.PN532.close()
            del self.PN532
            self.PN532 = I2CMaster(self.i2c_channel)
        else:
            del self.PN532
            self.PN532 = smbus.SMBus(self.i2c_channel)

        logging.debug("I2C Reset............Created.")

    def SAMconfigure(self, frame=None):
        """Send a SAMCONFIGURATION command to the PN532.

        Arguments:
        @param[in]  frame   Custom SAMconfigure options can be passed here.

        """
        if frame is None:
            frame = Pn532Frame(frame_type=PN532_FRAME_TYPE_DATA,
                               data=bytearray(
                                   [PN532_COMMAND_SAMCONFIGURATION,
                                    PN532_SAMCONFIGURATION_MODE_NORMAL,
                                    PN532_SAMCONFIGURATION_TIMEOUT_50MS,
                                    PN532_SAMCONFIGURATION_IRQ_OFF]))

        self.send_command_check_ack(frame)

    def __exit__(self, type, value, traceback):
        """Make sure the I2C communication channel is closed."""
        if sys.version_info > (3, 0):
            self.PN532.close()
        del self.PN532
