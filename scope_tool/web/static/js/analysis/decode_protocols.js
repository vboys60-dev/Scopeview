// 協定註冊；各協定只追加自己的匯出。
export { default as i3c } from './decode_i3c.js';
export { default as i2c } from './decode_i2c.js';
export { default as uart } from './decode_uart.js';
export { default as spi } from './decode_spi.js';
export { default as can } from './decode_can.js';
export { default as espi } from './decode_espi.js';
