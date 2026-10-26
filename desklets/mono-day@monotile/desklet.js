// Mono Day: 24 dots for the hours of the day (or 12 for the months of the year).
const GLib = imports.gi.GLib;
const M = require("./monolib");

class MonoDay extends M.MonoDesklet {
    constructor(metadata, deskletId) {
        super(metadata, deskletId, ["mode"]);
    }

    get W() { return 300; }
    get H() { return 92; }

    period() { return 60; }

    draw(cr, w, h, s) {
        let now = GLib.DateTime.new_now_local();
        let n, cur, pct, title, sub;
        if (this.mode === "year") {
            let leap = GLib.Date.is_leap_year(now.get_year());
            let days = leap ? 366 : 365, doy = now.get_day_of_year() - 1;
            n = 12; cur = now.get_month() - 1;
            pct = Math.floor(100 * doy / days);
            title = "YEAR"; sub = `${days - doy} days left`;
        } else {
            let mins = now.get_hour() * 60 + now.get_minute();
            n = 24; cur = now.get_hour();
            pct = Math.floor(100 * mins / 1440);
            title = "DAY"; sub = `${Math.floor((1440 - mins) / 60)}h ${(1440 - mins) % 60}m left`;
        }
        M.text(cr, title, M.TEXT_FONT, 12 * s, M.MUTED, 18 * s, 14 * s);
        M.text(cr, `${pct}%`, M.DOT_FONT, 18 * s, M.ink(), w - 18 * s, 10 * s, 1);
        let left = 22 * s, right = w - 22 * s, step = (right - left) / (n - 1);
        let radius = (n === 24 ? 4.2 : 6) * s;
        for (let i = 0; i < n; i++) {
            let c = i < cur ? M.ink() : i === cur ? this.accentRGB : M.ink(0.15);
            M.dot(cr, left + i * step, 52 * s, radius, c);
        }
        M.text(cr, sub, M.TEXT_FONT, 10 * s, M.MUTED, 18 * s, 66 * s);
    }
}

function main(metadata, deskletId) {
    return new MonoDay(metadata, deskletId);
}
