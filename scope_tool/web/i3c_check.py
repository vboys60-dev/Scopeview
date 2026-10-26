from __future__ import annotations

"""P1 驗收入口：手寫 H1–H3、協定／品質向量、四個實際路徑變異。"""
import sys
import numpy as np
from scope_tool.web import i3c_decode as dec
from scope_tool.web.i3c_synth import Bus, render
from scope_tool.web.i3c_vectors import check_result, protocol_vectors, run
from scope_tool.web.i3c_quality import quality_vectors


def handwritten(number: int) -> tuple[dict, list, float, float]:
    """獨立逐 bit 轉換；字串為線上真值，不呼叫 Bus／byte／DAA helper。"""
    trans = [(0., 'scl', 1), (0., 'sda', 1)]
    levels = {'scl': 1, 'sda': 1}
    now = 1000
    stamps = []

    def change(line: str, value: int) -> None:
        if levels[line] != value:
            trans.append((now * 1e-9, line, value))
            levels[line] = value

    def wait(ns: int) -> None:
        nonlocal now
        now += ns

    def start(repeated: bool = False) -> None:
        if repeated:
            change('scl', 0)
            wait(20)
            change('sda', 1)
            wait(20)
            change('scl', 1)
            wait(40)
        change('sda', 0)
        wait(40)
        change('scl', 0)

    def word(bits: str, abort: bool = False) -> None:
        times = []
        for i, digit in enumerate(bits):
            change('scl', 0)
            wait(20)
            change('sda', int(digit))
            wait(20)
            change('scl', 1)
            times.append(now * 1e-9)
            wait(40)
            if abort and i == len(bits) - 1:
                change('sda', 0)
                wait(20)
            change('scl', 0)
        stamps.append(times)

    begin = now * 1e-9
    start()
    word('111111000')  # 7E/W、ACK。
    if number == 2:
        word('000001110')  # ENTDAA、奇同位。
        start(True)
        word('111111010')  # 7E/R、ACK。
        word('000000010010001101000101011001111000100110101011')
        word('00000110')
        word('01000100')
        word('000100000')  # DA=08、PAR=0、ACK=0。
        start(True)
        word('111111011')  # DAA 結束 NACK。
    else:
        start(True)
        word('000100000' if number == 1 else '000100010')
        if number == 1:
            word('101001011')  # A5、T=1。
        else:
            word('001100001')  # 30、T=1。
            word('001100011', abort=True)  # 31、T=1，再由 Controller 拉低。
    change('scl', 0)
    wait(20)
    change('sda', 0)
    wait(20)
    change('scl', 1)
    wait(40)
    change('sda', 1)
    stop = now * 1e-9
    wait(200)
    waves = render(trans, 1e9, noise=0, tr=0, end=now * 1e-9)
    r = check_result(dec.decode_waveforms(*waves))
    return r, stamps, begin, stamps[-1][-1] + 40e-9 if number == 3 else stop


def hand_vectors() -> list[str]:
    for number in (1, 2, 3):
        r, stamps, begin, stop = handwritten(number)
        assert len(r['frames']) == 1
        f = r['frames'][0]
        common = ('addr', 252, 9, 0, 'ack', True)
        if number == 1:
            expected = [common, ('addr', 16, 9, 0, 'ack', True), ('data', 165, 9, 1, 'parity', True)]
            assert (f['kind'], f['start'], f['addr'], f['rw'], f['ack'], f['ccc'], f['ccc_name'], f['status'], f['reasons']) == (
                'private_write', 'S', 8, 0, True, None, None, 'ok', ['type_unknown'])
        elif number == 2:
            expected = [common, ('ccc', 7, 9, 0, 'parity', True), ('addr', 253, 9, 0, 'ack', True),
                        ('pid', 0x0123456789AB, 48, None, None, True), ('bcr', 6, 8, None, None, True),
                        ('dcr', 0x44, 8, None, None, True), ('da', 8, 9, 0, 'parity', True),
                        ('addr', 253, 9, 1, 'ack', True)]
            assert (f['kind'], f['start'], f['addr'], f['rw'], f['ack'], f['ccc'], f['ccc_name'], f['status'], f['reasons']) == (
                'daa', 'S', 126, 0, True, 7, 'ENTDAA', 'ok', [])
            assert [(a['da'], a['pid'], a['bcr'], a['dcr'], a['how']) for a in r['addresses']] == [(8, 0x0123456789AB, 6, 0x44, 'ENTDAA')]
        else:
            expected = [common, ('addr', 17, 9, 0, 'ack', True), ('data', 0x30, 9, 1, 'tbit', True), ('data', 0x31, 9, 1, 'tbit', True)]
            assert (f['kind'], f['start'], f['addr'], f['rw'], f['ack'], f['ccc'], f['ccc_name'], f['status'], f['reasons']) == (
                'private_read', 'S', 8, 1, True, None, None, 'ok', ['type_unknown'])
            assert 'Controller 提前結束' in f['label']
        actual = [(x['kind'], x['value'], x['nbits'], x['ninth'], x['ninth_kind'], x['ok']) for x in f['fields']]
        assert actual == expected, (number, actual)
        assert abs(f['t0'] - begin) <= 2e-9 and abs(f['t1'] - stop) <= 2e-9
        for x, times in zip(f['fields'], stamps):
            assert abs(x['t0'] - times[0]) <= 2e-9 and abs(x['t1'] - times[-1]) <= 2e-9
    return ['H1', 'H2', 'H3']


def pattern_counterexample() -> None:
    r = run(Bus().target_reset())
    assert [f['kind'] for f in r['frames']] == ['target_reset']


def mutations() -> None:
    hand_vectors()
    pattern_counterexample()
    changes = [('奇同位改偶同位', 'parity_ok', lambda v, t: (v.bit_count() + t) % 2 == 0),
               ('DA PAR 取反', 'da_par', lambda da: da.bit_count() & 1),
               ('k≥4 即 Exit', 'classify_pattern', lambda high, k, n, end: 'hdr_exit' if k >= 4 else 'pattern'),
               ('T 視窗忽略下降', 'read_t_end', lambda t, fell, rose: 'stop' if t == 0 and rose else None)]
    for label, name, replacement in changes:
        old = getattr(dec, name)
        setattr(dec, name, replacement)
        failed = []
        try:
            for test in (hand_vectors, pattern_counterexample):
                try:
                    test()
                except AssertionError:
                    failed.append(test.__name__)
        finally:
            setattr(dec, name, old)
        assert failed, f'變異未被測試抓到：{label}'
        print(f'變異 {label}: 已偵測（{", ".join(failed)} 失敗）')
    print('web.i3c_check mutations self-check OK')


if __name__ == '__main__':
    if '--mutations' in sys.argv:
        mutations()
    else:
        passed = hand_vectors() + protocol_vectors() + quality_vectors()
        required = {'H1', 'H2', 'H3', '22b', '22c', '22d'} | {str(i) for i in range(1, 41)}
        assert set(passed) == required
        print('通過向量: ' + ', '.join(passed))
        print('web.i3c_check self-check OK')
