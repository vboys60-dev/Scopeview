from __future__ import annotations

"""UART 獨立預期值；各組可直接在符號層或類比層驗收。"""
from scope_tool.web.uart_synth import uart_line


def raw(trans: list[tuple], end: float) -> dict:
    return dict(trans=[(float(t) / 9600, v) for t, v in trans], end=end / 9600, truth=[])


def prefixed(line: dict) -> dict:
    first = uart_line([0x55])
    return dict(trans=first['trans'] + [(t + 12 / 9600, v) for t, v in line['trans']],
                end=line['end'] + 12 / 9600, truth=[])


def vectors() -> list[tuple]:
    result = []
    def add(name: str, line: dict, values: list, codes: tuple = (), **opts: object) -> None:
        result.append((name, line, dict(baud=9600, **opts), values, set(codes)))
    add('U01', uart_line([0x55]), [0x55])
    add('U02', uart_line([0x41], parity='E'), [0x41], parity='E')
    add('U03', uart_line([0x41], parity='E'), [0x41], ('parity',), parity='O')
    b = prefixed(raw([(0, 1), (2, 0), (3, 1), (4, 0), (9, 1), (10, 0), (12, 1)], 15))
    add('U04', b, [0x55, 0x41], ('framing',))
    add('U04/HUNT', raw([(0, 1), (2, 0), (3, 1), (4, 0), (9, 1), (10, 0), (12, 1)], 15), [], ('unsynced',))
    add('U05', uart_line([0x41], breaks=((0, 12, 2),)), [None, 0x41], ('break',))
    add('U06', raw([(0, 1), (2, 0), (2.192, 1)], 5), [])
    add('false start 0.3T', raw([(0, 1), (2, 0), (2.3, 1), (4, 0), (5, 1), (6, 0), (11, 1), (12, 0), (13, 1)], 16), [0x41])
    add('U07a', raw([(0, 1), (1, 0), (2, 1), (3, 0), (8, 1), (9, 0), (10, 1)], 13), [0x41])
    # 起點低只標未同步；後面的 mark 足夠，下一字元可恢復。
    add('U07b', raw([(0, 0), (3, 1), (4, 0), (5, 1), (6, 0), (11, 1), (12, 0), (13, 1)], 16), [0x41], ('unsynced',))
    b = uart_line([0x41]); b['end'] = 6.2 / 9600
    add('U08', b, [None], ('truncated', 'unknown_bit'))
    b = prefixed(raw([(0, 1), (2, 0), (3, 1), (4, 0), (9, 1),
                      (10, 0), (11, 1), (11.3, 0), (12, 1)], 15))
    add('U09', b, [0x55, 0x41], ('framing', 'short_stop'))
    b = uart_line([0x55, 0x41], stop=2)
    b['trans'].extend([(23 / 9600, 0), (24 / 9600, 1)])
    b['trans'].sort()
    add('U10', b, [0x55, 0x41], ('framing',), stop=2)
    add('U11', uart_line([0x1F], bits=5), [0x1F], bits=5)
    add('U12', uart_line([0x1A5], bits=9), [0x1A5], bits=9)
    add('U13/U15', uart_line([0x41], idle_level=0), [0x41], invert=True)
    add('U14', uart_line([0x55] * 8, idle_level=0), [0x55] * 8, ('unsynced', 'framing'))
    add('U20', uart_line([0x55] * 8, eps=.04), [0x55] * 8)
    # 先同步一字元，再注入時脈誤差；只檢查第一個漂移字元。
    for name, eps in (('U21', .06), ('U22', -.06)):
        b = uart_line([0x55] * 8, eps=eps)
        add(name, prefixed(b), [0x55, 0xD5], ('framing', 'short_stop') if eps > 0 else ('framing',))
        add(name + '/HUNT', b, [], ('unsynced',))
    add('U27', prefixed(raw([(0, 1), (2, 0), (11.8, 1)], 15)),
        [0x55, 0], ('framing',))
    add('U28', uart_line([0x41], breaks=((0, 12, 1),)), [None, 0x41], ('break',))
    add('U29開放', raw([(0, 1), (2, 0)], 14), [None], ('break', 'truncated'))
    add('U29短', raw([(0, 1), (2, 0)], 7), [None], ('truncated', 'unknown_bit'))
    return result


def differential_checks(mutation: bool = False) -> None:
    """以實際 CSV 與共用解碼入口驗差動、極性與三態。"""
    import tempfile
    from pathlib import Path
    import numpy as np
    from scope_tool.web import uart_decode as dec
    from scope_tool.web.analysis_api import Analysis
    from scope_tool.web.synth import write_csv
    from scope_tool.web.uart_synth import differential, render

    line = uart_line([0x55] * 8, gaps=[4] + [0] * 7)
    t, pos, neg = differential(line, vcm=9.5)
    _, single = render(line, levels=(-2., 2.))
    start = line['truth'][0]['start'] + 10 / 9600
    stop = start + 3 / 9600
    _, tri_pos, tri_neg = differential(line, vcm=9.5, tristate=((start, stop),))
    assert np.all(tri_pos[(t >= start) & (t < stop)] == 9.5)
    assert np.all(tri_neg[(t >= start) & (t < stop)] == 9.5)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / '差動_20261112_000000.csv'
        write_csv(path, (t, pos, neg, single, tri_pos, tri_neg))
        api = Analysis()
        api.open_waveform(str(path))
        def decode(channels: dict, invert: bool = False, thresholds: dict | None = None) -> tuple:
            th = thresholds if thresholds is not None else {'tx': [-.2, .2]}
            result = api.decode('uart', channels, th, {'baud': 9600, 'invert': invert})
            return result, api.decode_frames(result['decode_id'])['frames'] if result['ok'] else []
        base, expected = decode({'tx': 'CHAN3'})
        assert base['ok'] and [x['value'] for f in expected for x in f['fields']] == [0x55] * 8
        if mutation:
            old = dec.DIFF
            try:
                dec.DIFF = {}
                result, actual = decode({'tx': 'CHAN1', 'tx_n': 'CHAN2'},
                                        thresholds={'tx': [-.2, .2], 'tx_n': [-.2, .2]})
                assert result['ok'] and actual == expected
            finally:
                dec.DIFF = old
            return
        result, actual = decode({'tx': 'CHAN1', 'tx_n': 'CHAN2'})
        assert result['ok'] and actual == expected and set(result['thresholds']) == {'tx'}
        auto, auto_frames = decode({'tx': 'CHAN1', 'tx_n': 'CHAN2'}, thresholds={'tx': None})
        assert auto['ok'] and [x['value'] for f in auto_frames for x in f['fields']] == [0x55] * 8
        wrong, _ = decode({'tx': 'CHAN2', 'tx_n': 'CHAN1'})
        assert any('可能需切換反相' in w for w in wrong['warnings'])
        corrected, actual = decode({'tx': 'CHAN2', 'tx_n': 'CHAN1'}, invert=True)
        assert corrected['ok'] and actual == expected
        tri, actual = decode({'tx': 'CHAN4', 'tx_n': 'CHAN5'})
        assert tri['ok'] and actual == expected
        for channels in ({'tx_n': 'CHAN2'}, {'tx': 'CHAN1', 'rx_n': 'CHAN2'}):
            try:
                dec.options({'baud': 9600}, channels)
            except ValueError:
                pass
            else:
                raise AssertionError(channels)
    print('RS-485 V1–V4／CSV／門檻／負端驗證：OK')


if __name__ == '__main__':
    assert len(vectors()) >= 20
    print('web.uart_vectors self-check OK')
