export const titleCase = function (string) {
    return string[0].toUpperCase() + string.slice(1).toLowerCase();
};

export const lightenDarkenColor = function(col, amt) {
    let num = parseInt(col, 16);
    let r = Math.max(Math.min((num >> 16) * amt, 255), 0);
    let g = Math.max(Math.min((num & 0x0000FF) * amt), 0);
    let b = Math.max(Math.min(((num >> 8) & 0x00FF) * amt), 0);
    let newColor = g | (b << 8) | (r << 16);
    return newColor.toString(16);
};

/**
 * Determines luma
 * true - bright color
 * false - dark color
 * @param {string} col Color in hex format
 * @returns {bool}
 */
export const determineLuma = function(col) {
    let num = parseInt(col, 16);
    let r = (num >> 16);
    let g = num & 0x0000FF;
    let b = (num >> 8) & 0x00FF;
    let luma = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    if (luma >= 100) {
        return true;
    }
    return false;
};

/**
 *
 * @param {string} str
 * @returns
 */
export const subUnderscores = function(str) {
    return str.replace("_", " ");
};

export const sanitizeSelector = function (str) {
    return str.replaceAll(/[/.]/g, "_");
};
