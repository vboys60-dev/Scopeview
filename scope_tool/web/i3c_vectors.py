from __future__ import annotations

"""計畫 §7.2 的協定向量 1–27；合成器真值與輸出分開核對。"""
import numpy as np
from scope_tool.web.i3c_synth import Bus
from scope_tool.web import i3c_decode as dec


def check_result(r: dict) -> dict:
    assert r['ok'], r.get('reason')
    frames = r['frames']
    assert all(a['t1'] <= b['t0'] for a, b in zip(frames, frames[1:]))
    assert np.all(np.diff(r['bits_t']) > 0)
    for i, f in enumerate(frames):
        assert f['i'] == i and f['t0'] <= f['t1']
        assert f['status'] in ('ok', 'warn', 'error')
        for x in f['fields']:
            assert f['t0'] <= x['t0'] <= x['t1'] <= f['t1']
            assert x['nbits'] >= 1 and isinstance(x['ok'], bool)
            ix = (r['bits_t'] >= x['t0']) & (r['bits_t'] <= x['t1'])
            assert ix.sum() == x['nbits'], (x, ix.sum())
            if x['kind'] != 'da':
                bits = r['bits_v'][ix]
                data = bits[:-1] if x['ninth_kind'] else bits
                assert x['value'] == int(''.join(str(int(v)) for v in data), 2)
                if x['ninth_kind']:
                    assert x['ninth'] == bits[-1]
    return r


def run(b: Bus, **options: object) -> dict:
    r = check_result(dec.decode_waveforms(*b.render(noise=0), **options))
    expected = []
    legacy = any(x[0] == 'i2c' for x in b.truth)
    for x in b.truth:
        if x[0] == 'header':
            expected.append((x[1], x[5], (x[2] << 1) | x[3], 0 if x[4] else 1, 'ack'))
        elif x[0] in ('write', 'read'):
            expected.append((x[1], x[4], x[2], x[3], 'parity' if x[0] == 'write' else 'tbit'))
    actual = [x for f in r['frames'] for x in f['fields'] if x['kind'] not in ('pid', 'bcr', 'dcr', 'da') and not x['kind'].startswith('hdr_')]
    if legacy:
        actual = [x for x in actual if x['kind'] == 'addr']
    if not r['truncated']:
        assert len(actual) == len(expected), (len(actual), len(expected))
    for f, (t0, t1, v, ninth, nk) in zip(actual, expected):
        assert (f['value'], f['ninth'], f['ninth_kind'], f['nbits']) == (v, ninth, nk, 9)
        assert abs(f['t0'] - t0) <= 2e-9 and abs(f['t1'] - t1) <= 2e-9
    # 每個取樣 bit 必須對應符號層真正的 SCL 上升，誤差不超過兩點。
    rises = np.array([tm for tm, ln, v in b.trans if ln == 'scl' and v == 1])
    bt = r['bits_t']  # HDR 區段的位元取在 SCL 兩個邊沿，不在此檢查範圍
    for f in r['frames']:
        if f['kind'] == 'hdr':
            bt = bt[(bt < f['t0']) | (bt > f['t1'])]
    ix = np.searchsorted(rises, bt)
    ix = np.minimum(ix, len(rises) - 1)
    dist = np.minimum(abs(rises[ix] - bt), abs(rises[np.maximum(ix - 1, 0)] - bt))
    assert np.all(dist <= 2e-9)
    return r


def private(data: tuple = (0xA5, 0x11, 0xF0), bad: bool = False) -> Bus:
    b = Bus().start().header(0x7E, od=True).rstart().header(8)
    for i, v in enumerate(data):
        b.byte_w(v, (v.bit_count() & 1) if bad and i == 1 else None)
    return b.stop()


def reader(ts: tuple = (1, 1, 0), abort: bool = False) -> Bus:
    b = Bus().start().header(0x7E, od=True).rstart().header(8, 1)
    for i, t in enumerate(ts):
        b.byte_r(0x30 + i, t, abort=abort and i == len(ts) - 1)
    if abort:
        b.header(9).byte_w(0x54)
    return b.stop()


def protocol_vectors() -> list[str]:
    passed = []
    f = run(private())['frames'][0]
    assert (f['kind'], f['start'], f['addr'], f['rw'], f['ack'], f['ccc'], f['status']) == ('private_write', 'S', 8, 0, True, None, 'ok')
    assert f['fields'][0]['label'] == '7E 開場'
    assert [x['value'] for x in f['fields']] == [252, 16, 165, 17, 240]
    passed.append('1')
    f = run(private(bad=True))['frames'][0]
    assert f['status'] == 'error' and f['reasons'] == ['type_unknown', 'parity']
    assert [x['ok'] for x in f['fields']] == [True, True, True, False, True]
    passed.append('2')
    f = run(reader())['frames'][0]
    assert f['kind'] == 'private_read' and f['status'] == 'ok'
    assert [x['ninth'] for x in f['fields'][2:]] == [1, 1, 0]
    passed.append('3')
    fs = run(reader((1, 1), True))['frames']
    assert len(fs) == 2 and 'Controller 提前結束' in fs[0]['label']
    assert fs[1]['addr'] == 9 and fs[1]['fields'][-1]['value'] == 0x54
    assert fs[1]['start'] == 'Sr' and fs[0]['status'] == 'ok'
    passed.append('4')
    # 去掉 STOP 從 T=0 之後繼續送八個時脈。
    b = Bus().start().header(0x7E, od=True).rstart().header(8, 1).byte_r(1, 0).word(0xFF).stop()
    f = run(b)['frames'][0]
    assert 't_bit' in f['reasons'] and f['status'] == 'error'
    passed.append('5')
    f = run(Bus().start().header(8, ack=False).stop())['frames'][0]
    assert f['ack'] is False and f['status'] == 'warn' and 'nack' in f['reasons']
    passed.append('6')
    b = Bus().entdaa([(1, 6, 4)]).ccc(0, payload=(7,)).ccc(6).ccc(9, payload=(1, 2)).ccc(9, payload=(1,))
    r = run(b)
    assert [f['ccc_name'] for f in r['frames'][1:]] == ['ENEC', 'RSTDAA', 'SETMWL', 'SETMWL']
    assert r['addresses'][0]['t_to'] is not None
    assert 'SETMWL=258' in r['frames'][-2]['fields'][-2]['label']
    assert 'ccc_format' in r['frames'][-1]['reasons']
    passed.append('7')
    b = Bus().ccc(0x8D, targets=((8, 1, True, (1, 2, 3, 4, 5, 6)), (9, 1, False, ())))
    b.ccc(0x8E, targets=((8, 1, True, (6,)),)).ccc(0x8F, targets=((8, 1, True, (0x44,)),))
    r = run(b)
    assert [(x['value'], x['ninth'], x['addr']) for x in r['frames'][0]['fields'] if x['kind'] == 'addr'] == [(252, 0, None), (17, 0, 8), (19, 1, 9)]
    assert (r['addresses'][0]['pid'], r['addresses'][0]['bcr'], r['addresses'][0]['dcr']) == (0x010203040506, 6, 0x44)
    passed.append('8')
    b = Bus().ccc(0x9A, 1, targets=((8, 0, True, ()),)).ccc(0x9A, targets=((8, 0, True, ()),))
    b.ccc(0x8E, 1, targets=((8, 1, True, (6,)),))
    fs = run(b)['frames']
    assert fs[0]['status'] == 'ok' and fs[0]['fields'][2]['kind'] == 'def'
    assert fs[0]['fields'][2]['label'] == '周邊重設'
    assert all('ccc_format' in f['reasons'] for f in fs[1:])
    passed.append('9')
    b = Bus().ccc(0x87, targets=((0x50, 0, True, (0x10,)),)).ccc(0x88, targets=((8, 0, True, (0x12,)),))
    b.ccc(0x87, targets=((0x51, 0, True, (0x11,)),))
    r = run(b)
    assert [(a['da'], a['how']) for a in r['addresses']] == [(8, 'SETDASA'), (9, 'SETNEWDA')]
    assert r['addresses'][0]['t_to'] == r['addresses'][1]['t_from']
    assert r['addresses'][1]['static'] == 0x50 and 'ccc_format' in r['frames'][-1]['reasons']
    passed.append('10')
    f = run(Bus().ccc(0x86, targets=((8, 0, True, ()),)))['frames'][0]
    assert 'ccc_invalid' in f['reasons'] and f['status'] == 'warn'
    passed.append('11')
    f = run(Bus().ccc(0x5A, payload=(1, 2)))['frames'][0]
    assert f['ccc_name'] is None and 'ccc_unknown' in f['reasons'] and f['label'] == 'CCC 0x5A'
    assert [x['value'] for x in f['fields'][-2:]] == [1, 2]
    passed.append('12')
    for targets in [[(0x800000000001, 6, 2), (0x0123456789AB, 2, 4)], [(1, 3, 0x01), (1, 2, 0xFE)]]:
        b = Bus().entdaa(targets)
        r = run(b)
        expected = sorted(targets)
        assert [(a['pid'], a['bcr'], a['dcr']) for a in r['addresses']] == expected
        f = r['frames'][0]
        assert f['status'] == 'ok' and not f['reasons'] and f['label'] == 'DAA 結束'
        assert [x[1:4] for x in b.truth if x[0] == 'winner'] == expected
    passed.append('13')
    r = run(Bus().entdaa([(1, 6, 4)], bad_parity=True))
    assert not r['addresses'] and 'addr_parity' in r['frames'][0]['reasons']
    assert r['frames'][0]['status'] == 'error'
    passed.append('14')
    for bcr, payload, kinds in [(6, (0x81, 1, 2), ['addr', 'mdb', 'data', 'data']), (2, (), ['addr']),
                                 (6, (0x81,), ['addr', 'mdb']), (2, (0x81,), ['addr', 'data'])]:
        r = run(Bus().entdaa([(1, bcr, 4)]).ibi(8, payload))
        assert [x['kind'] for x in r['frames'][-1]['fields']] == kinds
        assert r['frames'][-1]['kind'] == 'ibi'
        if bcr == 2 and payload:
            assert 'ibi_unexpected_payload' in r['frames'][-1]['reasons']
    passed.extend(['15', '16', '17'])
    f = run(Bus().ibi(8, (0x81,)))['frames'][0]
    assert f['fields'][1]['kind'] == 'data' and 'BCR 未知' in f['fields'][1]['label']
    passed.append('18')
    f = run(Bus().ibi(8, ack=False))['frames'][0]
    assert f['ack'] is False and f['status'] == 'warn' and 'nack' in f['reasons']
    passed.append('19')
    for ack, targets in [(True, [(1, 6, 4)]), (False, [(1, 6, 4)]), (True, [(1, 6, 4), (2, 2, 3)])]:
        r = run(Bus().hotjoin(ack).entdaa(targets))
        assert [f['kind'] for f in r['frames']] == ['hotjoin', 'daa']
        assert len(r['addresses']) == len(targets) and all(a['da'] != 2 for a in r['addresses'])
    passed.append('20')
    fs = run(Bus().hdr(mode=1))['frames']  # TSP 不解；DDR 見 i3c_hdr_check
    assert [f['kind'] for f in fs] == ['ccc_broadcast', 'hdr', 'hdr_exit']
    assert fs[1]['t1'] == fs[2]['t0'] and not fs[1]['fields']
    passed.append('21')
    r = run(Bus().entdaa([(1, 6, 4)]).target_reset())
    assert [f['kind'] for f in r['frames']] == ['daa', 'target_reset']
    assert r['addresses'][0]['t_to'] == r['frames'][1]['t1'] and '有效性未知' in r['addresses'][0]['note']
    passed.append('22')
    b = Bus().start().header(8).byte_w(1).target_reset()
    fs = run(b)['frames']
    assert fs[-1]['kind'] == 'target_reset' and fs[-1]['status'] == 'ok'
    assert fs[0]['kind'] == 'private_write' and 'truncated' in fs[0]['reasons']
    passed.extend(['22b', '22d'])
    f = run(Bus().pattern(8))['frames'][0]
    assert f['kind'] == 'pattern' and 'pattern_unknown' in f['reasons']
    passed.append('22c')
    for b in [Bus().target_reset(sr=False), Bus().target_reset(stop=False), Bus().pattern(9, raise_scl=False)]:
        f = run(b)['frames'][-1]
        assert 'pattern_incomplete' in f['reasons']
    passed.append('23')
    f = run(Bus().hdr_exit())['frames'][0]
    assert f['kind'] == 'hdr_exit' and '未見 ENTHDR' in f['label']
    f = run(Bus().pattern(5))['frames'][0]
    assert f['kind'] == 'pattern' and 'pattern_unknown' in f['reasons']
    passed.append('24')
    b = Bus().i2c(0x50, 0, (0, 0xA5), (True, True)).i2c(0x50, 1, (1, 2, 3), (True, True, False))
    fs = run(b, i2c_addrs={0x50})['frames']
    assert [f['kind'] for f in fs] == ['i2c', 'i2c'] and all(f['status'] == 'ok' for f in fs)
    assert [x['ninth'] for x in fs[1]['fields'][1:]] == [0, 0, 1]
    passed.append('25')
    fs = run(b)['frames']
    assert fs[0]['kind'] == 'private_write' and 'parity' in fs[0]['reasons']
    assert all('type_unknown' in f['reasons'] for f in fs)
    passed.append('26')
    b = Bus().start().header(8).byte_w(0, 0).stop().start().header(8).byte_w(0, 0).stop()
    r = run(b)
    assert all(set(f['reasons']) == {'type_unknown', 'parity'} for f in r['frames'])
    assert r['addresses'][0]['t_from'] is None and r['addresses'][0]['how'] == 'observed'
    passed.append('27')
    return passed


if __name__ == '__main__':
    print('向量', ','.join(protocol_vectors()))
    print('web.i3c_vectors self-check OK')
