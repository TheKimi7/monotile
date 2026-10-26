// Mono Date: weekday, dot-matrix day number and month.
const GLib = imports.gi.GLib;
const M = require("./monolib");

class MonoDate extends M.MonoDesklet {
    constructor(metadata, deskletId) {
        super(metadata, deskletId, ["weekend-accent", "show-year"]);
    }

    get W() { return 144; }
    get H() { return 140; }

    period() { return 60; }

    draw(cr, w, h, s) {
        let now = GLib.DateTime.new_now_local();
        let weekend = now.get_day_of_week() >= 6;
        let dayColour = weekend && this.weekend_accent ? this.accentRGB : M.MUTED;
        M.text(cr, now.format("%A").toUpperCase(), M.TEXT_FONT, 12 * s, dayColour, 18 * s, 16 * s);
        M.text(cr, now.format("%d"), M.DOT_FONT, 56 * s, M.ink(), 16 * s, 36 * s);
        let month = now.format("%B").toUpperCase();
        if (this.show_year) {
            M.text(cr, month, M.TEXT_FONT, 12 * s, M.ink(0.85), 18 * s, 96 * s);
            M.text(cr, now.format("%Y"), M.TEXT_FONT, 12 * s, M.MUTED, 18 * s, 112 * s);
        } else {
            M.text(cr, month, M.TEXT_FONT, 12 * s, M.ink(0.85), 18 * s, 106 * s);
        }
    }
}

function main(metadata, deskletId) {
    return new MonoDate(metadata, deskletId);
}
