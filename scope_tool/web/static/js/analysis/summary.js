/** 後端目錄可能尚未列出此模式；永遠只加一個且禁用。 */
export function disableTrackMeasurements(select) {
  let option = [...(select.options ?? select.children)].find(o => o.value === 'Track Measurements');
  if (!option) { option = new Option('Track Measurements','Track Measurements'); select.append(option); }
  option.disabled = true; option.title = '需先補後端事件座標，暫未提供';
}
