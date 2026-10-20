// Shared look and helpers for the Mono desklets (copied into each desklet by install.sh).
const St = imports.gi.St;
const Clutter = imports.gi.Clutter;
const GLib = imports.gi.GLib;
const Gio = imports.gi.Gio;
const PangoCairo = imports.gi.PangoCairo;
const Pango = imports.gi.Pango;

var DOT_FONT = "Ndot 57";
var TEXT_FONT = "JetBrains Mono";

// Panacea / Nothing card: near-black, hairline border, generous radius
function cardStyle(scale, opacity) {
    let a = Math.max(0, Math.min(100, opacity)) / 100;
    return `background-color: rgba(23,23,23,${(0.96 * a).toFixed(3)});` +
        `border: 1px solid rgba(255,255,255,${(0.06 * a).toFixed(3)});` +
        `border-radius: ${Math.round(22 * scale)}px;`;
}

// Fixed-size card holding a drawing area that fills it.
function makeCard(w, h, scale, opacity, onRepaint) {
    let card = new St.Widget({ style: cardStyle(scale, opacity), reactive: false,
                               layout_manager: new Clutter.BinLayout() });
    card.set_size(Math.round(w * scale), Math.round(h * scale));
    let area = new St.DrawingArea({ x_expand: true, y_expand: true });
    area.connect("repaint", (a) => {
        let cr = a.get_context();
        try {
            onRepaint(cr, a.get_width(), a.get_height());
        } catch (e) {
            global.logError(e);
        }
        cr.$dispose();
    });
    card.add_child(area);
    return [card, area];
}

// "#rrggbb" / "rgb(r,g,b)" / "rgba(...)" -> [r,g,b] in 0..1
function parseColor(s, fallback) {
    let m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i.exec(s || "");
    if (m)
        return [parseInt(m[1], 16) / 255, parseInt(m[2], 16) / 255, parseInt(m[3], 16) / 255];
    m = /rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i.exec(s || "");
    if (m)
        return [m[1] / 255, m[2] / 255, m[3] / 255];
    return fallback || [0.843, 0.098, 0.129];
}

// Draw text with Pango; align: 0 left, 0.5 centre, 1 right. Returns [w, h].
function text(cr, str, font, px, rgba, x, y, align) {
    let layout = PangoCairo.create_layout(cr);
    let fd = Pango.FontDescription.from_string(font);
    fd.set_family(font);                 // "Ndot 57" must stay a family name, not "Ndot" at 57pt
    fd.set_absolute_size(px * Pango.SCALE);
    layout.set_font_description(fd);
    layout.set_text(str, -1);
    let [w, h] = layout.get_pixel_size();
    cr.setSourceRGBA(rgba[0], rgba[1], rgba[2], rgba.length > 3 ? rgba[3] : 1);
    cr.moveTo(x - w * (align || 0), y);
    PangoCairo.show_layout(cr, layout);
    return [w, h];
}

function dot(cr, x, y, r, rgba) {
    cr.setSourceRGBA(rgba[0], rgba[1], rgba[2], rgba.length > 3 ? rgba[3] : 1);
    cr.arc(x, y, r, 0, 2 * Math.PI);
    cr.fill();
}

var WHITE = [1, 1, 1, 1];
var MUTED = [0.53, 0.53, 0.53, 1];

// Timer helpers that are safe to clear twice.
function every(seconds, fn) {
    return GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, seconds, () => { fn(); return GLib.SOURCE_CONTINUE; });
}

function clear(id) {
    if (id)
        GLib.source_remove(id);
    return 0;
}

function readFile(path) {
    try {
        let [ok, bytes] = GLib.file_get_contents(path);
        return ok ? imports.byteArray.toString(bytes) : "";
    } catch (e) {
        return "";
    }
}

function ramPercent() {
    let info = {};
    for (let line of readFile("/proc/meminfo").split("\n")) {
        let m = /^(\w+):\s+(\d+)/.exec(line);
        if (m) info[m[1]] = parseInt(m[2]);
    }
    return info.MemTotal ? 100 * (1 - info.MemAvailable / info.MemTotal) : 0;
}

function diskPercent(path) {
    try {
        let f = Gio.File.new_for_path(path || "/");
        let i = f.query_filesystem_info("filesystem::size,filesystem::free", null);
        let size = i.get_attribute_uint64("filesystem::size");
        let free = i.get_attribute_uint64("filesystem::free");
        return size ? 100 * (1 - free / size) : 0;
    } catch (e) {
        return 0;
    }
}

// CPU usage between successive calls
var _cpuPrev = null;
function cpuPercent() {
    let line = readFile("/proc/stat").split("\n")[0].trim().split(/\s+/).slice(1).map(Number);
    let idle = line[3] + (line[4] || 0), total = line.reduce((a, b) => a + b, 0);
    let pct = 0;
    if (_cpuPrev) {
        let dt = total - _cpuPrev[1], di = idle - _cpuPrev[0];
        pct = dt > 0 ? 100 * (1 - di / dt) : 0;
    }
    _cpuPrev = [idle, total];
    return pct;
}

// ---------------------------------------------------------------- base desklet
const Desklet = imports.ui.desklet;
const Settings = imports.ui.settings;

// Subclasses set this.W / this.H (unscaled card size), list their own setting keys
// in `keys`, implement draw(cr, w, h, s) and optionally period() / tick().
var MonoDesklet = class MonoDesklet extends Desklet.Desklet {
    constructor(metadata, deskletId, keys) {
        super(metadata, deskletId);
        this._timer = 0;
        this.settings = new Settings.DeskletSettings(this, metadata.uuid, deskletId);
        for (let key of ["scale", "opacity", "accent"].concat(keys || []))
            this.settings.bind(key, key.replace(/-/g, "_"), () => this._rebuild());
        this._rebuild();
    }

    get accentRGB() {
        return parseColor(this.accent);
    }

    _rebuild() {
        [this.card, this.area] = makeCard(this.W, this.H, this.scale, this.opacity,
            (cr, w, h) => this.draw(cr, w, h, w / this.W));
        this.setContent(this.card);
        this.onSettingsChanged();
        this._restart();
    }

    _restart() {
        this._timer = clear(this._timer);
        this._timer = every(this.period(), () => this.tick());
    }

    on_desklet_added_to_desktop() {
        this._restart();
    }

    on_desklet_removed() {
        this._timer = clear(this._timer);
        this.onRemoved();
    }

    period() { return 60; }
    tick() { this.area.queue_repaint(); }
    onSettingsChanged() {}
    onRemoved() {}
};
