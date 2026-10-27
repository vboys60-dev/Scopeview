from __future__ import annotations

"""合成協定向量與獨立列舉真值；不以解碼器推導預期結果。"""
from scope_tool.web.i2c_synth import Bus


def expected(kind: str, addr: int | None, rw: int | None, values: list[int], *,
             acks: tuple = (), start: str = 'S', reasons: tuple = (), status: str = 'ok',
             low: bool = False, labels: dict | None = None, bad: tuple = ()) -> dict:
    acks = acks or (True,) * len(values)
    fields = [('addr_lo' if low and i == 1 else 'addr' if i == 0 else 'data',
               v, 9, int(not ack), 'ack', i not in bad)
              for i, (v, ack) in enumerate(zip(values, acks))]
    return dict(kind=kind, addr=addr, rw=rw, ack=acks[0] if acks else None, start=start,
                status=status, reasons=list(reasons), fields=fields, labels=labels or {})


def vectors() -> list[tuple[str, Bus, list[dict]]]:
    e, result = expected, []
    def add(name: str, bus: Bus, *frames: dict) -> None:
        result.append((name, bus, list(frames)))
    add('T01/T32', Bus().start().byte(0xA0).byte(0x12).byte(0x34).stop(),
        e('write', 0x50, 0, [0xA0, 0x12, 0x34]))
    for name, write, read in (('T02', 0, 0xAB), ('T05', 0x12, 0x34)):
        add(name, Bus().start().byte(0xA0).byte(write).rstart().byte(0xA1).byte(read, False).stop(),
            e('write', 0x50, 0, [0xA0, write]),
            e('read', 0x50, 1, [0xA1, read], acks=(True, False), start='Sr'))
    add('T03', Bus().start().byte(0xD0, False).stop(),
        e('write', 0x68, 0, [0xD0], acks=(False,), reasons=('nack',), status='warn', bad=(0,)))
    add('T04', Bus().start().byte(0xA0).byte(0x10, False).byte(0x22).stop(),
        e('write', 0x50, 0, [0xA0, 0x10, 0x22], acks=(True, False, True),
          reasons=('nack',), status='warn', bad=(1,)))
    add('T06', Bus().start().byte(0xA0).byte(0x12).rstart(),
        e('write', 0x50, 0, [0xA0, 0x12]),
        dict(kind='partial', addr=None, rw=None, ack=None, start='Sr', status='warn',
             reasons=['truncated'], fields=[], labels={}))
    add('T07', Bus().start().byte(0xF4).byte(0xA5).byte(0x77).stop(),
        e('write', 0x2A5, 0, [0xF4, 0xA5, 0x77], low=True, labels={0: 'A1', 1: 'A2'}))
    add('T08', Bus().start().byte(0xF4).byte(0xA5).rstart().byte(0xF5).byte(0x34, False).stop(),
        e('write', 0x2A5, 0, [0xF4, 0xA5], low=True, labels={0: 'A1', 1: 'A2'}),
        e('read', 0x2A5, 1, [0xF5, 0x34], acks=(True, False), start='Sr', labels={0: 'A3'}))
    add('T09/A1', Bus().start().byte(0xF4, False).byte(0xA5).stop(),
        e('write', None, 0, [0xF4], acks=(False,), reasons=('nack',), status='warn',
          labels={0: 'A1'}, bad=(0,)))
    add('T10/A2', Bus().start().byte(0xF4).byte(0xA5, False).stop(),
        e('write', 0x2A5, 0, [0xF4, 0xA5], acks=(True, False), low=True,
          reasons=('nack',), status='warn', labels={0: 'A1', 1: 'A2'}, bad=(1,)))
    add('A3', Bus().start().byte(0xF4).byte(0xA5).rstart().byte(0xF5, False).byte(0x34).stop(),
        e('write', 0x2A5, 0, [0xF4, 0xA5], low=True),
        e('read', 0x2A5, 1, [0xF5], acks=(False,), start='Sr', reasons=('nack',),
          status='warn', labels={0: 'A3'}, bad=(0,)))
    for name, value, code, status in (('T11', 6, (), 'ok'), ('T12', 0, ('gc_invalid',), 'error'),
                                       ('GC04', 4, (), 'ok'), ('GChardware', 0xA1, (), 'ok'),
                                       ('GChex', 0x12, (), 'ok')):
        add(name, Bus().start().byte(0).byte(value).stop(),
            e('gc', 0, 0, [0, value], reasons=code, status=status, bad=(1,) if code else ()))
    add('T13', Bus().start().byte(1, False).rstart().byte(0xA0).stop(),
        e('start_byte', 0, 1, [1], acks=(False,)), e('write', 0x50, 0, [0xA0], start='Sr'))
    add('T14', Bus().start().byte(1).stop(),
        e('start_byte', 0, 1, [1], reasons=('start_byte_ack',), status='error', bad=(0,)))
    for ack in (False, True):
        add(f'T15/{ack}', Bus().start().byte(9, ack).rstart().byte(0xA0).byte(0x12).stop(),
            e('hs_code', 4, 1, [9], acks=(ack,), reasons=('hs_code_ack',) if ack else (),
              status='error' if ack else 'ok', bad=(0,) if ack else ()),
            e('write', 0x50, 0, [0xA0, 0x12], start='Sr'))
    add('T17', Bus().start().byte(0xA0).stretch(.002).byte(0x12).byte(0x34).stop(),
        e('write', 0x50, 0, [0xA0, 0x12, 0x34]))
    # T20 在第五個上升緣暫存值之後，SCL 高時插入 P，再過 300 ns 插入 S。
    b = Bus().start().word(0xA, 4)
    b.idle(b.period / 2).set('scl', 1)
    b.idle(b.period / 8).set('sda', 1)
    b.idle(300e-9).set('sda', 0)
    b.idle(b.period / 2).set('scl', 0)
    b.byte(0xA0).stop()
    cut = dict(kind='partial', addr=None, rw=None, ack=None, start='S', status='error',
               reasons=['byte_cut'], fields=[('addr', 0xA, 4, None, None, False)], labels={})
    add('T20', b, cut, e('write', 0x50, 0, [0xA0]))
    b = Bus().word(0xB, 4).stop().start().byte(0xA0).stop()
    add('T21', b, dict(kind='partial', addr=None, rw=None, ack=None, start=None, status='ok',
                      reasons=[], fields=[], labels={}), e('write', 0x50, 0, [0xA0]))
    add('T31', Bus().start().stop(),
        dict(kind='empty', addr=None, rw=None, ack=None, start='S', status='warn',
             reasons=['empty'], fields=[], labels={}))
    add('T34', Bus().start().byte(0xF4).byte(0xA5).stop().start().byte(0xF5).byte(0x34, False).stop(),
        e('write', 0x2A5, 0, [0xF4, 0xA5], low=True),
        e('read', None, 1, [0xF5, 0x34], acks=(True, False), reasons=('addr10_unresolved',), status='warn'))
    for raw in (0xA0, 0xA1):
        add(f'位址NACK/{raw}', Bus().start().byte(raw, False).byte(0xFF).stop(),
            e('read' if raw & 1 else 'write', raw >> 1, raw & 1, [raw], acks=(False,),
              reasons=('nack',), status='warn', bad=(0,)))
    for a, b in ((False, True), (True, False), (False, False)):
        add(f'GC無應答/{a}/{b}', Bus().start().byte(0, a).byte(6, b).stop(),
            e('gc', 0, 0, [0, 6], acks=(a, b)))
    add('GC第三byteNACK', Bus().start().byte(0).byte(6).byte(0x12, False).stop(),
        e('gc', 0, 0, [0, 6, 0x12], acks=(True, True, False), reasons=('nack',), status='warn', bad=(2,)))
    add('讀ACK後NACK', Bus().start().byte(0xA1).byte(0x12).byte(0x34, False).stop(),
        e('read', 0x50, 1, [0xA1, 0x12, 0x34], acks=(True, True, False)))
    for addr in (1, 2, 3, 0x7C, 0x7D, 0x7E, 0x7F):
        for rw in (0, 1):
            raw = addr * 2 + rw
            add(f'保留/{raw}', Bus().start().byte(raw).stop(),
                e('read' if rw else 'write', addr, rw, [raw], reasons=('reserved_addr',)))
    return result


if __name__ == '__main__':
    assert len(vectors()) >= 40
    print('web.i2c_vectors self-check OK')
