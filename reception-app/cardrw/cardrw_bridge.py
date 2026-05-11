import json
import sys
from datetime import datetime

from mifare_reader import MifareHotelReader


def emit(payload):
    print(json.dumps(payload, ensure_ascii=False))


def parse_stdin_json():
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    return json.loads(raw)


def map_language(app_lang: str) -> str:
    normalized = (app_lang or '').strip().lower()
    if normalized == 'srb':
        return 'B'
    if normalized == 'eng':
        return 'E'
    if normalized == 'ger':
        return 'G'
    return (normalized[:1] or 'E').upper()


def handle_check():
    reader = MifareHotelReader()
    connected = reader.connect()
    if connected:
        reader.close()
        emit({"ok": True, "available": True, "message": "Reader connected"})
        return 0

    emit({"ok": True, "available": False, "message": "Reader not detected"})
    return 0


def handle_write_guest():
    payload = parse_stdin_json()

    room_number = payload.get('room_number')
    check_out_date = payload.get('check_out_date')
    check_out_time = payload.get('check_out_time')
    sys_id = payload.get('sys_id')
    first_name = payload.get('first_name') or ' '
    last_name = payload.get('last_name') or ' '
    gender = payload.get('gender', 'M')
    language = map_language(payload.get('language', 'srb'))

    if not room_number:
        emit({"ok": False, "message": "room_number is required"})
        return 1

    if not check_out_date or not check_out_time:
        emit({"ok": False, "message": "check_out_date and check_out_time are required"})
        return 1

    if sys_id is None:
        emit({"ok": False, "message": "sys_id is required"})
        return 1

    try:
        date_time = datetime.strptime(f"{check_out_date} {check_out_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        emit({"ok": False, "message": "Invalid date/time format. Expected YYYY-MM-DD and HH:MM"})
        return 1

    reader = MifareHotelReader()
    if not reader.connect():
        emit({"ok": False, "message": "Reader not available"})
        return 1

    try:
        success = reader.write_card(
            card_type='G',
            room_number=room_number,
            date_time=date_time,
            sys_id=sys_id,
            first_name=first_name,
            last_name=last_name,
            gender=gender,
            language=language,
        )

        if not success:
            emit({"ok": False, "message": "Failed to write card"})
            return 1

        emit({
            "ok": True,
            "message": "Guest card programmed",
            "room_number": str(room_number),
            "valid_until": f"{check_out_date} {check_out_time}",
            "sys_id": int(sys_id),
            "card_type": "G",
            "first_name": first_name,
            "last_name": last_name,
        })
        return 0
    finally:
        reader.close()


def handle_write_staff_card():
    payload = parse_stdin_json()

    card_type = payload.get('card_type')  # 'H' (maid) or 'M' (manager)
    check_out_date = payload.get('check_out_date')
    check_out_time = payload.get('check_out_time', '23:59')
    sys_id = payload.get('sys_id')

    if card_type not in ('H', 'M'):
        emit({"ok": False, "message": "card_type must be H (maid) or M (manager)"})
        return 1

    if not check_out_date:
        emit({"ok": False, "message": "check_out_date is required"})
        return 1

    if sys_id is None:
        emit({"ok": False, "message": "sys_id is required"})
        return 1

    try:
        date_time = datetime.strptime(f"{check_out_date} {check_out_time}", "%Y-%m-%d %H:%M")
    except ValueError:
        emit({"ok": False, "message": "Invalid date/time format. Expected YYYY-MM-DD and HH:MM"})
        return 1

    reader = MifareHotelReader()
    if not reader.connect():
        emit({"ok": False, "message": "Reader not available"})
        return 1

    try:
        success = reader.write_card(
            card_type=card_type,
            room_number=0,
            date_time=date_time,
            sys_id=sys_id,
            first_name=' ',
            last_name=' ',
            gender='M',
            language='E',
        )

        if not success:
            emit({"ok": False, "message": "Failed to write card"})
            return 1

        card_name = "Maid" if card_type == 'H' else "Manager"
        emit({
            "ok": True,
            "message": f"{card_name} card programmed",
            "valid_until": f"{check_out_date} {check_out_time}",
            "sys_id": int(sys_id),
            "card_type": card_type,
        })
        return 0
    finally:
        reader.close()


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ''

    try:
        if action == 'check':
            code = handle_check()
        elif action == 'write_guest':
            code = handle_write_guest()
        elif action == 'write_staff':
            code = handle_write_staff_card()
        else:
            emit({"ok": False, "message": "Unknown action"})
            code = 1
    except Exception as exc:
        emit({"ok": False, "message": str(exc)})
        code = 1

    raise SystemExit(code)


if __name__ == '__main__':
    main()
