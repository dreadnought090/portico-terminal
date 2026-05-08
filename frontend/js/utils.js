// Portico utils — pure number/formatter helpers. Loaded before app.js.
// All functions are global (window-scope) to keep current call sites working.
// No side effects, no DOM access.

function fmt(num) {
    if (num === null || num === undefined || isNaN(num)) return '-';
    return numeral(Math.round(num)).format('0,0');
}
function fmtRp(num) {
    if (num === null || num === undefined || isNaN(num)) return 'Rp -';
    return 'Rp ' + numeral(Math.round(num)).format('0,0');
}
function fmtPct(num) {
    if (num === null || num === undefined || isNaN(num)) return '-';
    return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`;
}
function fmtChange(num) {
    if (num === null || num === undefined || isNaN(num)) return '-';
    return `${num >= 0 ? '+' : ''}${fmt(num)}`;
}
function pnlClass(num) {
    if (num > 0) return 'positive';
    if (num < 0) return 'negative';
    return 'neutral';
}
function fmtBigNum(num) {
    if (!num || num === 0) return '-';
    const abs = Math.abs(num);
    const sign = num < 0 ? '-' : '';
    if (abs >= 1e12) return `${sign}Rp ${numeral(abs / 1e12).format('0.0')}T`;
    if (abs >= 1e9)  return `${sign}Rp ${numeral(abs / 1e9).format('0.0')}M`;
    if (abs >= 1e6)  return `${sign}Rp ${numeral(abs / 1e6).format('0.0')}Jt`;
    return fmtRp(num);
}
function fmtPctVal(num) {
    if (num === null || num === undefined || num === 0) return '-';
    // TradingView & yfinance return margins/ratios as decimals (0.15 = 15%)
    // Values > 1 or < -1 are already in percentage form (e.g., growth 120%)
    if (Math.abs(num) <= 1) return numeral(num * 100).format('0.00') + '%';
    return numeral(num).format('0.00') + '%';
}
function fmtDecimal(num, d = 2) {
    if (!num) return '-';
    return numeral(num).format('0.' + '0'.repeat(d));
}
