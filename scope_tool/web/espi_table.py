from __future__ import annotations

"""eSPI 命令長度與 CRC；依 Rev 0.75 XML，待實機驗證。"""
NAMES = {0:'PUT_PC', 1:'GET_PC', 2:'PUT_NP', 3:'GET_NP', 4:'PUT_VWIRE',
         5:'GET_VWIRE', 6:'PUT_OOB', 7:'GET_OOB', 8:'PUT_FLASH_C', 9:'GET_FLASH_NP',
         0x21:'GET_CONFIGURATION', 0x22:'SET_CONFIGURATION', 0x25:'GET_STATUS', 0xff:'RESET'}


def crc8(data: list[int] | bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ (0x07 if crc & 0x80 else 0)) & 0xff
    return crc


def command(data: list[int]) -> tuple[str, int | None]:
    if not data:
        return '', None
    op = data[0]
    if 0x40 <= op <= 0x4f:
        if op & 3 == 2:
            return '', None
        group = (op - 0x40) // 4
        name = ('PUT_IORD_SHORT', 'PUT_IOWR_SHORT', 'PUT_MEMRD32_SHORT', 'PUT_MEMWR32_SHORT')[group]
        return name, 2 + (2 if group < 2 else 4) + ((1, 2, 0, 4)[op & 3] if group & 1 else 0)
    name = NAMES.get(op, '')
    if op in (1, 3, 5, 7, 9, 0x25):
        return name, 2
    if op in (0x21, 0x22):
        return name, 4 if op == 0x21 else 8
    if op == 4:
        return name, 3 + 2 * ((data[1] & 63) + 1) if len(data) > 1 else None
    if op in (0, 2, 6, 8):
        if len(data) < 4:
            return name, None
        cycle, length = data[1], ((data[2] & 15) << 8) | data[3]
        if op == 6 and cycle == 0x21:
            return name, 5 + length
        if op == 8 and cycle in (6, 12, 14, 9, 11, 13, 15):
            return name, 5 + (length if cycle in (9, 11, 13, 15) else 0)
        if op in (0, 2):
            extra = {0:4, 1:4, 2:8, 3:8, 0x10:1, 0x11:1, 6:0, 12:0, 14:0, 9:0, 11:0, 13:0, 15:0}.get(cycle)
            if extra is not None:
                return name, 5 + extra + (length if cycle in (1, 3, 0x11, 9, 11, 13, 15) else 0)
        # ponytail: 未列出的 cycle 不猜測長度。
        return '', None
    return name, 2 if op == 0xff else None


if __name__ == '__main__':
    assert [crc8(x) for x in (b'123456789', bytes.fromhex('25'), bytes.fromhex('21 00 04'), bytes.fromhex('08 0F 03'))] == [0xf4, 0xfb, 0x34, 0x9b]
    assert command([0x40])[1] == 4 and command([0x47])[1] == 8 and command([0x42])[0] == ''
    print('web.espi_table self-check OK')
