from __future__ import annotations

"""Analysis 的離線多協定解碼快照與 CSV；只用來源時間。# 待真機驗證。"""
import csv
import datetime as dt
import itertools
import importlib
import json
from pathlib import Path

import numpy as np

from scope_tool.contracts import ScopeError
from scope_tool.storage.writer import timestamped
from scope_tool.web.analysis_util import BadRequest, StaleError
from scope_tool.web.logic import prepare, validate_time, MAX_FRAMES, MAX_FIELDS

_DECODE_IDS = itertools.count(1)
MAX_BITS = 4096
NAMES = ('i3c', 'i2c', 'spi', 'uart', 'can')


def _finite(v: object) -> bool:
    return type(v) in (int, float) and np.isfinite(v)


def protocol(name: str) -> object:
    if name not in NAMES:
        raise BadRequest('不支援的協定')
    module = f'scope_tool.web.{name}_decode'
    try:
        return importlib.import_module(module)
    except ModuleNotFoundError as exc:
        if exc.name != module:
            raise
        raise BadRequest('此協定尚未實作') from exc


def _params(mod: object, channels: dict, thresholds: dict, options: dict) -> dict:
    estimating = getattr(mod, '__name__', '') == 'scope_tool.web.uart_decode' and isinstance(options, dict) and options.get('estimate') is True
    if not isinstance(channels, dict) or set(channels) - mod.ROLES.keys() or any(r not in channels for r, required in mod.ROLES.items() if required and not estimating):
        raise BadRequest('channels 角色無效或缺少必填角色')
    if not all(isinstance(v, str) for v in channels.values()) or len(set(channels.values())) != len(channels):
        raise BadRequest('通道須為不同的字串')
    if not isinstance(thresholds, dict) or set(thresholds) != channels.keys() - getattr(mod, 'DIFF', {}).keys():
        raise BadRequest('thresholds 鍵須等於邏輯線')
    for th in thresholds.values():
        if th is not None and not (isinstance(th, (list, tuple)) and len(th) == 2 and all(_finite(v) for v in th) and th[0] < th[1]):
            raise BadRequest('門檻須為兩個有限數 lo < hi 或 null')
    if not channels:
        raise BadRequest('請至少選擇一個通道')
    try:
        return mod.options(options, channels)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


class DecodeMixin:
    def decode(self, protocol: str, channels: dict, thresholds: dict, options: dict) -> dict:
        with self._lock:
            estimating = protocol == 'uart' and isinstance(options, dict) and options.get('estimate') is True
            if not estimating:
                self._dec = None  # 正式解碼失敗（含參數錯誤）使舊 id 失效；估計保留快照。
            gen, waves, _ = self._need()
            path = self._path
        mod = globals()['protocol'](protocol)
        opts = _params(mod, channels, thresholds, options)
        lines = {r: self._wf(waves, channels[r]) for r in mod.ROLES if r in channels}
        base = lines.get(mod.BASE) or next(iter(lines.values()))
        try:
            for w in lines.values():
                validate_time(base.time, w.time)
            diff = getattr(mod, 'DIFF', {})
            volts = {r: w.voltage for r, w in lines.items() if r not in diff}
            for neg, pos in diff.items():
                if neg in lines:
                    # ponytail: 相減配置整條陣列；1e8 點時 +800 MB，需要時改分塊。
                    volts[pos] = volts[pos] - lines[neg].voltage
            if estimating:
                used, reason = mod.estimate_waveforms(base.time, volts, thresholds)
            else:
                edges, used, end, reason = prepare(base.time, volts, thresholds, require_edges=mod.REQUIRE_EDGES)
        except ValueError as exc:
            raise BadRequest(str(exc)) from exc
        summary = dict(ok=False, reason=reason, gen=gen, decode_id=None, protocol=protocol,
                       channels=dict(channels), thresholds={r: list(v) if v is not None else None for r, v in used.items()},
                       t0=None, t1=None, counts=dict(frames=0, fields=0, errors=0, warns=0), truncated=False, warnings=[])
        if reason:
            with self._lock:
                self._alive(gen)
                if any(next((v for v in self._waves if v.channel == w.channel), None) is not w for w in lines.values()):
                    raise StaleError('解碼來源已變更，請重新解碼')
            return summary
        result = mod.run(edges, t1=end, max_frames=MAX_FRAMES, max_fields=MAX_FIELDS, **opts)
        frames = result['frames']
        summary.update(ok=True, decode_id=f'd{next(_DECODE_IDS)}', t0=float(base.time[0]), t1=result['t1'],
                       counts=dict(frames=len(frames), fields=sum(len(f['fields']) for f in frames),
                                   errors=sum(f['status'] == 'error' for f in frames), warns=sum(f['status'] == 'warn' for f in frames)),
                       truncated=result['truncated'], warnings=result['warnings'])
        meta = dict(path=path, channels=dict(channels), thresholds=summary['thresholds'],
                    options=json.loads(json.dumps(options)), decoded_at=dt.datetime.now().isoformat(' ', 'seconds'))
        with self._lock:
            self._alive(gen)
            if any(next((v for v in self._waves if v.channel == w.channel), None) is not w for w in lines.values()):
                raise StaleError('解碼來源已變更，請重新解碼')
            self._dec = dict(id=summary['decode_id'], gen=gen, meta=meta, protocol=protocol, base=channels[mod.BASE], addr_table=mod.ADDR_TABLE, **result)
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
                    addr = protocol(snap['protocol']).display_addr(f, meta['options']) if snap['protocol'] == 'i2c' else f['addr']
                    prefix = [f['i'], f['kind'], repr(float(f['t0'])), repr(float(f['t1'])), addr, f['rw'], f['ack'],
                              f['ccc'], f['status'], ' '.join(f['reasons']), f['label']]
                    for i, field in enumerate(f['fields'] or [None]):
                        suffix = [i, field['kind'], '' if field['value'] is None else hex(field['value']), field['nbits'],
                                  field['ninth'], field['ninth_kind'], field['ok'], field['label']] if field else [''] * 8
                        writer.writerow(prefix + suffix)
                if snap['addr_table']:
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
                      {'thresholds': {'scl': [0, float('inf')], 'sda': None}}, {'protocol': 'lin'},
                      {'channels': {'scl': 'CH1', 'sda': '不存在'}}, {'options': {'x': 1}}):
            ident = good()
            raises(BadRequest, lambda: a.decode(**{**params, **patch}))
            raises(StaleError, lambda: a.decode_frames(ident))
        ident = good()
        failed = a.decode(**{**params, 'thresholds': {'scl': [10, 11], 'sda': None}})
        assert not failed['ok'] and a._dec is None and set(failed['thresholds']) == {'scl', 'sda'}
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
    import sys
    import scope_tool.web.analysis_decode as registry
    from types import SimpleNamespace
    from unittest.mock import patch
    from scope_tool.web.logic import prepare as real_prepare
    fake = SimpleNamespace(ROLES={'a': True, 'b': False, 'n': False}, BASE='a',
                           DIFF={'n': 'a'}, REQUIRE_EDGES=False, ADDR_TABLE=False,
                           options=lambda o, c: {}, run=None)
    received = []
    def run(edges: dict, **kw: object) -> dict:
        received.append((edges, kw))
        return dict(frames=[], addresses=[], bits_t=np.array([]), bits_v=np.array([]),
                    warnings=[], truncated=False, t1=kw['t1'])
    fake.run = run
    with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules, {'scope_tool.web.fake_decode': fake}), patch.dict(registry.__dict__, NAMES=(*NAMES, 'fake', 'zz_missing')):
        a = Analysis()
        a._gen, a._path = 1, Path(directory) / '假協定.csv'
        t = np.arange(20.)
        v = np.tile([0., 2.], 10)
        a._waves = [Waveform('A', t, v+3), Waveform('N', t, np.full(20, 3.)), Waveform('B', t, np.full(20, 2.))]
        fp = dict(protocol='fake', channels={'a':'A','n':'N','b':'B'}, thresholds={'a':[.5,1.5],'b':[.5,1.5]}, options={})
        r = a.decode(**fp)
        assert r['ok'] and received[-1][0]['a'].value.tolist() == [0, 1]*10, (r, received)
        text = Path(a.export_decode(r['decode_id'], directory)['path']).read_text(encoding='utf-8-sig')
        assert 'DA,PID' not in text
        assert a.decode('fake', {'a':'A'}, {'a':[3.5,4.5]}, {})['ok']
        failed = a.decode(**{**fp, 'thresholds': {'a':[.5,1.5], 'b':None}})
        assert not failed['ok'] and 'B 無有限高低平台；請改用手動門檻' == failed['reason']
        for channels, thresholds in [({'x':'A'}, {'x':None}), ({'b':'B'}, {'b':None}),
                                     ({'a':'A','b':'A'}, {'a':None,'b':None}), ({'a':'A'}, {'b':None})]:
            raises(BadRequest, lambda: a.decode('fake', channels, thresholds, {}))
        def limited(t: np.ndarray, volts: dict, thresholds: dict, **kw: object) -> tuple:
            return real_prepare(t, volts, thresholds, max_edges=4, **kw)
        with patch.dict(registry.__dict__, prepare=limited):
            assert a.decode(**fp)['ok']
            e, kw = received[-1]
            assert kw['t1'] == min(float(x.time[-1]) for x in e.values() if x.truncated)
        for name, message in [('lin','不支援的協定'), ('zz_missing','此協定尚未實作')]:
            try:
                a.decode(name, {}, {}, {})
            except BadRequest as exc:
                assert str(exc) == message
            else:
                raise AssertionError(name)
    print('web.analysis_decode self-check OK')
