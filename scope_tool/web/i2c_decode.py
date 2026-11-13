from __future__ import annotations

"""I2C 離線事件解碼；僅處理位元協定，不推測時序模式或儀器狀態。"""
import numpy as np
from scope_tool.web.logic import Edges, auto_threshold, validate_time, to_edges
from scope_tool.web.i3c_events import events
from scope_tool.web.i3c_fields import frame, field
from scope_tool.web.i3c_ccc import reason
from scope_tool.web.i2c_roles import estimate_waveforms

ROLES = {'scl': True, 'sda': True}
BASE = 'scl'
ADDR_TABLE = False
REQUIRE_EDGES = True


def options(options: dict, channels: dict) -> dict:
    if not isinstance(options, dict) or set(options) - {'addr_bits', 'estimate'}:
        raise ValueError('I2C 參數不合法')
    if type(options.get('estimate', False)) is not bool:
        raise ValueError('I2C estimate 須為布林值')
    if type(options.get('addr_bits', 7)) is not int or options.get('addr_bits', 7) not in (7, 8):
        raise ValueError('I2C addr_bits 須為 7 或 8 的整數')
    return {}  # 只影響顯示，不把選項傳入解碼核心。


def display_addr(f: dict, options: dict) -> int | None:
    """CSV 位址欄使用快照選項；特殊位址沿用原值。"""
    addr = f['addr']
    if (options.get('addr_bits', 7) == 8 and f['kind'] in ('write', 'read')
            and addr is not None and 0x08 <= addr <= 0x77 and f['rw'] in (0, 1)
            and not any(x['kind'] == 'addr_lo' or x['kind'] == 'addr'
                        and x['value'] is not None and x['value'] & 0xF8 == 0xF0 for x in f['fields'])):
        return addr << 1 | f['rw']
    return addr


class Decoder:
    """保留一個待確認位元；10-bit 脈絡只跨越連續且目標相同的 Sr。"""
    def __init__(self, max_frames: int, max_fields: int) -> None:
        self.max_frames, self.max_fields = max_frames, max_fields
        self.frames, self.bits, self.warnings = [], [], []
        self.f, self.pending, self.partial, self.context = None, None, None, None
        self.buf = []
        self.stage, self.blocked = 'addr', False
        self.nfields, self.truncated, self.halted = 0, False, False
        self.cut = None

    def limit(self, tm: float) -> None:
        self.halted = self.truncated = True
        self.cut = tm
        self.warnings.append(f'事件超過上限，只解到 t={tm:.12g}')

    def add(self, item: dict) -> bool:
        if self.nfields >= self.max_fields:
            self.limit(item['t0'])
            return False
        self.f['fields'].append(item)
        self.nfields += 1
        return True

    def close(self, tm: float, truncated: bool = False) -> None:
        if self.f is None:
            return
        if self.buf:
            item = field(self.buf, self.stage)
            item['ok'] = False
            self.add(item)
            reason(self.f, 'truncated' if truncated else 'byte_cut', 'warn' if truncated else 'error')
        elif not self.f['fields'] and self.f['start'] and not truncated:
            self.f['kind'] = 'empty'
            reason(self.f, 'empty', 'warn')
        if truncated:
            reason(self.f, 'truncated', 'warn')
        self.f.update(t1=tm, i=len(self.frames))
        self.frames.append(self.f)
        self.f, self.buf = None, []

    def nack(self, item: dict, label: str = '') -> None:
        if label:
            item['label'] = label
        if item['ninth'] == 1:
            item['ok'] = False
            reason(self.f, 'nack', 'warn')

    def header(self, item: dict) -> None:
        f, raw = self.f, item['value']
        addr, rw, ack = raw >> 1, raw & 1, item['ninth'] == 0
        f.update(addr=addr, rw=rw, ack=ack, kind='read' if rw else 'write')
        self.stage = 'data'
        old, self.context = self.context, None
        if raw & 0xF8 == 0xF0:
            item['label'] = 'A3' if rw else 'A1'
            self.nack(item, item['label'])
            if rw:
                if f['start'] == 'Sr' and old is not None and old >> 8 == (raw >> 1) & 3:
                    f['addr'] = old
                    if ack:
                        self.context = old
                else:
                    f['addr'] = None
                    reason(f, 'addr10_unresolved', 'warn')
            else:
                f['addr'] = None
                self.high = ((raw >> 1) & 3) << 8
                self.stage = 'addr_lo'
            self.blocked = not ack
        elif raw == 0:
            f.update(kind='gc', label='General Call')
            if not ack:
                item['label'] = '無目標應答'
        elif raw == 1:
            f.update(kind='start_byte', label='START byte')
            if ack:
                item['ok'] = False
                reason(f, 'start_byte_ack')
            self.blocked = True
        elif raw & 0xF8 == 8:
            f.update(kind='hs_code', label='Hs controller code')
            if ack:
                item['ok'] = False
                reason(f, 'hs_code_ack')
        else:
            self.nack(item)
            self.blocked = not ack
            if addr in (1, 2, 3) or addr >= 0x7C:
                reason(f, 'reserved_addr', 'ok')
                f['label'] = {1: 'CBUS', 2: '其他匯流排格式保留', 3: '未來用途保留'}.get(
                    addr, 'Device ID 前綴' if addr == 0x7C or rw else '保留位址')

    def bit(self, tm: float, val: int) -> None:
        if self.f is None or self.blocked:
            return
        if len(self.buf) == 8 and self.nfields >= self.max_fields:
            self.limit(tm)
            return
        self.bits.append((tm, val))
        self.buf.append((tm, val))
        if len(self.buf) != 9:
            return
        item = field(self.buf, self.stage, 'ack')
        self.buf = []
        self.add(item)
        f = self.f
        if self.stage == 'addr':
            self.header(item)
        elif self.stage == 'addr_lo':
            f['addr'] = self.high | item['value']
            self.nack(item, 'A2')
            self.context = f['addr'] if item['ninth'] == 0 else None
            self.stage = 'data'
        elif f['kind'] == 'gc' and len(f['fields']) == 2:
            v = item['value']
            item['label'] = {6: '重設並寫入可程式位址', 4: '寫入可程式位址但不重設'}.get(
                v, f'hardware GC 來源位址 {v >> 1:02X}' if v & 1 else f'{v:02X}')
            if v == 0:
                reason(f, 'gc_invalid')
                item['ok'] = False
            if item['ninth']:
                item['label'] += '；無目標應答'
        elif f['rw'] == 0:
            self.nack(item)

    def consume(self, event: tuple) -> None:
        tag, tm = event[:2]
        if tag == 'bit':
            if self.f is None:
                if self.partial is None:
                    self.partial = tm
            else:
                self.pending = (tm, event[2])
        elif tag == 'low':
            if self.f is None and self.partial is None:
                self.partial = tm
            if self.pending is not None:
                self.bit(*self.pending)
                self.pending = None
        elif tag in ('start', 'stop'):
            self.pending = None
            repeat = self.f is not None
            if self.partial is not None:
                if len(self.frames) >= self.max_frames:
                    self.limit(tm)
                    return
                self.f = frame(self.partial)
                self.f['label'] = '擷取開始於傳輸中途'
                self.partial = None
            self.close(tm)
            if tag == 'stop':
                self.context = None
            else:
                if len(self.frames) >= self.max_frames:
                    self.limit(tm)
                    return
                self.f = frame(tm, start='Sr' if repeat else 'S')
                self.stage, self.blocked = 'addr', False
        elif tag in ('gap', 'pattern'):
            self.pending = None
            if self.f is None and self.partial is not None:
                if len(self.frames) >= self.max_frames:
                    self.limit(tm)
                    return
                self.f = frame(self.partial)
                self.f['label'] = '擷取開始於傳輸中途'
            if tag == 'pattern' and self.f is not None:
                reason(self.f, 'sda_glitch', 'warn')
            self.close(tm, True)
            self.context, self.partial = None, None
        elif tag == 'ambiguous':
            if self.f is not None:
                reason(self.f, 'ambiguous_edge', 'warn')
            self.warnings.append(f'ambiguous_edge t={tm:g}')


def run(edges: dict[str, Edges], *, t1: float | None = None,
        max_frames: int = 100_000, max_fields: int = 100_000) -> dict:
    """兩線共用最早截斷點，所有輸出均在有效擷取範圍內。"""
    if max_frames < 1 or max_fields < 1:
        raise ValueError('事件上限須為正整數')
    scl, sda = edges['scl'], edges['sda']
    end = float(t1 if t1 is not None else max(scl.time[-1], sda.time[-1]))
    cuts = [float(e.time[-1]) for e in (scl, sda) if e.truncated]
    if cuts:
        end = min(end, *cuts)
    d = Decoder(max_frames, max_fields)
    if scl.min_run and scl.min_run < 4:
        d.warnings.append(f'取樣不足（最短 SCL 脈寬 {scl.min_run} 點）')
    for event in events(scl, sda, end):
        d.consume(event)
        if d.halted:
            end = min(end, d.cut)
            break
    if d.partial is not None and len(d.frames) < max_frames:
        d.f = frame(d.partial)
        d.f['label'] = '擷取開始於傳輸中途'
    d.close(end, True)
    if cuts:
        d.warnings.append(f'邊沿超過上限，只解到 t={end:.12g}')
    bits = [(tm, v) for tm, v in d.bits if tm <= end]
    return dict(frames=d.frames, bits_t=np.array([b[0] for b in bits]),
                bits_v=np.array([b[1] for b in bits], dtype=np.int8), addresses=[],
                warnings=d.warnings, truncated=d.truncated or bool(cuts), t1=end)


def decode_waveforms(t: np.ndarray, scl: np.ndarray, sda: np.ndarray, *,
                     thresholds: dict | None = None, max_edges: int = 10_000_000, **kw: object) -> dict:
    """純函式入口，門檻與邊沿轉換直接沿用既有邏輯層。"""
    validate_time(t)
    edges, used = {}, {}
    for name, v in (('scl', scl), ('sda', sda)):
        th = (thresholds or {}).get(name)
        th = auto_threshold(v) if th is None else th
        used[name] = th
        if th is None:
            return dict(ok=False, reason=f'{name.upper()} 無有限高低平台', thresholds=used)
        edge = to_edges(t, v, *th, max_edges=max_edges)
        if not np.any((edge.value >= 0) & ~edge.resync):
            return dict(ok=False, reason=f'{name.upper()} 無轉態（門檻 {th}）', thresholds=used)
        edges[name] = edge
    kw.setdefault('t1', float(t[-1]))
    return dict(ok=True, reason=None, thresholds=used, **run(edges, **kw))


if __name__ == '__main__':
    assert options({}, {}) == {} and BASE == 'scl' and not ADDR_TABLE
    assert options({'addr_bits': 7}, {}) == options({'addr_bits': 8}, {}) == {}
    assert options({'estimate': True}, {}) == {}
    for value in (1, None, 'true'):
        try:
            options({'estimate': value}, {})
        except ValueError:
            pass
        else:
            raise AssertionError(value)
    print('web.i2c_decode self-check OK')
