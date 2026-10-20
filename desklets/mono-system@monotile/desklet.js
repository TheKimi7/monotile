// Mono System: concentric RAM (outer) and disk (inner) rings with a number in the middle.
const M = require("./monolib");

class MonoSystem extends M.MonoDesklet {
    constructor(metadata, deskletId) {
        super(metadata, deskletId, ["center", "disk-path", "refresh"]);
    }

    get W() { return 144; }
    get H() { return 140; }

    period() { return Math.max(1, this.refresh); }

    tick() {
        this.ram = M.ramPercent();
        this.disk = M.diskPercent(this.disk_path);
        this.cpu = M.cpuPercent();
        this.area.queue_repaint();
    }

    onSettingsChanged() {
        this.tick();
    }

    draw(cr, w, h, s) {
        let cx = w / 2, cy = h / 2, accent = this.accentRGB;
        let rings = [[48, this.ram || 0], [38, this.disk || 0]];
        cr.setLineCap(1);
        for (let [r, pct] of rings) {
            cr.setLineWidth(5 * s);
            cr.setSourceRGBA(1, 1, 1, 0.08);
            cr.arc(cx, cy, r * s, 0, 2 * Math.PI);
            cr.stroke();
            let c = pct >= 90 ? accent : [1, 1, 1];          // red only when nearly full
            cr.setSourceRGBA(c[0], c[1], c[2], 1);
            cr.arc(cx, cy, r * s, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * Math.min(pct, 100) / 100);
            cr.stroke();
        }
        let value = { ram: this.ram, cpu: this.cpu, disk: this.disk }[this.center] || 0;
        let label = { ram: "RAM", cpu: "CPU", disk: "DISK" }[this.center] || "RAM";
        M.text(cr, `${Math.round(value)}`, M.DOT_FONT, 26 * s, M.WHITE, cx, cy - 20 * s, 0.5);
        M.text(cr, label, M.TEXT_FONT, 9 * s, M.MUTED, cx, cy + 10 * s, 0.5);
    }
}

function main(metadata, deskletId) {
    return new MonoSystem(metadata, deskletId);
}
