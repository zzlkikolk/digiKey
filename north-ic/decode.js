var _PADCHAR = "=";
var _ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
function login_prot(strpwd) {
    var strRandom = lp_randomString();
    var timestamp = Date.parse(new Date) / 1000;
    var password = _bs(strpwd, strRandom, timestamp);
    return {
        "random": strRandom,
        "timestamp": timestamp,
        "pwd": password
    }
}
function lp_randomString(len) {
    var strRandom = "";
    len = len || 32;
    var maxPos = _ALPHA.length;
    for (i = 0; i < len; i++) {
        strRandom += _ALPHA.charAt(Math.floor(Math.random() * maxPos))
    }
    return strRandom
}
function _get_chars(ch, y) {
    if (ch < 128)
        y.push(ch);
    else if (ch < 2048) {
        y.push(192 + (ch >> 6 & 31));
        y.push(128 + (ch & 63))
    } else {
        y.push(224 + (ch >> 12 & 15));
        y.push(128 + (ch >> 6 & 63));
        y.push(128 + (ch & 63))
    }
}
function _bs(s, r, t) {
    s = String(s);
    if (s.length === 0) {
        return s
    } else {
        var l = s.length * chrsz;
        var s = bbh(c_w(sbb(s, 1), l)) + t + s + bbh(c_h(sbb(r), r.length * chrsz), 1);
        s = bbh(c_w(sbb(s, 1), s.length * chrsz))
    }
    var i = 0;
    var b10 = 0;
    var y = [];
    var x = [];
    var len = s.length;
    while (i < len) {
        _get_chars(s.charCodeAt(i), y);
        while (y.length >= 3) {
            var ch1 = y.shift();
            var ch2 = y.shift();
            var ch3 = y.shift();
            b10 = ch1 << 16 | ch2 << 8 | ch3;
            x.push(_ALPHA.charAt(b10 >> 18));
            x.push(_ALPHA.charAt(b10 >> 12 & 63));
            x.push(_ALPHA.charAt(b10 >> 6 & 63));
            x.push(_ALPHA.charAt(b10 & 63))
        }
        i++
    }
    switch (y.length) {
    case 1:
        var ch = y.shift();
        b10 = ch << 16;
        x.push(_ALPHA.charAt(b10 >> 18) + _ALPHA.charAt(b10 >> 12 & 63) + _PADCHAR + _PADCHAR);
        break;
    case 2:
        var ch1 = y.shift();
        var ch2 = y.shift();
        b10 = ch1 << 16 | ch2 << 8;
        x.push(_ALPHA.charAt(b10 >> 18) + _ALPHA.charAt(b10 >> 12 & 63) + _ALPHA.charAt(b10 >> 6 & 63) + _PADCHAR);
        break;
    }
    return x.join("")
}
var hexcase = 0;
var b64pad = "";
var chrsz = 8;
function c_w(x, len) {
    x[len >> 5] |= 128 << len % 32;
    x[(len + 64 >>> 9 << 4) + 14] = len;
    var a = 1732584193;
    var b = -271733879;
    var c = -1732584194;
    var d = 271733878;
    for (var i = 0; i < x.length; i += 16) {
        var olda = a;
        var oldb = b;
        var oldc = c;
        var oldd = d;
        a = m_ff(a, b, c, d, x[i + 0], 7, -680876936);
        d = m_ff(d, a, b, c, x[i + 1], 12, -389564586);
        c = m_ff(c, d, a, b, x[i + 2], 17, 606105819);
        b = m_ff(b, c, d, a, x[i + 3], 22, -1044525330);
        a = m_ff(a, b, c, d, x[i + 4], 7, -176418897);
        d = m_ff(d, a, b, c, x[i + 5], 12, 1200080426);
        c = m_ff(c, d, a, b, x[i + 6], 17, -1473231341);
        b = m_ff(b, c, d, a, x[i + 7], 22, -45705983);
        a = m_ff(a, b, c, d, x[i + 8], 7, 1770035416);
        d = m_ff(d, a, b, c, x[i + 9], 12, -1958414417);
        c = m_ff(c, d, a, b, x[i + 10], 17, -42063);
        b = m_ff(b, c, d, a, x[i + 11], 22, -1990404162);
        a = m_ff(a, b, c, d, x[i + 12], 7, 1804603682);
        d = m_ff(d, a, b, c, x[i + 13], 12, -40341101);
        c = m_ff(c, d, a, b, x[i + 14], 17, -1502002290);
        b = m_ff(b, c, d, a, x[i + 15], 22, 1236535329);
        a = m_gg(a, b, c, d, x[i + 1], 5, -165796510);
        d = m_gg(d, a, b, c, x[i + 6], 9, -1069501632);
        c = m_gg(c, d, a, b, x[i + 11], 14, 643717713);
        b = m_gg(b, c, d, a, x[i + 0], 20, -373897302);
        a = m_gg(a, b, c, d, x[i + 5], 5, -701558691);
        d = m_gg(d, a, b, c, x[i + 10], 9, 38016083);
        c = m_gg(c, d, a, b, x[i + 15], 14, -660478335);
        b = m_gg(b, c, d, a, x[i + 4], 20, -405537848);
        a = m_gg(a, b, c, d, x[i + 9], 5, 568446438);
        d = m_gg(d, a, b, c, x[i + 14], 9, -1019803690);
        c = m_gg(c, d, a, b, x[i + 3], 14, -187363961);
        b = m_gg(b, c, d, a, x[i + 8], 20, 1163531501);
        a = m_gg(a, b, c, d, x[i + 13], 5, -1444681467);
        d = m_gg(d, a, b, c, x[i + 2], 9, -51403784);
        c = m_gg(c, d, a, b, x[i + 7], 14, 1735328473);
        b = m_gg(b, c, d, a, x[i + 12], 20, -1926607734);
        a = m_hh(a, b, c, d, x[i + 5], 4, -378558);
        d = m_hh(d, a, b, c, x[i + 8], 11, -2022574463);
        c = m_hh(c, d, a, b, x[i + 11], 16, 1839030562);
        b = m_hh(b, c, d, a, x[i + 14], 23, -35309556);
        a = m_hh(a, b, c, d, x[i + 1], 4, -1530992060);
        d = m_hh(d, a, b, c, x[i + 4], 11, 1272893353);
        c = m_hh(c, d, a, b, x[i + 7], 16, -155497632);
        b = m_hh(b, c, d, a, x[i + 10], 23, -1094730640);
        a = m_hh(a, b, c, d, x[i + 13], 4, 681279174);
        d = m_hh(d, a, b, c, x[i + 0], 11, -358537222);
        c = m_hh(c, d, a, b, x[i + 3], 16, -722521979);
        b = m_hh(b, c, d, a, x[i + 6], 23, 76029189);
        a = m_hh(a, b, c, d, x[i + 9], 4, -640364487);
        d = m_hh(d, a, b, c, x[i + 12], 11, -421815835);
        c = m_hh(c, d, a, b, x[i + 15], 16, 530742520);
        b = m_hh(b, c, d, a, x[i + 2], 23, -995338651);
        a = m_ii(a, b, c, d, x[i + 0], 6, -198630844);
        d = m_ii(d, a, b, c, x[i + 7], 10, 1126891415);
        c = m_ii(c, d, a, b, x[i + 14], 15, -1416354905);
        b = m_ii(b, c, d, a, x[i + 5], 21, -57434055);
        a = m_ii(a, b, c, d, x[i + 12], 6, 1700485571);
        d = m_ii(d, a, b, c, x[i + 3], 10, -1894986606);
        c = m_ii(c, d, a, b, x[i + 10], 15, -1051523);
        b = m_ii(b, c, d, a, x[i + 1], 21, -2054922799);
        a = m_ii(a, b, c, d, x[i + 8], 6, 1873313359);
        d = m_ii(d, a, b, c, x[i + 15], 10, -30611744);
        c = m_ii(c, d, a, b, x[i + 6], 15, -1560198380);
        b = m_ii(b, c, d, a, x[i + 13], 21, 1309151649);
        a = m_ii(a, b, c, d, x[i + 4], 6, -145523070);
        d = m_ii(d, a, b, c, x[i + 11], 10, -1120210379);
        c = m_ii(c, d, a, b, x[i + 2], 15, 718787259);
        b = m_ii(b, c, d, a, x[i + 9], 21, -343485551);
        a = safe_add(a, olda);
        b = safe_add(b, oldb);
        c = safe_add(c, oldc);
        d = safe_add(d, oldd)
    }
    return Array(a, b, c, d)
}
function m_cmn(q, a, b, x, s, t) {
    return safe_add(rl(safe_add(safe_add(a, q), safe_add(x, t)), s), b)
}
function m_ff(a, b, c, d, x, s, t) {
    return m_cmn(b & c | ~b & d, a, b, x, s, t)
}
function m_gg(a, b, c, d, x, s, t) {
    return m_cmn(b & d | c & ~d, a, b, x, s, t)
}
function m_hh(a, b, c, d, x, s, t) {
    return m_cmn(b ^ c ^ d, a, b, x, s, t)
}
function m_ii(a, b, c, d, x, s, t) {
    return m_cmn(c ^ (b | ~d), a, b, x, s, t)
}
function safe_add(x, y) {
    var lsw = (x & 65535) + (y & 65535);
    var msw = (x >> 16) + (y >> 16) + (lsw >> 16);
    return msw << 16 | lsw & 65535
}
function rl(num, cnt) {
    return num << cnt | num >>> 32 - cnt
}
function h_kt(t) {
    return t < 20 ? 1518500249 : t < 40 ? 1859775393 : t < 60 ? -1894007588 : -899497514
}
function h_ft(t, b, c, d) {
    if (t < 20)
        return b & c | ~b & d;
    if (t < 40)
        return b ^ c ^ d;
    if (t < 60)
        return b & c | b & d | c & d;
    return b ^ c ^ d
}
function sbb(str) {
    var a = arguments[1] ? arguments[1] : 0;
    var bin = Array();
    var mask = (1 << chrsz) - 1;
    for (var i = 0; i < str.length * chrsz; i += chrsz)
        bin[i >> 5] |= (str.charCodeAt(i / chrsz) & mask) << (!!a ? i % 32 : 24 - i % 32);
    return bin
}
function bbh(binarray) {
    var a = arguments[1] ? arguments[1] : 0;
    var hex_tab = hexcase ? "0123456789ABCDEF" : "0123456789abcdef";
    var str = "";
    for (var i = 0; i < binarray.length * 4; i++) {
        str += hex_tab.charAt(binarray[i >> 2] >> (!!a ? 3 - i % 4 : i % 4) * 8 + 4 & 15) + hex_tab.charAt(binarray[i >> 2] >> (!!a ? 3 - i % 4 : i % 4) * 8 & 15)
    }
    return str
}
function c_h(x, len) {
    x[len >> 5] |= 128 << 24 - len % 32;
    x[(len + 64 >> 9 << 4) + 15] = len;
    var w = Array(80);
    var a = 1732584193;
    var b = -271733879;
    var c = -1732584194;
    var d = 271733878;
    var e = -1009589776;
    for (var i = 0; i < x.length; i += 16) {
        var olda = a;
        var oldb = b;
        var oldc = c;
        var oldd = d;
        var olde = e;
        for (var j = 0; j < 80; j++) {
            if (j < 16)
                w[j] = x[i + j];
            else
                w[j] = rl(w[j - 3] ^ w[j - 8] ^ w[j - 14] ^ w[j - 16], 1);
            var t = safe_add(safe_add(rl(a, 5), h_ft(j, b, c, d)), safe_add(safe_add(e, w[j]), h_kt(j)));
            e = d;
            d = c;
            c = rl(b, 30);
            b = a;
            a = t
        }
        a = safe_add(a, olda);
        b = safe_add(b, oldb);
        c = safe_add(c, oldc);
        d = safe_add(d, oldd);
        e = safe_add(e, olde)
    }
    return Array(a, b, c, d, e)
}
