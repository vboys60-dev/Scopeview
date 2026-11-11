from __future__ import annotations

"""CAN FD 手寫位元參考與待解碼器到位後執行的驗收。"""
import sys
import numpy as np
from scope_tool.web import logic, can_decode
from scope_tool.web.can_synth import can_frame, fd_bus, fd_frame, render
from scope_tool.web.can_check import invariants

# 手寫欄位：SOF、ID 123、RRS/IDE/FDF/res、BRS/ESI、DLC 1、資料 A5。
RAW = '0' + '00100100011' + '0010' + '00' + '0001' + '10100101'
# 手寫動態填充後；DATA 結尾無額外動態填充位。
DYNAMIC = '0001001000110010000010110100101'
SBC = '0011'
CRC = '00111101010111001'
WIRE = DYNAMIC + '0' + SBC + '0' + CRC[:4] + '0' + CRC[4:8] + '0' + CRC[8:12] + '0' + CRC[12:16] + '1' + CRC[16:] + '1011111111'


def independent_crc(data: str, width: int, initial: int | None = None) -> int:
    """以多項式長除法獨立計算，初值先作用於訊息最高位。"""
    init = (1 << (width - 1)) if initial is None else initial
    value = (int(data, 2) << width) ^ (init << len(data))
    poly = (1 << width) | (0x3685b if width == 17 else 0x302899)
    while value.bit_length() > width:
        value ^= poly << (value.bit_length() - width - 1)
    return value


def references() -> None:
    assert RAW == '000100100011001000000110100101'
    assert independent_crc(DYNAMIC + SBC, 17) == int(CRC, 2) == 0x7ab9
    f = fd_frame(0x123, [0xa5], dlc=1)
    assert ''.join(map(str, f['bits'])) == WIRE
    assert f['stuff_count'] == 1 and f['sbc'] == [0, 0, 1, 1]
    assert len(f['fsb']) == 6
    assert independent_crc(DYNAMIC + SBC, 17, 0) != int(CRC, 2)
    assert independent_crc(WIRE[:58], 17) != int(CRC, 2)
    for dlc, length in [(8, 8), (9, 12), (15, 64)]:
        for brs in (False, True):
            f = fd_frame(0x123, bytes(range(length)), dlc=dlc, brs=brs)
            assert len(f['fsb']) == (6 if length <= 16 else 7)
            assert (f['brs'] is not None) == brs
    print('手寫位串與獨立 CRC：OK')


def decode(frame: dict | list[int], *, data_bitrate: float | None = 2000000) -> dict:
    bus = fd_bus([frame])
    t, v = render(bus, fs=32000000)
    edges, _, end, error = logic.prepare(t, {'can': v}, {'can': None}, require_edges=True)
    assert error is None, error
    opts = {'bitrate': 500000, 'dominant_high': True}
    if data_bitrate is not None:
        opts.update(data_bitrate=data_bitrate, data_sample_point=75)
    result = can_decode.run(edges, t1=end, **opts)
    invariants(result)
    return result


def vectors() -> None:
    hand = [int(x) for x in WIRE]
    f = decode(hand)['frames'][0]
    assert f['kind'] == 'fd' and f['addr'] == 0x123 and not f['reasons']
    assert [x['value'] for x in f['fields'] if x['kind'] == 'data'] == [0xa5]
    assert next(x for x in f['fields'] if x['kind'] == 'crc')['value'] == 0x7ab9
    assert any(x['kind'] == 'sbc' for x in f['fields'])
    for data in (b'\x1f', b'\xe0', bytes(8)):  # DATA 末 5 同值、全 0（stuff count 跨 mod 8）
        for brs in (False, True):
            g = decode(fd_frame(0x123, data, dlc=len(data), brs=brs))['frames'][0]
            assert g['kind'] == 'fd' and not g['reasons'], (data, brs, g['reasons'])
    for dlc, length in [(8, 8), (9, 12), (15, 64)]:
        for brs in (False, True):
            data = bytes(range(length))
            f = decode(fd_frame(0x123, data, dlc=dlc, brs=brs))['frames'][0]
            assert f['kind'] == 'fd' and not f['reasons']
            assert [x['value'] for x in f['fields'] if x['kind'] == 'data'] == list(data)
    f = fd_frame(0x123, [0xa5], dlc=1)
    assert 'fd_unsupported' in decode(f, data_bitrate=None)['frames'][0]['reasons']
    for index, reason in [(f['fsb'][0], 'form'), (f['fsb'][0] + 1, 'stuff_count')]:
        bad = dict(f, bits=f['bits'].copy())
        bad['bits'][index] ^= 1
        assert reason in decode(bad)['frames'][0]['reasons']
    bus = fd_bus([can_frame(0x123, [0x12]), f])
    t, v = render(bus, fs=32000000)
    edges, _, end, err = logic.prepare(t, {'can': v}, {'can': None}, require_edges=True)
    assert err is None
    result = can_decode.run(edges, t1=end, bitrate=500000, data_bitrate=2000000, data_sample_point=75)
    invariants(result)
    assert [x['kind'] for x in result['frames']] == ['data', 'fd']
    print('FD 解碼向量與混排：OK')


def mutations() -> None:
    """改壞解碼器本身（monkeypatch），各自必須讓 vectors() 失敗。"""
    from scope_tool.web import can_fd, can_fields
    orig = (can_fd.gray_sbc, can_fd.crc_fd, can_fields.Reader.rebase)

    def crc_init0(bits, n):
        crc, mask = 0, (1 << n) - 1
        for x in bits:
            top = ((crc >> (n - 1)) ^ x) & 1
            crc = (crc << 1) & mask
            if top:
                crc ^= can_fd.POLY[n] & mask
        return crc

    def binary(n):
        v = n % 8
        b = [(v >> 2) & 1, (v >> 1) & 1, v & 1]
        return b + [b[0] ^ b[1] ^ b[2]]

    def shifted(self, t, T, sp):
        orig[2](self, t + .3 * self.T, T, sp)

    cases = {'SBC 用二進位': ('gray_sbc', binary), 'CRC 初值為 0': ('crc_fd', crc_init0)}
    for name, (attr, fn) in cases.items():
        setattr(can_fd, attr, fn)
        try:
            vectors()
        except Exception:
            print(f'變異已抓到：{name}')
        else:
            raise AssertionError(f'變異未被抓到：{name}')
        finally:
            can_fd.gray_sbc, can_fd.crc_fd = orig[0], orig[1]
    can_fields.Reader.rebase = shifted
    try:
        vectors()
    except Exception:
        print('變異已抓到：BRS 切換點偏離')
    else:
        raise AssertionError('變異未被抓到：BRS 切換點偏離')
    finally:
        can_fields.Reader.rebase = orig[2]
    # ponytail: 「DATA 末尾 5 同值多插動態填充位」變異需改 Reader 內部，未做；向量 0x1F／0xE0 已覆蓋正確行為。


if __name__ == '__main__':
    references()
    if '--legacy' in sys.argv:
        assert 'fd_unsupported' in decode(fd_frame(0x123, [0xa5], dlc=1), data_bitrate=None)['frames'][0]['reasons']
    elif '--references' not in sys.argv:
        vectors()
        if '--mutations' in sys.argv:
            mutations()
    print('web.can_fd_check self-check OK')
