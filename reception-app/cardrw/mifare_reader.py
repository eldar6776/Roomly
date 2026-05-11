import hid
import struct
from datetime import datetime

VID = 0x04D8
PID = 0x002F


class MifareHotelReader:
    def __init__(self, vid=VID, pid=PID):
        self.vid = vid
        self.pid = pid
        self.device = hid.device()
        self.connected = False

    def connect(self):
        try:
            self.device.open(self.vid, self.pid)
            self.device.set_nonblocking(0)
            self.connected = True
            return True
        except OSError:
            self.connected = False
            return False

    def close(self):
        if self.connected:
            self.device.close()
            self.connected = False

    def _replace_chars(self, text):
        replacements = {
            "Č": "C", "Ć": "C", "č": "c", "ć": "c",
            "Ž": "Z", "ž": "z", "Š": "S", "š": "s",
            "Đ": "D", "đ": "d"
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    def send_command(self, buffer):
        if not self.connected:
            return None

        if len(buffer) < 65:
            buffer += [0xFF] * (65 - len(buffer))
        elif len(buffer) > 65:
            buffer = buffer[:65]

        try:
            self.device.write(buffer)
            response = self.device.read(65)
            if len(response) == 64:
                response = [0x00] + response
            return response
        except OSError:
            return None

    def read_card(self):
        buffer = [0x00, ord('R')] + [0xFF] * 63
        response = self.send_command(buffer)
        if not response:
            return None

        if response[1] == 0x46:
            return None

        try:
            card_id_bytes = response[2:6]
            card_id = struct.unpack('<I', bytes(card_id_bytes))[0]

            day = bytes(response[10:12]).decode('ascii', errors='ignore')
            month = bytes(response[12:14]).decode('ascii', errors='ignore')
            year = bytes(response[14:16]).decode('ascii', errors='ignore')
            hour = bytes(response[16:18]).decode('ascii', errors='ignore')
            minute = bytes(response[18:20]).decode('ascii', errors='ignore')

            card_type = chr(response[8]) if response[8] not in (0xFF, 0x00) else "Nepoznato"
            room_address = bytes(response[23:28]).decode('ascii', errors='ignore').strip('\x00\xff')
            object_id = bytes(response[32:42]).decode('ascii', errors='ignore').strip('\x00\xff ').strip()
            first_name = bytes(response[48:64]).decode('utf-8', errors='ignore').replace('\x00', '').strip()

            return {
                "card_id": card_id,
                "card_type": card_type,
                "object_id": object_id,
                "valid_until": f"{day}.{month}.20{year} {hour}:{minute}",
                "room_address": room_address,
                "first_name": first_name
            }
        except Exception:
            return None

    def write_card(self, card_type, room_number, date_time: datetime, sys_id, first_name, last_name, gender='M', language='E'):
        first_name = self._replace_chars(first_name or ' ').upper()
        last_name = self._replace_chars(last_name or ' ').upper()

        buffer = [0x7F] * 65
        buffer[0] = 0x00
        buffer[1] = ord('W')
        buffer[2] = ord(card_type)

        day = f"{date_time.day:02d}"
        month = f"{date_time.month:02d}"
        year = f"{date_time.year % 100:02d}"
        hour = f"{date_time.hour:02d}"
        minute = f"{date_time.minute:02d}"

        date_str = f"{day}{month}{year}{hour}{minute}"
        for i, char in enumerate(date_str):
            buffer[3 + i] = ord(char)

        if card_type == '0':
            addr_str = "00000"
        else:
            addr_str = f"{int(room_number):05d}"

        for i, char in enumerate(addr_str):
            buffer[13 + i] = ord(char)

        buffer[18] = ord('N')
        buffer[19] = ord(language[0].upper())
        buffer[20] = ord(' ')
        buffer[21] = ord(gender)

        sys_id_str = f"{int(sys_id):05d}"[-5:]
        for i, char in enumerate(sys_id_str):
            buffer[22 + i] = ord(char)

        for i in range(16):
            buffer[32 + i] = ord(' ')
            buffer[48 + i] = ord(' ')

        for i, char in enumerate(last_name[:16]):
            buffer[32 + i] = ord(char)

        for i, char in enumerate(first_name[:16]):
            buffer[48 + i] = ord(char)

        response = self.send_command(buffer)
        return bool(response)
