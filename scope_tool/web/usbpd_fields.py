from __future__ import annotations

"""USB PD 4b5b、ordered set 與 R3.1 訊息列舉；待實機驗證。"""

DATA_CODES = (0b11110, 0b01001, 0b10100, 0b10101, 0b01010, 0b01011,
              0b01110, 0b01111, 0b10010, 0b10011, 0b10110, 0b10111,
              0b11010, 0b11011, 0b11100, 0b11101)
S1, S2, S3, R1, R2, EOP = 0b11000, 0b10001, 0b00110, 0b00111, 0b11001, 0b01101
ORDERED = {(S1, S1, S1, S2): 'SOP', (S1, S1, S3, S3): "SOP'",
           (S1, S3, S1, S3): "SOP''", (R1, R1, R1, R2): 'Hard Reset',
           (R1, S1, R1, S3): 'Cable Reset', (S1, R2, R2, S3): "SOP'_Debug",
           (S1, R2, S3, S2): "SOP''_Debug"}
CONTROL = {i: name for i, name in enumerate((
    'Reserved_0', 'GoodCRC', 'GotoMin', 'Accept', 'Reject', 'Ping', 'PS_RDY',
    'Get_Source_Cap', 'Get_Sink_Cap', 'DR_Swap', 'PR_Swap', 'VCONN_Swap',
    'Wait', 'Soft Reset'))}
CONTROL.update({i: name for i, name in enumerate((
    'Not_Supported', 'Get_Source_Cap_Extended', 'Get_Status', 'FR_Swap',
    'Get_PPS_Status', 'Get_Country_Codes'), 16)})
DATA = {i: name for i, name in enumerate((
    'Reserved_0', 'Source_Capabilities', 'Request', 'BIST', 'Sink_Capabilities',
    'Battery_Status', 'Alert', 'Get_Country_Info', 'Enter_USB', 'EPR_Request',
    'EPR_Mode', 'Source_Info', 'Revision'))}
DATA[15] = 'Vendor_Defined'
EXTENDED = {i: name for i, name in enumerate((
    'Reserved_0', 'Source_Capabilities_Extended', 'Status', 'Get_Battery_Cap',
    'Get_Battery_Status', 'Battery_Capabilities', 'Get_Manufacturer_Info',
    'Manufacturer_Info', 'Security_Request', 'Security_Response',
    'Firmware_Update_Request', 'Firmware_Update_Response', 'PPS_Status',
    'Country_Info', 'Country_Codes', 'Sink_Capabilities_Extended',
    'Extended_Control', 'EPR_Source_Capabilities', 'EPR_Sink_Capabilities'))}
EXTENDED[30] = 'Vendor_Defined_Extended'


def header(value: int) -> dict:
    """拆解 16 位標頭並保留 XML 的訊息名稱。"""
    count, extended, typ = (value >> 12) & 7, bool(value & 0x8000), value & 31
    kind = 'extended' if extended else 'data' if count else 'control'
    names = EXTENDED if extended else DATA if count else CONTROL
    return dict(kind=kind, type=typ, name=names.get(typ, 'Reserved'),
                data_role=(value >> 5) & 1, spec_rev=(value >> 6) & 3,
                power_role=(value >> 8) & 1, message_id=(value >> 9) & 7,
                count=count, extended=extended)


if __name__ == '__main__':
    assert len(set(DATA_CODES)) == 16 and len(ORDERED) == 7
    assert header(0x0141)['name'] == 'GoodCRC'
    assert header(0x1001)['name'] == 'Source_Capabilities'
    print('web.usbpd_fields self-check OK')
