// Mono Weather: temperature, condition and place from wttr.in (no API key needed).
const GLib = imports.gi.GLib;
const Soup = imports.gi.Soup;
const M = require("./monolib");

class MonoWeather extends M.MonoDesklet {
    constructor(metadata, deskletId) {
        super(metadata, deskletId, ["location", "units", "refresh"]);
    }

    get W() { return 144; }
    get H() { return 140; }

    period() { return Math.max(10, this.refresh) * 60; }

    onSettingsChanged() {
        this.data = this.data || null;
        this.fetch();
    }

    tick() { this.fetch(); }

    fetch() {
        if (!this.session)
            this.session = new Soup.Session({ timeout: 15, user_agent: "monotile-desklet" });
        let loc = encodeURIComponent((this.location || "").trim());
        let msg = Soup.Message.new("GET", `https://wttr.in/${loc}?format=j1`);
        if (!msg)
            return;
        this.session.send_and_read_async(msg, GLib.PRIORITY_LOW, null, (session, res) => {
            try {
                let bytes = session.send_and_read_finish(res);
                if (msg.get_status() !== 200)
                    throw new Error("HTTP " + msg.get_status());
                let j = JSON.parse(imports.byteArray.toString(bytes.get_data()));
                let cur = j.current_condition[0];
                let area = (j.nearest_area && j.nearest_area[0]) || {};
                this.data = {
                    C: cur.temp_C, F: cur.temp_F,
                    cond: (cur.weatherDesc && cur.weatherDesc[0].value) || "",
                    place: (area.areaName && area.areaName[0].value) || (this.location || ""),
                };
                this.error = null;
            } catch (e) {
                this.error = "offline";
            }
            if (this.area)
                this.area.queue_repaint();
        });
    }

    draw(cr, w, h, s) {
        M.text(cr, "WEATHER", M.TEXT_FONT, 12 * s, M.MUTED, 18 * s, 16 * s);
        let d = this.data;
        let temp = d ? `${this.units === "F" ? d.F : d.C}°` : "--";
        M.text(cr, temp, M.DOT_FONT, 44 * s, M.WHITE, 16 * s, 40 * s);
        let cond = d ? d.cond : (this.error || "loading");
        M.text(cr, cond.length > 16 ? cond.slice(0, 15) + "…" : cond, M.TEXT_FONT, 11 * s, [1, 1, 1, 0.85], 18 * s, 94 * s);
        if (d && d.place)
            M.text(cr, d.place.toUpperCase().slice(0, 16), M.TEXT_FONT, 10 * s, M.MUTED, 18 * s, 112 * s);
    }

    onRemoved() {
        if (this.session)
            this.session.abort();
    }
}

function main(metadata, deskletId) {
    return new MonoWeather(metadata, deskletId);
}
