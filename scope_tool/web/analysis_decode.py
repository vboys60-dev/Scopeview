from __future__ import annotations

"""Analysis 的離線 I3C 解碼快照與 CSV；只用來源時間。# 待真機驗證。"""
import csv
import datetime as dt
import itertools
import json
from pathlib import Path

import numpy as np

from scope_tool.contracts import ScopeError
from scope_tool.storage.writer import timestamped
from scope_tool.web.analysis_util import BadRequest, StaleError
from scope_tool.web.i3c_decode import decode as decode_edges
from scope_tool.web.logic import auto_threshold, to_edges, validate_time

_DECODE_IDS = itertools.count(1)
MAX_BITS = 4096
ROLES = {'scl', 'sda'}


def _finite(v: object) -> bool:
    return type(v) in (int, float) and np.isfinite(v)


def _params(protocol: str, channels: dict, thresholds: dict, options: dict) -> None:
    if protocol != 'i3c':
        raise BadRequest('目前只支援 i3c')
    if not isinstance(channels, dict) or set(channels) != ROLES or not all(isinstance(v, str) for v in channels.values()):
        raise BadRequest('channels 必須為 scl／sda 字串 map')
    if channels['scl'] == channels['sda']:
        raise BadRequest('SCL 與 SDA 通道必須不同')
    if not isinstance(thresholds, dict) or set(thresholds) != ROLES:
        raise BadRequest('thresholds 鍵必須為 scl／sda')
    for th in thresholds.values():
        if th is not None and not (isinstance(th, (list, tuple)) and len(th) == 2 and all(_finite(v) for v in th) and th[0] < th[1]):
            raise BadRequest('門檻須為兩個有限數 lo < hi 或 null')
    if not isinstance(options, dict) or set(options) - {'i2c_addrs'}:
        raise BadRequest('options 只接受 i2c_addrs')
    addrs = options.get('i2c_addrs', [])
    if not isinstance(addrs, list) or any(type(v) is not int or not 0 <= v <= 127 for v in addrs):
        raise BadRequest('i2c_addrs 須為 0–127 整數陣列')


class DecodeMixin:
    def decode(self, protocol: str, channels: dict, thresholds: dict, options: dict) -> dict:
        with self._lock:
            self._dec = None  # 所有失敗（含參數錯誤）都使舊 id 失效。
            gen, waves, _ = self._need()
            path = self._path
        _params(protocol, channels, thresholds, options)
        lines = {r: self._wf(waves, channels[r]) for r in ('scl', 'sda')}
        try:
            validate_time(lines['scl'].time, lines['sda'].time)
        except ValueError as exc:
            raise BadRequest(str(exc)) from exc
        used = {r: (auto_threshold(lines[r].voltage) if thresholds[r] is None else tuple(thresholds[r])) for r in ('scl', 'sda')}
        summary = dict(ok=False, reason=None, gen=gen, decode_id=None, protocol=protocol,
                       channels=dict(channels), thresholds={r: list(v) if v is not None else None for r, v in used.items()},
                       t0=None, t1=None, counts=dict(frames=0, fields=0, errors=0, warns=0), truncated=False, warnings=[])
        edges = []
        for role in ('scl', 'sda'):
            th, w = used[role], lines[role]
            if th is None:
                summary['reason'] = f'{role.upper()} 無有限高低平台'
            else:
                try:
                    edge = to_edges(w.time, w.voltage, *th)
                except ValueError as exc:
                    raise BadRequest(str(exc)) from exc
                if not np.any((edge.value >= 0) & ~edge.resync):
                    summary['reason'] = f'{role.upper()} 無轉態（門檻 {th}）'
                edges.append(edge)
            if summary['reason']:
                with self._lock:
                    self._alive(gen)
                return summary
        result = decode_edges(*edges, t1=float(lines['scl'].time[-1]), i2c_addrs=set(options.get('i2c_addrs', [])))
        frames = result['frames']
        summary.update(ok=True, decode_id=f'd{next(_DECODE_IDS)}', t0=float(lines['scl'].time[0]), t1=result['t1'],
                       counts=dict(frames=len(frames), fields=sum(len(f['fields']) for f in frames),
                                   errors=sum(f['status'] == 'error' for f in frames), warns=sum(f['status'] == 'warn' for f in frames)),
                       truncated=result['truncated'], warnings=result['warnings'])
        meta = dict(path=path, channels=dict(channels), thresholds=summary['thresholds'],
                    options=json.loads(json.dumps(options)), decoded_at=dt.datetime.now().isoformat(' ', 'seconds'))
        with self._lock:
            self._alive(gen)
            self._dec = dict(id=summary['decode_id'], gen=gen, meta=meta, **result)
        return summary

    def _decode_snapshot(self, decode_id: str) -> dict:
        if not isinstance(decode_id, str):
            raise BadRequest('decode_id 必須為字串')
        with self._lock:
            snap = self._dec
            if snap is None or snap['id'] != decode_id or snap['gen'] != self._gen:
                raise StaleError('解碼結果已過期，請重新解碼')
            return snap

    def decode_frames(self, decode_id: str) -> dict:
        snap = self._decode_snapshot(decode_id)
        return dict(decode_id=decode_id, frames=snap['frames'], addresses=snap['addresses'])

    def decode_bits(self, decode_id: str, t0: float, t1: float) -> dict:
        if not _finite(t0) or not _finite(t1):
            raise BadRequest('t0／t1 必須為有限數')
        snap = self._decode_snapshot(decode_id)
        lo, hi = sorted((t0, t1))
        a, b = np.searchsorted(snap['bits_t'], lo, 'left'), np.searchsorted(snap['bits_t'], hi, 'right')
        end = min(b, a + MAX_BITS)
        return dict(bits=[[float(t), int(v)] for t, v in zip(snap['bits_t'][a:end], snap['bits_v'][a:end])], truncated=b - a > MAX_BITS)

    def export_decode(self, decode_id: str, directory: str | None) -> dict:
        if directory is not None and not isinstance(directory, str):
            raise BadRequest('directory 必須為字串或 null')
        snap = self._decode_snapshot(decode_id)
        meta, source = snap['meta'], snap['meta']['path']
        out = Path(directory).expanduser() if directory is not None else (source.parent if source else None)
        if out is None:
            raise ScopeError('沒有來源檔資料夾，請指定輸出資料夾')
        try:
            p = timestamped(out, f"{source.stem if source else 'waveform'}_解碼", 'csv')
            with p.open('w', newline='', encoding='utf-8-sig') as stream:
                writer = csv.writer(stream)
                writer.writerow(['來源檔', str(source or '（未存檔）')])
                for k, label in (('channels', '通道'), ('thresholds', '門檻'), ('options', '選項'), ('decoded_at', '解碼時間')):
                    writer.writerow([label, json.dumps(meta[k], ensure_ascii=False)])
                writer.writerow([])
                writer.writerow(['frame#', '種類', '起(s)', '迄(s)', '位址', 'RnW', 'ACK', 'CCC', '狀態', '原因', '說明',
                                 'field#', '欄位', '值(hex)', '位元數', '第9位', '第9位意義', 'field狀態', 'field說明'])
                for f in snap['frames']:
                    prefix = [f['i'], f['kind'], repr(float(f['t0'])), repr(float(f['t1'])), f['addr'], f['rw'], f['ack'],
                              f['ccc'], f['status'], ' '.join(f['reasons']), f['label']]
                    for i, field in enumerate(f['fields'] or [None]):
                        suffix = [i, field['kind'], '' if field['value'] is None else hex(field['value']), field['nbits'],
                                  field['ninth'], field['ninth_kind'], field['ok'], field['label']] if field else [''] * 8
                        writer.writerow(prefix + suffix)
                writer.writerow([])
                writer.writerow(['DA', 'PID', 'BCR', 'DCR', 'static', '起', '迄', '來源', '備註'])
                for addr in snap['addresses']:
                    writer.writerow([repr(float(addr[k])) if k in ('t_from', 't_to') and addr[k] is not None else addr[k]
                                     for k in ('da', 'pid', 'bcr', 'dcr', 'static', 't_from', 't_to', 'how', 'note')])
        except OSError as exc:
            raise ScopeError(f'匯出解碼結果失敗：{exc}') from exc
        return {'path': str(p)}


if __name__ == '__main__':
    import tempfile
    from scope_tool.contracts import Waveform
    from scope_tool.web.analysis_api import Analysis
    from scope_tool.web.i3c_synth import Bus

    a = Analysis()
    t, scl, sda = Bus().start().header(0x30).byte_w(0xA5).stop().target_reset().render()
    with tempfile.TemporaryDirectory() as directory:
        a._gen, a._path = 1, Path(directory) / '來源.csv'
        a._waves = [Waveform('CH1', t, scl), Waveform('CH2', t, sda)]
        params = dict(protocol='i3c', channels={'scl': 'CH1', 'sda': 'CH2'}, thresholds={'scl': None, 'sda': None}, options={})
        def good() -> str:
            r = a.decode(**params)
            assert r['ok'], r
            return r['decode_id']
        def raises(kind: type, fn: object) -> None:
            try:
                fn()
            except kind:
                return
            raise AssertionError(f'應拋出 {kind}')
        ident = good()
        frames = a.decode_frames(ident)['frames']
        field = next(v for f in frames for v in f['fields'] if v['kind'] == 'data')
        bits = a.decode_bits(ident, field['t0'], field['t1'])['bits']
        assert len(bits) == 9 and int(''.join(str(v) for _, v in bits[:8]), 2) == field['value']
        assert bits[-1][1] == field['ninth']
        assert a.decode_bits(ident, field['t1'], field['t0'])['bits'] == bits
        assert a.decode_bits(ident, bits[0][0], bits[0][0])['bits'] == bits[:1]
        for v in (float('nan'), float('inf'), True, '1'):
            raises(BadRequest, lambda: a.decode_bits(ident, v, 1))
        snap = a._dec
        a._dec = {**snap, 'bits_t': np.arange(5000.), 'bits_v': np.zeros(5000, dtype=int)}
        capped = a.decode_bits(ident, 0, 5000)
        assert capped['truncated'] and len(capped['bits']) == MAX_BITS
        a._dec = snap
        a._path = Path(directory) / '不可使用.csv'
        p = Path(a.export_decode(ident, None)['path'])
        assert p.name.startswith('來源_解碼_') and p.read_bytes().startswith(b'\xef\xbb\xbf')
        rows = list(csv.reader(p.open(encoding='utf-8-sig')))
        assert len(rows) == 9 + sum(max(1, len(f['fields'])) for f in frames) + len(snap['addresses'])
        for patch in ({'channels': {'scl': 'CH1', 'sda': 'CH1'}}, {'options': {'i2c_addrs': [True]}},
                      {'thresholds': {'scl': [0, float('inf')], 'sda': None}}, {'protocol': 'spi'},
                      {'channels': {'scl': 'CH1', 'sda': '不存在'}}, {'options': {'x': 1}}):
            ident = good()
            raises(BadRequest, lambda: a.decode(**{**params, **patch}))
            raises(StaleError, lambda: a.decode_frames(ident))
        ident = good()
        failed = a.decode(**{**params, 'thresholds': {'scl': [10, 11], 'sda': None}})
        assert not failed['ok'] and a._dec is None and set(failed['thresholds']) == ROLES
        raises(StaleError, lambda: a.decode_frames(ident))
        ident = good()
        a._waves[1] = Waveform('CH2', t + 1e-9, sda)
        raises(BadRequest, lambda: a.decode(**params))
        a._waves[1] = Waveform('CH2', t, sda)
        for voltage in (np.ones_like(sda), np.full_like(sda, np.nan), np.full_like(sda, np.inf)):
            ident = good()
            a._waves[1] = Waveform('CH2', t, voltage)
            failed = a.decode(**params)
            assert not failed['ok'] and 'SDA' in failed['reason'] and a._dec is None
            raises(StaleError, lambda: a.decode_frames(ident))
            a._waves[1] = Waveform('CH2', t, sda)
        original = a._waves
        bad_time = t.copy()
        bad_time[len(t) // 2] = bad_time[len(t) // 2 - 1]
        a._waves = [Waveform('CH1', bad_time, scl), Waveform('CH2', bad_time, sda)]
        raises(BadRequest, lambda: a.decode(**params))
        a._waves = original
        ident = good()
        new_id = good()
        assert new_id != ident
        raises(StaleError, lambda: a.decode_frames(ident))
        for fn in (lambda: a.decode_frames(None), lambda: a.decode_bits(None, 0, 1), lambda: a.export_decode(new_id, 42)):
            raises(BadRequest, fn)
        raises(ScopeError, lambda: a.export_decode(new_id, str(p)))
        ident = good()
        a.close_waveform()
        for fn in (lambda: a.decode_frames(ident), lambda: a.decode_bits(ident, 0, 1), lambda: a.export_decode(ident, None)):
            raises(StaleError, fn)
    print('web.analysis_decode self-check OK')
