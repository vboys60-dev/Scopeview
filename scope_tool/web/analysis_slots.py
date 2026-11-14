"""Analysis 的比對槽：鎖外讀檔與預建金字塔，鎖內原子替換；不碰儀器。"""
from __future__ import annotations

from pathlib import Path

from scope_tool.contracts import ScopeError, Waveform
from scope_tool.storage.reader import read_file_info, read_waveform_file
from scope_tool.web import decimate
from scope_tool.web.analysis_util import BadRequest, _clean, _file_rows


def _slot(slot: str) -> None:
    if slot not in ("Mem1", "Mem2", "Mem3", "Mem4"):
        raise BadRequest("槽位必須為 Mem1～Mem4")


class SlotMixin:
    def add_waveform(self, path: str, slot: str, channels: list[str]) -> dict:
        _slot(slot)
        with self._lock:
            if not self._main:
                raise ScopeError("請先開啟主檔")
            gen, _, _ = self._need()
        p = Path(path).expanduser()
        # ponytail: 改勾選仍重讀整檔；大檔慢時再暫存完整槽位資料。
        try:
            waves = [w for w in read_waveform_file(p) if len(w.time)]
        except OSError as exc:
            raise ScopeError(f"讀取比對檔失敗：{exc}") from exc
        if not waves:
            raise ScopeError("沒有波形資料可畫。")
        info = read_file_info(p)
        all_names = [w.channel for w in waves]
        if not isinstance(channels, list) or any(c not in all_names for c in channels):
            raise BadRequest("channels 含檔案裡沒有的通道")
        selected = [Waveform(f"{slot}.{w.channel}", w.time, w.voltage)
                    for w in waves if not channels or w.channel in channels]
        names = [w.channel for w in selected]
        if len(set(names)) != len(names):
            raise BadRequest("比對檔通道名稱重複")
        pyr = {w.channel: decimate.Pyramid(w.voltage) for w in selected
               if len(w.time) > decimate.PYRAMID_MIN}
        with self._lock:
            self._alive(gen)
            others = {w.channel for w in self._waves} - set(self._slots.get(slot, []))
            if others.intersection(names):
                raise BadRequest("比對檔通道與現有通道撞名")
            self._drop_slot(slot)
            self._waves.extend(selected)
            self._units.update({name: "V" for name in names})
            self._pyr.update(pyr)
            self._slots[slot] = names
            return _clean({"slot": slot, "path": str(p), "gen": gen, "all": all_names,
                           "info": _file_rows(p, info, selected),
                           "channels": [self._info(w, self._units, gen) for w in selected]})

    def remove_slot(self, slot: str) -> None:
        _slot(slot)
        with self._lock:
            self._drop_slot(slot)
        return None

    def _drop_slot(self, slot: str) -> None:
        """呼叫者持鎖；只清除引用此槽的快照，保留已算出的衍生通道。"""
        names = set(self._slots.pop(slot, []))
        self._waves = [w for w in self._waves if w.channel not in names]
        for name in names:
            self._units.pop(name, None)
            self._pyr.pop(name, None)
        if self._snap and any(r.get(k) in names for r in self._snap["results"] for k in ("channel", "channel2")):
            self._snap = None
        if self._spec and self._spec.get("source") in names:
            self._spec = None
        if self._dec and names.intersection(self._dec["meta"]["channels"].values()):
            self._dec = None


if __name__ == "__main__":
    import csv
    import tempfile
    from unittest.mock import patch

    import numpy as np

    from scope_tool.web.analysis_api import Analysis, fft_bytes, wave_bytes
    from scope_tool.web.analysis_util import StaleError
    from scope_tool.web.i3c_synth import Bus, write_csv

    def raises(kind: type, fn: object) -> Exception:
        try:
            fn()
        except kind as exc:
            return exc
        raise AssertionError(f"應拋出 {kind}")

    a = Analysis()
    raises(ScopeError, lambda: a.add_waveform("不存在.csv", "Mem1", []))
    raises(BadRequest, lambda: a.add_waveform("不存在.csv", "Mem5", []))
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        t = np.arange(4000) * 1e-6
        v = np.tile(np.r_[np.zeros(100), np.ones(100)], 20)

        def fixture(name: str, times: np.ndarray, volts: np.ndarray, two: bool = True) -> str:
            p = tmp / name
            with p.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Time(s)", "CH1(V)", *(["CH2(V)"] if two else [])])
                writer.writerows((x, y, *([1-y] if two else [])) for x, y in zip(times, volts))
            return str(p)

        main = fixture("主檔.csv", t, v)
        shifted = fixture("位移.csv", t + .00003, v)
        other = fixture("替換.csv", t, v * 3, False)
        fs = a.open_waveform(main)
        gen = fs["gen"]
        summary = a.add_waveform(shifted, "Mem1", [])
        assert summary["all"] == ["CHAN1", "CHAN2"] and summary["gen"] == gen == a._gen
        assert [c["name"] for c in summary["channels"]] == ["Mem1.CHAN1", "Mem1.CHAN2"]
        assert all(not c["derived"] for c in summary["channels"])
        assert ["通道", "Mem1.CHAN1, Mem1.CHAN2"] in summary["info"]
        raises(ScopeError, lambda: a.remove_channel("Mem1.CHAN1"))
        summary = a.add_waveform(shifted, "Mem1", ["CHAN1"])
        assert summary["all"] == ["CHAN1", "CHAN2"] and len(summary["channels"]) == 1
        raises(BadRequest, lambda: wave_bytes(a, "Mem1.CHAN2", 0, 1, 10, gen))
        before = list(a._waves)
        raises(BadRequest, lambda: a.add_waveform(main, "Mem1", ["NOPE"]))
        raises(ScopeError, lambda: a.add_waveform(str(tmp / "缺檔.h5"), "Mem1", []))
        assert all(x is y for x, y in zip(before, a._waves)) and len(before) == len(a._waves)
        dual = a.measure([dict(channel="CHAN1", channel2="Mem1.CHAN1", name="延遲", rising=True)],
                         None, {"Mem1.CHAN1": -.00003}, "10/50/90 %")["results"][0]
        assert dual["ok"] and abs(dual["stats"]["mean"]) < 1e-12, dual
        params = dict(protocol="i3c", channels={"scl": "CHAN1", "sda": "Mem1.CHAN1"},
                      thresholds={"scl": None, "sda": None}, options={})
        assert "時間軸不一致" in str(raises(BadRequest, lambda: a.decode(**params)))
        f = a.math("反相", "CHAN1", None, 0)
        with patch.object(decimate, "PYRAMID_MIN", 100):
            a.add_waveform(main, "Mem2", [])
        assert "Mem2.CHAN1" in a._pyr and not a._info(a._waves[-1], a._units, gen)["derived"]
        a.remove_channel(f["name"])
        a.remove_slot("Mem2")
        assert not any(n.startswith("Mem2.") for n in a._pyr)
        exported = Path(a.export_csv(None, None, directory)["path"])
        assert exported.read_text().splitlines()[0] == "Time(s),CH1(V),CH2(V)"

        def measured(ch: str, second: bool = False) -> dict:
            entry = dict(channel="CHAN1" if second else ch, name="延遲" if second else "Vmax", rising=True)
            if second:
                entry["channel2"] = ch
            return a.measure([entry], None, {}, "10/50/90 %")

        def export(m: dict) -> dict:
            return a.export_measurements(m["results"], gen, m["revision"], directory)

        def spectrum(ch: str) -> dict:
            return a.fft(ch, None, {}, "Hanning", "dBV", 50., 3, -80., "Decreasing Magnitude")

        # 鎖外計算途中同 gen 替換／移除來源，不能存回舊快照（含雙來源）。
        cut = a._cut
        for change in (lambda: a.add_waveform(other, "Mem1", []), lambda: a.remove_slot("Mem1")):
            for operation in (lambda: measured("Mem1.CHAN1"), lambda: measured("Mem1.CHAN1", True),
                              lambda: spectrum("Mem1.CHAN1")):
                a.add_waveform(main, "Mem1", [])
                def interrupted_cut(w: Waveform, rng: object, dx: dict) -> tuple:
                    result = cut(w, rng, dx)
                    change()
                    return result
                with patch.object(a, "_cut", side_effect=interrupted_cut):
                    assert isinstance(raises(StaleError, operation), StaleError)
                assert a._gen == gen and a._snap is None and a._spec is None

        a.add_waveform(main, "Mem1", [])
        for second in (False, True):
            m = measured("Mem1.CHAN1", second)
            fr = spectrum("Mem1.CHAN1")
            a.add_waveform(other, "Mem1", [])
            raises(StaleError, lambda: export(m))
            raises(StaleError, lambda: a.fft_track_rf(fr["spectrum_id"], 0, 0, -80))
            raises(StaleError, lambda: fft_bytes(a, fr["spectrum_id"], 0, 1e5, 100, False))
        assert a._wf(a._waves, "Mem1.CHAN1").voltage.max() == 3
        assert a._slots["Mem1"] == ["Mem1.CHAN1"]
        assert decimate.decode(wave_bytes(a, "Mem1.CHAN1", 0, 1, 100, gen))[4].max() == 3
        m, fr = measured("CHAN1"), spectrum("CHAN1")
        a.add_waveform(main, "Mem1", [])
        assert Path(export(m)["path"]).exists()
        assert a.fft_track_rf(fr["spectrum_id"], 0, 0, -80)["available"]
        assert a.remove_slot("Mem4") is None
        raises(BadRequest, lambda: a.remove_slot("Mem5"))

        # 解碼在槽內同軸可用；替換、移除使全部舊快照端點失效，主檔解碼則保留。
        bus = tmp / "匯流排.csv"
        write_csv(bus, Bus().start().header(0x30).byte_w(0xA5).stop().target_reset().render())
        a.add_waveform(str(bus), "Mem3", [])
        dp = dict(protocol="i3c", channels={"scl": "Mem3.CHAN1", "sda": "Mem3.CHAN2"},
                  thresholds={"scl": None, "sda": None}, options={})
        # 解碼計算中換槽／移除，即使 gen 不變也不能將舊來源快照寫回。
        from scope_tool.web import i3c_decode
        run = i3c_decode.run
        for change in (lambda: a.add_waveform(str(bus), "Mem3", []), lambda: a.remove_slot("Mem3")):
            a.add_waveform(str(bus), "Mem3", [])
            def interrupted_decode(*args: object, **kwargs: object) -> dict:
                result = run(*args, **kwargs)
                change()
                return result
            with patch.object(i3c_decode, "run", side_effect=interrupted_decode):
                raises(StaleError, lambda: a.decode(**dp))
            assert a._gen == gen and a._dec is None
        # 只換非基準來源也須拒絕；未使用的槽位變更則不影響結果。
        a.add_waveform(str(bus), "Mem3", [])
        a.add_waveform(str(bus), "Mem4", [])
        split = {**dp, "channels": {"scl": "Mem3.CHAN1", "sda": "Mem4.CHAN2"}}
        change = lambda: a.add_waveform(str(bus), "Mem4", [])
        with patch.object(i3c_decode, "run", side_effect=interrupted_decode):
            raises(StaleError, lambda: a.decode(**split))
        assert a._dec is None
        with patch.object(i3c_decode, "run", side_effect=interrupted_decode):
            assert a.decode(**dp)["ok"]
        # 門檻準備失敗的提早返回路徑也核對來源，不能回傳舊資料的摘要。
        from scope_tool.web import analysis_decode
        prepare = analysis_decode.prepare
        def interrupted_prepare(*args: object, **kwargs: object) -> tuple:
            edges, used, end, _ = prepare(*args, **kwargs)
            a.remove_slot("Mem3")
            return edges, used, end, "門檻失敗"
        with patch.object(analysis_decode, "prepare", side_effect=interrupted_prepare):
            raises(StaleError, lambda: a.decode(**dp))
        assert a._gen == gen and a._dec is None
        a.remove_slot("Mem4")
        a.add_waveform(str(bus), "Mem3", [])
        for change in (lambda: a.add_waveform(str(bus), "Mem3", []), lambda: a.remove_slot("Mem3")):
            ds = a.decode(**dp)
            assert ds["ok"]
            ident = ds["decode_id"]
            change()
            raises(StaleError, lambda: a.decode_frames(ident))
            raises(StaleError, lambda: a.decode_bits(ident, 0, 1))
            raises(StaleError, lambda: a.export_decode(ident, directory))
        a.open_waveform(str(bus))
        ds = a.decode("i3c", {"scl": "CHAN1", "sda": "CHAN2"}, {"scl": None, "sda": None}, {})
        a.add_waveform(main, "Mem1", [])
        a.remove_slot("Mem1")
        assert a.decode_frames(ds["decode_id"])["frames"]

        # 撞名與空波形不破壞原槽；讀檔時主檔換世代則不得寫入。
        a.add_waveform(main, "Mem1", [])
        a._waves.append(Waveform("Mem2.CHAN1", t, v))
        raises(BadRequest, lambda: a.add_waveform(main, "Mem2", []))
        assert "Mem2" not in a._slots
        with patch("scope_tool.web.analysis_slots.read_waveform_file", return_value=[]):
            raises(ScopeError, lambda: a.add_waveform(main, "Mem1", []))
        # 全空開檔／替換既有槽都須保留世代、路徑、波形物件與槽位。
        empty = [Waveform("EMPTY", np.array([]), np.array([]))]
        before_gen, before_path = a._gen, a._path
        before_waves = list(a._waves)
        before_slots = {s: list(names) for s, names in a._slots.items()}
        for module, operation in (
                ("analysis_api", lambda: a.open_waveform(other)),
                ("analysis_slots", lambda: a.add_waveform(other, "Mem1", []))):
            with patch(f"scope_tool.web.{module}.read_waveform_file", return_value=empty):
                assert str(raises(ScopeError, operation)) == "沒有波形資料可畫。"
            assert (a._gen, a._path, a._slots) == (before_gen, before_path, before_slots)
            assert len(a._waves) == len(before_waves)
            assert all(x is y for x, y in zip(a._waves, before_waves))
        # 混合空／非空通道只留下可畫資料，主檔與比對檔皆如此。
        mixed = empty + [Waveform("CH1", t, v)]
        with patch("scope_tool.web.analysis_api.read_waveform_file", return_value=mixed):
            assert [c["name"] for c in a.open_waveform(main)["channels"]] == ["CH1"]
        with patch("scope_tool.web.analysis_slots.read_waveform_file", return_value=mixed):
            summary = a.add_waveform(main, "Mem1", [])
            assert summary["all"] == ["CH1"]
            assert [c["name"] for c in summary["channels"]] == ["Mem1.CH1"]
        # 原檔的 F1／F2 不得被 Math 配號占用，刪除 F3 後也不重用。
        math_file = tmp / "math.csv"
        with math_file.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Time(s)", "F1(V)", "F2(V)"])
            writer.writerows((x, y, 1-y) for x, y in zip(t, v))
        a.open_waveform(str(math_file))
        assert a.math("反相", "F1", None, 0)["name"] == "F3"
        a.remove_channel("F3")
        assert a.math("反相", "F2", None, 0)["name"] == "F4"
        read = read_waveform_file
        for change in (lambda: a.open_waveform(main), a.close_waveform):
            a.open_waveform(main)
            def interrupted(p: Path) -> list[Waveform]:
                waves = read(p)
                change()
                return waves
            with patch("scope_tool.web.analysis_slots.read_waveform_file", side_effect=interrupted):
                raises(StaleError, lambda: a.add_waveform(main, "Mem1", []))
            assert a._slots == {}
        a.open_waveform(main)
        a.add_waveform(main, "Mem1", [])
        a.close_waveform()
        assert a._slots == {} and a._main == [] and not a._pyr
    print("analysis_slots self-check OK")
