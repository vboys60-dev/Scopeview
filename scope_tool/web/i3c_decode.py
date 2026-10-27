from __future__ import annotations

"""單 lane I3C SDR 被動解碼核心，不持有 Analysis 或儀器。# 待真機驗證。"""
import numpy as np
from scope_tool.web.logic import Edges, auto_threshold, to_edges, validate_time, MAX_FRAMES, MAX_FIELDS
from scope_tool.web.i3c_events import events
from scope_tool.web.i3c_fields import frame, field, header, daa_fields
from scope_tool.web.i3c_ccc import COMMANDS, active, finish_ccc, invalidate, reason

def parity_ok(v: int, t: int) -> bool:
    return (v.bit_count() + t) % 2 == 1


def da_par(da: int) -> int:
    return 1 ^ (da.bit_count() & 1)


def classify_pattern(start_high: bool, k: int, n: int, end_sda: int) -> str:
    if start_high and n == 14 and k == 7 and end_sda == 1:
        return 'target_reset'
    if start_high and k == 4 and end_sda == 0:
        return 'hdr_exit'
    return 'pattern'


def read_t_end(t: int, sda_fell: bool, sda_rose: bool) -> str | None:
    return 'controller' if t == 1 and sda_fell else 'stop' if t == 0 and sda_rose else None


class Decoder:
    """只在事件層迭代；位元時間保留實際 SCL 上升緣。"""
    def __init__(self, i2c_addrs: set[int], max_frames: int, max_fields: int) -> None:
        self.i2c = i2c_addrs
        self.max_frames, self.max_fields = max_frames, max_fields
        self.frames, self.addresses, self.bits = [], [], []
        self.warnings = []
        self.f = None
        self.buf = []
        self.head, self.da, self.rw, self.ack = False, 0, 0, False
        self.start = 'S'
        self.window, self.ended, self.after_end = None, False, 0
        self.partial = None
        self.synced, self.truncated = False, False
        self.nfields = 0

    def limit(self, tm: float) -> None:
        self.truncated = True
        self.warnings.append(f'事件超過上限，只解到 t={tm:.12g}')

    def close(self, tm: float, truncated: bool = False) -> None:
        if self.f is not None and self.f['kind'] == 'partial' and not self.f['label'] and not self.f['fields'] and len(self.buf) < 8:
            self.f = None
        if self.f is not None:
            self.f['t1'] = tm
            if truncated:
                reason(self.f, 'truncated', 'warn')
            if self.f['ccc'] is not None and self.f['kind'] != 'daa':
                finish_ccc(self.f, self.addresses)
            self.f['i'] = len(self.frames)
            self.frames.append(self.f)
            self.nfields += len(self.f['fields'])
        self.f, self.buf, self.window = None, [], None

    def begin(self, tm: float) -> None:
        start = 'Sr' if self.synced and self.f is not None else 'S'
        carry = None
        keep = self.f is not None and self.f['kind'] in ('ccc_direct', 'daa')
        if self.f and self.f['addr'] == 0x7E and self.f['ccc'] is None and len(self.f['fields']) == 1:
            carry = self.f
            carry['fields'][0]['label'] = '7E 開場'
            self.f = None
        if not keep:
            self.close(tm)
            self.f = carry or frame(tm, start=start)
        self.head, self.buf, self.start = True, [], start
        self.window, self.ended, self.after_end = None, False, 0
        self.synced = True

    def bit(self, tm: float, val: int) -> None:
        if not self.synced:
            if self.partial is None:
                self.partial = tm
            return
        if self.f is None or self.f['kind'] == 'hdr':
            return
        self.bits.append((tm, val))
        self.buf.append((tm, val))
        f = self.f
        if self.head:
            if len(self.buf) < 9:
                return
            # Direct 遇到新的 7E/W 開啟下一筆 CCC。
            raw = field(self.buf, 'addr', 'ack')['value']
            direct, daa = f['kind'] == 'ccc_direct', f['kind'] == 'daa'
            if (direct or daa) and raw == 0xFC:
                begin = self.buf[0][0]
                pending = self.buf
                self.close(begin)
                self.f = f = frame(begin, start='Sr')
                self.buf = pending
                direct = daa = False
            self.da, self.rw, self.ack = header(f, self.buf, self.i2c, self.addresses, self.start, direct, daa)
            self.head, self.buf = False, []
            return
        if not self.ack:
            self.buf = []
            return
        if self.ended:
            self.after_end += 1
            if self.after_end >= 8:
                reason(f, 't_bit')
            return
        if f['kind'] == 'daa':
            if len(self.buf) == 73:
                if self.nfields + len(f['fields']) + 4 > self.max_fields:
                    self.limit(tm)
                    return
                daa_fields(f, self.buf, self.addresses, da_par)
                self.buf = []
            return
        if len(self.buf) < 9:
            return
        reading = self.rw == 1
        ninth = 'ack' if f['kind'] == 'i2c' else 'tbit' if reading else 'parity'
        data = field(self.buf, 'data', ninth, self.da if f['kind'] == 'ccc_direct' else None)
        self.buf = []
        if ninth == 'parity' and not parity_ok(data['value'], data['ninth']):
            data['ok'] = False
            data['label'] = '同位錯'
            reason(f, 'parity')
        if f['addr'] == 0x7E and f['ccc'] is None:
            code = data['value']
            data['kind'] = 'ccc'
            f.update(ccc=code, kind='daa' if code == 7 else 'ccc_direct' if code & 128 else 'ccc_broadcast')
            cmd = COMMANDS.get(code)
            f['ccc_name'] = cmd.name if cmd else None
        elif f['kind'] == 'ibi':
            a = active(self.addresses, self.da)
            bcr = a['bcr'] if a else None
            if bcr is None:
                data['label'] = 'BCR 未知（若為 IBI 首 byte 為 MDB）'
            elif bcr & 4:
                if len(f['fields']) == 1:
                    data['kind'] = 'mdb'
            else:
                reason(f, 'ibi_unexpected_payload', 'warn')
        f['fields'].append(data)
        if ninth == 'tbit':
            self.window = data['ninth']
            self.ended = self.window == 0
        if ninth == 'ack' and not reading and data['ninth']:
            reason(f, 'nack', 'warn')
        if data['kind'] == 'ccc' and 0x20 <= data['value'] <= 0x27:
            mode = data['value'] - 0x20
            self.close(tm)
            self.f = frame(tm, 'hdr')
            self.f['label'] = f"HDR-{('DDR', 'TSP', 'TSL', 'BT')[mode] if mode < 4 else mode} 區段（未解碼）"

    def consume(self, event: tuple) -> None:
        tag, tm = event[:2]
        if tag == 'pattern':
            _, t0, t1, k, n, end_sda, sr, stop, low = event
            was_hdr = self.f is not None and self.f['kind'] == 'hdr'
            if self.f is None and self.partial is not None and self.partial < t0:
                self.f = frame(self.partial)
                self.f['label'] = '擷取開始於傳輸中途'
            self.partial = None
            self.close(t0, not was_hdr)
            if len(self.frames) >= self.max_frames:
                self.limit(t0)
                return
            kind = classify_pattern(True, k, n, end_sda) if not low else 'pattern'
            self.f = frame(t0, kind)
            self.f['label'] = f'k={k}；形狀辨識，未檢時序（tDIG_H 等待確認）'
            if kind == 'hdr_exit' and not was_hdr:
                self.f['label'] += '（未見 ENTHDR）'
            incomplete = low or (kind != 'pattern' and (not stop or (kind == 'target_reset' and not sr)))
            if incomplete:
                reason(self.f, 'pattern_incomplete', 'warn')
            elif kind == 'pattern':
                reason(self.f, 'pattern_unknown', 'warn')
            if kind == 'target_reset' and not incomplete:
                invalidate(self.addresses, t1, 'Target Reset 後有效性未知')
            self.close(t1)
            self.synced = stop
        elif tag == 'gap':
            self.close(tm, True)
            self.synced, self.partial = False, None
        elif tag == 'ambiguous':
            if self.f:
                reason(self.f, 'ambiguous_edge', 'warn')
            self.warnings.append(f'ambiguous_edge t={tm:g}')
        elif tag in ('low', 'activity'):
            if not self.synced and self.partial is None:
                self.partial = tm
            if tag == 'low':
                self.window = None
        elif tag == 'bit':
            self.bit(tm, event[2])
        elif tag in ('start', 'stop'):
            if self.f and self.f['kind'] == 'hdr':
                return
            action = read_t_end(self.window, tag == 'start', tag == 'stop') if self.window is not None else None
            if action == 'controller' and self.f:
                self.f['label'] += '；Controller 提前結束'
            if not self.synced and self.partial is not None:
                self.f = frame(self.partial)
                self.f['label'] = '擷取開始於傳輸中途'
                self.close(tm)
                self.partial = None
            if tag == 'start':
                self.begin(tm)
            else:
                self.close(tm)
                self.synced = True


def decode(scl: Edges, sda: Edges, *, t1: float | None = None,
           i2c_addrs: set[int] | None = None, max_frames: int = MAX_FRAMES,
           max_fields: int = MAX_FIELDS) -> dict:
    """輸入邊沿，輸出 frames／bits／addresses／warnings；上限可覆寫供自檢。"""
    # ponytail: 狀態機純 Python；邊沿 >5M 時考慮 numpy 化位元取樣。
    if max_frames < 1 or max_fields < 1:
        raise ValueError('事件上限須為正整數')
    end = t1 if t1 is not None else max(scl.time[-1], sda.time[-1])
    cuts = [e.time[-1] for e in (scl, sda) if e.truncated]
    if cuts:
        end = min(end, *cuts)
    d = Decoder(i2c_addrs or set(), max_frames, max_fields)
    if scl.min_run and scl.min_run < 4:
        d.warnings.append(f'取樣不足（最短 SCL 脈寬 {scl.min_run} 點）')
    for e in events(scl, sda, end):
        if e[1] > end:
            break
        # ponytail: 上限防 JSON／記憶體過大；需要時改分頁 RPC。
        if len(d.frames) >= max_frames or d.nfields + (len(d.f['fields']) if d.f else 0) >= max_fields:
            d.truncated = True
            d.warnings.append(f'事件超過上限，只解到 t={e[1]:.12g}')
            if len(d.frames) < max_frames:
                d.close(e[1], True)
            else:
                d.f = None
            break
        d.consume(e)
        if d.truncated:
            d.close(e[1], True)
            break
    d.close(end, True)
    if d.partial is not None:
        d.f = frame(d.partial)
        d.f['label'] = '擷取開始於傳輸中途'
        d.close(end, True)
    if cuts:
        d.warnings.append(f'邊沿超過上限，只解到 t={end:.12g}')
    return dict(frames=d.frames, bits_t=np.array([b[0] for b in d.bits]),
                bits_v=np.array([b[1] for b in d.bits], dtype=np.int8), addresses=d.addresses,
                warnings=d.warnings, truncated=d.truncated or bool(cuts), t1=end)


def decode_waveforms(t: np.ndarray, scl: np.ndarray, sda: np.ndarray, *,
                     thresholds: dict | None = None, max_edges: int = 10_000_000, **options: object) -> dict:
    """P1 純函式入口；P2 可用同一流程，不建立 _dec 快取。"""
    validate_time(t)
    thresholds = thresholds or {}
    edges, used = [], {}
    for name, v in (('scl', scl), ('sda', sda)):
        th = thresholds.get(name)
        th = auto_threshold(v) if th is None else th
        used[name] = th
        if th is None:
            return dict(ok=False, reason=f'{name.upper()} 無有限高低平台', thresholds=used)
        edge = to_edges(t, v, *th, max_edges=max_edges)
        if not np.any((edge.value >= 0) & ~edge.resync):
            return dict(ok=False, reason=f'{name.upper()} 無轉態（門檻 {th}）', thresholds=used)
        edges.append(edge)
    return dict(ok=True, reason=None, thresholds=used, **decode(*edges, t1=float(t[-1]), **options))

ROLES = {'scl': True, 'sda': True}
BASE = 'scl'
ADDR_TABLE = REQUIRE_EDGES = True


def options(options: dict, channels: dict) -> dict:
    if not isinstance(options, dict) or set(options) - {'i2c_addrs'}:
        raise ValueError('options 只接受 i2c_addrs')
    addrs = options.get('i2c_addrs', [])
    if not isinstance(addrs, list) or any(type(v) is not int or not 0 <= v <= 127 for v in addrs):
        raise ValueError('i2c_addrs 須為 0–127 整數陣列')
    return {'i2c_addrs': set(addrs)}

def run(edges: dict, **kwargs: object) -> dict:
    return decode(edges['scl'], edges['sda'], **kwargs)


if __name__ == '__main__':
    assert parity_ok(0xA5, 1) and not parity_ok(0, 0) and da_par(8) == 0
    assert classify_pattern(True, 7, 14, 1) == 'target_reset'
    assert read_t_end(1, True, False) == 'controller'
    print('web.i3c_decode self-check OK')
