// Mono Clock: 12-dot analog dial (red second hand) or dot-matrix digital time.
const GLib = imports.gi.GLib;
const M = require("./monolib");

class MonoClock extends M.MonoDesklet {
    constructor(metadata, deskletId) {
        super(metadata, deskletId, ["style", "seconds", "hour24"]);
    }

    get W() { return 144; }
    get H() { return 140; }

    period() { return this.seconds ? 1 : 10; }

    draw(cr, w, h, s) {
        let now = GLib.DateTime.new_now_local();
        if (this.style === "digital")
            return this.drawDigital(cr, w, h, s, now);
        let cx = w / 2, cy = h / 2, r = 52 * s;
        let accent = this.accentRGB;

        for (let i = 0; i < 12; i++) {                       // 12-dot dial
            let a = i * Math.PI / 6 - Math.PI / 2;
            let big = i % 3 === 0;
            M.dot(cr, cx + Math.cos(a) * r, cy + Math.sin(a) * r, (big ? 2.0 : 1.3) * s,
                  [1, 1, 1, big ? 1 : 0.35]);
        }
        for (let dx of [-5, 5])                              // double dot at 12
            M.dot(cr, cx + dx * s, cy - r, 1.4 * s, [1, 1, 1, 0.9]);

        let hr = now.get_hour(), mi = now.get_minute(), se = now.get_second();
        let ha = ((hr % 12) + mi / 60 + se / 3600) * Math.PI / 6 - Math.PI / 2;
        let ma = (mi + se / 60) * Math.PI / 30 - Math.PI / 2;
        cr.setLineCap(1);                                    // round
        for (let [ang, lw, len, alpha] of [[ha, 3.6, 0.50, 1], [ma, 2.0, 0.78, 0.95]]) {
            cr.setLineWidth(lw * s);
            cr.setSourceRGBA(1, 1, 1, alpha);
            cr.moveTo(cx + Math.cos(ang) * 3 * s, cy + Math.sin(ang) * 3 * s);
            cr.lineTo(cx + Math.cos(ang) * r * len, cy + Math.sin(ang) * r * len);
            cr.stroke();
        }
        if (this.seconds) {
            let sa = se * Math.PI / 30 - Math.PI / 2;
            cr.setLineWidth(1.2 * s);
            cr.setSourceRGBA(accent[0], accent[1], accent[2], 1);
            cr.moveTo(cx - Math.cos(sa) * r * 0.18, cy - Math.sin(sa) * r * 0.18);
            cr.lineTo(cx + Math.cos(sa) * r * 0.82, cy + Math.sin(sa) * r * 0.82);
            cr.stroke();
        }
        cr.setSourceRGBA(0.078, 0.078, 0.078, 1);            // hub
        cr.arc(cx, cy, 3.8 * s, 0, 2 * Math.PI);
        cr.fillPreserve();
        cr.setLineWidth(1 * s);
        cr.setSourceRGBA(1, 1, 1, 0.25);
        cr.stroke();
        M.dot(cr, cx, cy, 1.8 * s, accent);
    }

    drawDigital(cr, w, h, s, now) {
        let hh = now.format(this.hour24 ? "%H" : "%I");
        M.text(cr, hh, M.DOT_FONT, 46 * s, M.WHITE, w / 2, 12 * s, 0.5);
        M.text(cr, now.format("%M"), M.DOT_FONT, 46 * s, M.WHITE, w / 2, 66 * s, 0.5);
        if (this.seconds)
            M.text(cr, now.format("%S"), M.DOT_FONT, 14 * s, this.accentRGB, w - 16 * s, h - 26 * s, 1);
    }
}

function main(metadata, deskletId) {
    return new MonoClock(metadata, deskletId);
}
