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


if __name__ == '__main__':
    assert len(vectors()) >= 20
    print('web.uart_vectors self-check OK')
