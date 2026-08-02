/* ============================================================================
   Graphiques SVG, sans aucune bibliotheque.
   Chaque fonction rend une chaine HTML a partir de donnees deja chargees.
   ========================================================================= */
"use strict";

/** Couleur attribuee a chaque famille d'armes, reprise dans tous les visuels. */
const CATEGORY_COLORS = {
    "Fusil": "#ff6a3d",
    "Pistolet": "#6aa6dd",
    "SMG": "#4cc38a",
    "Sniper": "#c77dff",
    "Fusil a pompe": "#d9a441",
    "Mitrailleuse": "#e0655b",
    "Grenade": "#3fb6a8",
    "Corps a corps": "#8b949e",
    "Autre": "#56616f",
};

function categoryColor(name) {
    return CATEGORY_COLORS[name] || CATEGORY_COLORS.Autre;
}

/** Pictogrammes d'armes, tracés a la main en SVG (aucune image externe). */
const WEAPON_GLYPHS = {
    "Fusil": "M2 11h13l2-3h4v3h2v3h-9l-2 3H6l-1-3H2z",
    "Pistolet": "M3 8h11v4h-2l-3 6H6l1-6H3z",
    "SMG": "M2 9h12v3h-3l-1 5H7l1-5H4v3H2z",
    "Sniper": "M1 11h16l3-3h3v3h-2v3H9l-2 3H4l-1-3H1z",
    "Fusil a pompe": "M2 10h18v3h-4l-1 4h-3l1-4H2z",
    "Mitrailleuse": "M2 9h14v2h4v4h-8l-2 3H5l-1-3H2z",
    "Grenade": "M12 3h2v2h-2zM8 7h10v3a5 5 0 0 1-5 11 5 5 0 0 1-5-11z",
    "Corps a corps": "M4 20l9-9 3-8 3 3-8 3-4 9z",
};

function weaponGlyph(category, color, size = 18) {
    const path = WEAPON_GLYPHS[category] || WEAPON_GLYPHS["Fusil"];
    return `<svg class="glyph" viewBox="0 0 24 24" width="${size}" height="${size}"
                 aria-hidden="true"><path d="${path}" fill="${color}"/></svg>`;
}

/* ------------------------------------------------- silhouette des impacts */

/**
 * Repartition des eliminations par zone du corps.
 *
 * **Limite assumee** : l'API Steam ne distingue que les headshots du reste.
 * Torse, bras et jambes ne sont pas exposes — les inventer donnerait un beau
 * schema et une information fausse. La silhouette n'affiche donc que deux
 * zones, et le dit.
 */
function bodyZones(headshotRate, totalKills) {
    const hs = Math.max(0, Math.min(1, headshotRate || 0));
    const body = 1 - hs;
    const headKills = Math.round(totalKills * hs);
    const bodyKills = totalKills - headKills;

    // L'opacite traduit la part de chaque zone : lecture immediate.
    const headFill = 0.25 + hs * 0.75;
    const bodyFill = 0.25 + body * 0.75;

    return `
    <div class="zones">
        <svg viewBox="0 0 120 190" class="zones-figure" role="img"
             aria-label="Repartition des eliminations par zone">
            <!-- Tete -->
            <circle cx="60" cy="26" r="20"
                    fill="var(--flash)" fill-opacity="${headFill.toFixed(3)}"
                    stroke="var(--flash)" stroke-width="1.5"/>
            <!-- Corps : torse, bras et jambes forment une seule zone, faute de
                 donnees plus fines cote Steam. -->
            <path d="M60 50
                     C 40 50, 30 58, 28 74
                     L 24 116 L 36 118 L 40 92
                     L 38 132 L 44 186 L 56 186 L 58 136
                     L 62 136 L 64 186 L 76 186 L 82 132
                     L 80 92 L 84 118 L 96 116 L 92 74
                     C 90 58, 80 50, 60 50 Z"
                  fill="var(--ct)" fill-opacity="${bodyFill.toFixed(3)}"
                  stroke="var(--ct)" stroke-width="1.5" stroke-linejoin="round"/>
        </svg>
        <div class="zones-legend">
            <div class="zone-row">
                <span class="zone-dot" style="background:var(--flash)"></span>
                <span class="zone-name">Tete</span>
                <span class="zone-val">${(hs * 100).toFixed(1)} %</span>
                <span class="zone-sub">${formatInt(headKills)} kills</span>
            </div>
            <div class="zone-row">
                <span class="zone-dot" style="background:var(--ct)"></span>
                <span class="zone-name">Reste du corps</span>
                <span class="zone-val">${(body * 100).toFixed(1)} %</span>
                <span class="zone-sub">${formatInt(bodyKills)} kills</span>
            </div>
            <p class="zones-note">
                Steam ne distingue que la tete du reste du corps. Le detail
                torse / bras / jambes n'existe pas dans son API.
            </p>
        </div>
    </div>`;
}

/* ----------------------------------------------------- barres horizontales */

/** Classement en barres : armes les plus utilisees, cartes les plus jouees. */
function barList(items, options = {}) {
    const { unit = "", limit = 10, showGlyph = false } = options;
    const shown = items.slice(0, limit);
    if (!shown.length) {
        return `<p class="paste-help">Aucune donnee.</p>`;
    }
    const max = Math.max(...shown.map((item) => item.value)) || 1;

    return `<div class="bars">${shown
        .map((item) => {
            const width = (item.value / max) * 100;
            const color = item.color || "var(--flash)";
            const glyph = showGlyph ? weaponGlyph(item.category, color, 15) : "";
            return `
            <div class="bar-row">
                <span class="bar-label">${glyph}${escapeHtml(item.label)}</span>
                <span class="bar-track">
                    <span class="bar-fill" style="width:${width.toFixed(1)}%;background:${color}"></span>
                </span>
                <span class="bar-value">${formatInt(item.value)}${unit}</span>
            </div>`;
        })
        .join("")}</div>`;
}

/* --------------------------------------------------------------- anneau */

/** Anneau de repartition — par exemple les kills par famille d'armes. */
function donut(slices, centerLabel, centerValue) {
    const total = slices.reduce((sum, slice) => sum + slice.value, 0);
    if (!total) return `<p class="paste-help">Aucune donnee.</p>`;

    const R = 54;
    const C = 2 * Math.PI * R;
    let offset = 0;

    const arcs = slices
        .map((slice) => {
            const fraction = slice.value / total;
            const dash = `${(fraction * C).toFixed(2)} ${(C - fraction * C).toFixed(2)}`;
            const arc = `
            <circle cx="70" cy="70" r="${R}" fill="none"
                    stroke="${slice.color}" stroke-width="17"
                    stroke-dasharray="${dash}"
                    stroke-dashoffset="${(-offset * C).toFixed(2)}"
                    transform="rotate(-90 70 70)">
                <title>${escapeHtml(slice.label)} — ${(fraction * 100).toFixed(1)} %</title>
            </circle>`;
            offset += fraction;
            return arc;
        })
        .join("");

    const legend = slices
        .map((slice) => `
        <div class="donut-row">
            <span class="zone-dot" style="background:${slice.color}"></span>
            <span class="donut-name">${escapeHtml(slice.label)}</span>
            <span class="donut-val">${((slice.value / total) * 100).toFixed(1)} %</span>
        </div>`)
        .join("");

    return `
    <div class="donut">
        <svg viewBox="0 0 140 140" class="donut-figure" role="img"
             aria-label="${escapeHtml(centerLabel)}">
            <circle cx="70" cy="70" r="${R}" fill="none"
                    stroke="var(--void)" stroke-width="17"/>
            ${arcs}
            <text x="70" y="66" class="donut-center">${escapeHtml(centerValue)}</text>
            <text x="70" y="82" class="donut-caption">${escapeHtml(centerLabel)}</text>
        </svg>
        <div class="donut-legend">${legend}</div>
    </div>`;
}

/* ----------------------------------------------------------------- radar */

/**
 * Radar de precision par famille d'armes, compare a la moyenne.
 *
 * Le polygone gris est la reference de population, le polygone orange le
 * joueur : l'ecart se lit d'un coup d'oeil, sans chiffre a interpreter.
 */
function radar(axes) {
    if (axes.length < 3) return "";

    // La zone de dessin est plus large que haute : la marge laterale accueille
    // des libelles comme « MITRAILLEUSE », qui seraient sinon rognes.
    const width = 340;
    const height = 260;
    const cx = width / 2;
    const cy = height / 2;
    const radius = 80;

    const point = (index, ratio) => {
        const angle = (index / axes.length) * Math.PI * 2 - Math.PI / 2;
        const r = Math.max(0.05, Math.min(1.35, ratio)) * radius;
        return [cx + Math.cos(angle) * r, cy + Math.sin(angle) * r];
    };

    const polygon = (values) =>
        values.map((v, i) => point(i, v).map((n) => n.toFixed(1)).join(",")).join(" ");

    const rings = [0.25, 0.5, 0.75, 1]
        .map((ratio) => `<circle cx="${cx}" cy="${cy}" r="${(radius * ratio).toFixed(1)}"
                                 fill="none" stroke="var(--line)" stroke-width="1"/>`)
        .join("");

    const spokes = axes
        .map((_axis, index) => {
            const [x, y] = point(index, 1);
            return `<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}"
                          y2="${y.toFixed(1)}" stroke="var(--line)" stroke-width="1"/>`;
        })
        .join("");

    const labels = axes
        .map((axis, index) => {
            const [x, y] = point(index, 1.22);
            return `<text x="${x.toFixed(1)}" y="${(y + 3).toFixed(1)}"
                          text-anchor="${textAnchor(x, cx)}"
                          class="radar-label">${escapeHtml(axis.label)}</text>`;
        })
        .join("");

    return `
    <svg viewBox="0 0 ${width} ${height}" class="radar" role="img"
         aria-label="Precision par famille d'armes">
        ${rings}${spokes}
        <polygon points="${polygon(axes.map(() => 1))}"
                 fill="var(--ash)" fill-opacity="0.10"
                 stroke="var(--line-2)" stroke-width="1" stroke-dasharray="3 3"/>
        <polygon points="${polygon(axes.map((a) => a.ratio))}"
                 fill="var(--flash)" fill-opacity="0.18"
                 stroke="var(--flash)" stroke-width="2" stroke-linejoin="round"/>
        ${axes.map((axis, index) => {
            const [x, y] = point(index, axis.ratio);
            return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.2"
                            fill="var(--flash)" stroke="var(--plate)" stroke-width="1.5"/>`;
        }).join("")}
        ${labels}
    </svg>`;
}

/* --------------------------------------------------------------- utilitaires */

/** Ancrage d'un libelle selon sa position par rapport au centre. */
function textAnchor(x, center) {
    if (Math.abs(x - center) < 14) return "middle";
    return x > center ? "start" : "end";
}

function escapeHtml(text) {
    return String(text).replace(/[<>&"]/g, (c) =>
        ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[c]));
}

function formatInt(value) {
    if (value === null || value === undefined) return "—";
    return Math.round(Number(value)).toLocaleString("fr-FR").replace(/[ ,]/g, " ");
}
