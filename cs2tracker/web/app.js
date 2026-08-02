/* ============================================================================
   CS2 Tracker — client de l'API locale.
   Aucune dependance externe : l'application doit fonctionner hors ligne.
   ========================================================================= */
"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

/* ------------------------------------------------------------------- reseau */

/** Appelle l'API en respectant l'enveloppe { success, data, error }. */
async function api(path, { method = "GET", body = null, params = null } = {}) {
    const url = new URL(path, window.location.origin);
    if (params) {
        for (const [key, value] of Object.entries(params)) {
            if (value !== null && value !== undefined) url.searchParams.set(key, value);
        }
    }

    let response;
    try {
        response = await fetch(url, {
            method,
            headers: body ? { "Content-Type": "application/json" } : {},
            body: body ? JSON.stringify(body) : null,
        });
    } catch {
        throw new Error("L'API locale ne repond pas. Le service tourne-t-il toujours ?");
    }

    let payload;
    try {
        payload = await response.json();
    } catch {
        throw new Error(`Reponse illisible de l'API (HTTP ${response.status}).`);
    }

    if (!response.ok || payload.success === false) {
        throw new Error(payload.error || `Erreur HTTP ${response.status}.`);
    }
    return payload.data;
}

/* ---------------------------------------------------------------- affichage */

function toast(message, kind = "") {
    const node = document.createElement("div");
    node.className = `toast ${kind}`;
    node.textContent = message;
    $("#toasts").append(node);
    setTimeout(() => node.remove(), kind === "bad" ? 8000 : 4500);
}

const NUM_SPACE = " "; // espace fine insecable, separateur de milliers

function int(value) {
    if (value === null || value === undefined || value === "") return "—";
    return Math.round(Number(value)).toLocaleString("fr-FR").replace(/ |,/g, NUM_SPACE);
}

function dec(value, digits = 2) {
    if (value === null || value === undefined || value === "") return "—";
    return Number(value).toFixed(digits);
}

function pct(value, digits = 1) {
    if (value === null || value === undefined || value === "") return "—";
    return `${(Number(value) * 100).toFixed(digits)}${NUM_SPACE}%`;
}

function shortDate(iso) {
    if (!iso) return "—";
    return String(iso).slice(0, 16).replace("T", " ");
}

/** Construit un tableau complet (en-tetes + lignes) dans un <table>. */
function renderTable(table, headers, rows, options = {}) {
    const { rowClass = null, onRowClick = null } = options;
    table.innerHTML = "";

    const thead = table.createTHead().insertRow();
    for (const label of headers) {
        const th = document.createElement("th");
        th.textContent = label;
        thead.append(th);
    }

    const tbody = table.createTBody();
    if (!rows.length) {
        const cell = tbody.insertRow().insertCell();
        cell.colSpan = headers.length;
        cell.textContent = options.emptyText || "Aucune donnee.";
        cell.style.color = "var(--dust)";
        cell.style.padding = "22px 0";
        return;
    }

    rows.forEach((row, index) => {
        const tr = tbody.insertRow();
        if (rowClass) tr.className = rowClass(row, index) || "";
        for (const value of row.cells ?? row) {
            tr.insertCell().textContent = value === null || value === undefined ? "—" : String(value);
        }
        if (onRowClick) {
            tr.dataset.clickable = "1";
            tr.addEventListener("click", () => onRowClick(row, index, tr));
        }
    });
}

function setTag(node, text, kind) {
    node.textContent = text;
    node.className = `tag ${kind}`;
}

/** Classe CSS coloriant une ligne selon le camp du joueur. */
function teamClass(team) {
    if (team === "CT") return "is-ct";
    if (team === "T") return "is-t";
    return "";
}

/** Ancrage d'un libelle d'axe selon sa position autour du cercle. */
function textAnchorFor(cos) {
    if (Math.abs(cos) < 0.3) return "middle";
    return cos > 0 ? "start" : "end";
}

/**
 * Met en forme une valeur selon son unite, en adaptant le nombre de decimales
 * a l'ordre de grandeur : 0.85 se lit mieux que 1, et 118 mieux que 118.00.
 */
function formatMetric(value, unit, digits = 0) {
    if (unit === "%") return pct(value, digits || 1);
    return dec(value, Math.abs(value) >= 20 ? 0 : 2);
}

/**
 * Formule le rang d'une metrique.
 *
 * « TOP 93 % » pour un joueur classe dans les 7 % les plus faibles se lit comme
 * une bonne nouvelle : le cadrage « top » n'a de sens qu'au-dessus de la
 * mediane. En dessous, on annonce le centile tel quel.
 */
function rankLabel(percentile, topPercent) {
    if (percentile >= 50) return `TOP ${topPercent}%`;
    return `${percentile.toFixed(0)}ᵉ pct`;
}

/** Rang d'une arme dans sa categorie, ou tiret si non calculable. */
function weaponRank(ranking) {
    if (!ranking) return "—";
    return `top ${(100 - ranking.percentile).toFixed(0)}%`;
}

/** Fleche et classe de couleur associees au sens d'une variation. */
function trendMark(gap) {
    if (gap > 0) return { arrow: "▲", cls: "up" };
    if (gap < 0) return { arrow: "▼", cls: "down" };
    return { arrow: "", cls: "" };
}

/* ------------------------------------------------------------------- routeur */

function showPage(name) {
    $$(".page").forEach((page) => page.classList.toggle("active", page.id === `page-${name}`));
    $$(".nav-item").forEach((item) => {
        if (item.dataset.page === name) item.setAttribute("aria-current", "page");
        else item.removeAttribute("aria-current");
    });
    if (name === "live") live.start(); else live.stop();
    if (name === "matches") matches.load();
    if (name === "settings") {
        settings.refresh();
        settings.refreshOverlay();
    }
}

$$(".nav-item").forEach((item) =>
    item.addEventListener("click", () => showPage(item.dataset.page))
);

$$(".tabs").forEach((group) => {
    group.addEventListener("click", (event) => {
        const tab = event.target.closest(".tab");
        if (!tab) return;
        const scope = group.parentElement;
        $$(".tab", group).forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
        $$(".panel", scope).forEach((p) =>
            p.classList.toggle("active", p.dataset.panel === tab.dataset.panel)
        );
    });
});

/* ------------------------------------------------------------ page « joueur » */

const player = {
    steamid: "",

    async search(query) {
        const button = $("#player-search .btn.go");
        button.disabled = true;
        button.innerHTML = '<i class="spinner"></i>';
        try {
            const profile = await api("/api/players/search", { method: "POST", body: { query } });
            this.render(profile);
            const errors = profile.partial_errors || [];
            if (errors.length) toast(`Profil charge, donnees partielles : ${errors.join(", ")}`);
        } catch (error) {
            toast(error.message, "bad");
        } finally {
            button.disabled = false;
            button.textContent = "Chercher";
        }
    },

    render(profile) {
        const { identity = {}, summary = {}, bans = {}, stats = {}, account = {} } = profile;
        this.steamid = identity.steamid64 || "";
        $("#player-analyse").disabled = !this.steamid;
        $("#player-empty").hidden = true;
        $("#player-body").hidden = false;

        // L'avatar vient de Steam : on n'accepte qu'une URL HTTPS explicite.
        if (typeof summary.avatar === "string" && summary.avatar.startsWith("https://")) {
            $("#player-avatar").src = summary.avatar;
        }
        $("#player-name").textContent = summary.persona_name || "Profil sans nom";
        $("#player-ids").textContent = [identity.steamid64, identity.steamid3, identity.steamid2]
            .filter(Boolean).join("   ");

        const meta = [];
        if (summary.time_created) meta.push(`compte cree le ${summary.time_created.slice(0, 10)}`);
        if (summary.country_code) meta.push(summary.country_code);
        if (account.steam_level) meta.push(`niveau ${account.steam_level}`);
        if (account.friends_count) meta.push(`${account.friends_count} amis`);
        if (account.games_owned) meta.push(`${account.games_owned} jeux`);
        $("#player-meta").textContent = meta.join("   ·   ") || "Metadonnees indisponibles";

        const tags = $("#player-tags");
        tags.innerHTML = "";
        const addTag = (text, kind) => {
            const node = document.createElement("span");
            setTag(node, text, kind);
            tags.append(node);
        };
        addTag(summary.is_public ? "Profil public" : "Profil prive", summary.is_public ? "ok" : "warn");
        addTag(
            bans.has_any_ban ? `${bans.total_bans} sanction(s)` : "Aucune sanction",
            bans.has_any_ban ? "bad" : "ok"
        );
        if (summary.playing_cs2) addTag("En jeu sur CS2", "hot");
        else if (summary.in_game) addTag(summary.game_extra_info || "En jeu", "");

        this.renderOverall(profile.percentiles);
        this.renderRanks(profile.percentiles);
        this.renderDrift(profile.drift);
        this.renderOverview(profile);
        this.renderWeapons(stats.weapons || []);
        this.renderMaps(stats.maps || []);
        this.loadLibrary();
        this.loadHistory();
    },

    /**
     * Bandeau de rang global : la position du joueur dans la population est
     * l'information dominante de la page, pas ses chiffres bruts.
     */
    renderOverall(percentiles) {
        const banner = $("#player-overall");
        if (!percentiles?.available) {
            banner.hidden = true;
            return;
        }
        banner.hidden = false;
        const figure = $("#overall-figure");
        figure.textContent = `${percentiles.overall_percentile}`;
        figure.className = `overall-figure tier-${percentiles.overall_tier}`;

        $("#overall-tier").textContent = `${percentiles.overall_tier_label} — ${
            rankLabel(percentiles.overall_percentile, percentiles.overall_top_percent)
        }`;
        $("#overall-tier").className = `overall-tier tier-${percentiles.overall_tier}`;

        const sample = percentiles.sample || {};
        $("#overall-note").textContent = sample.reliable
            ? `Percentile moyen sur 10 metriques, calcule sur ${int(sample.rounds)} manches.`
            : `Echantillon mince (${int(sample.rounds)} manches) : ce classement reste indicatif.`;

        $("#export-csv").href = `/api/players/${this.steamid}/export.csv`;
    },

    /** Une tuile par métrique : valeur, percentile et repère de la moyenne. */
    renderRanks(percentiles) {
        const grid = $("#player-ranks");
        if (!percentiles?.available) {
            grid.innerHTML = "";
            return;
        }

        grid.innerHTML = percentiles.metrics
            .map((metric) => {
                const shown = formatMetric(metric.value, metric.unit, 1);
                const average = formatMetric(metric.average, metric.unit, 0);
                return `
                <div class="rank-tile">
                    <div class="rank-head">
                        <span class="rank-value">${shown}</span>
                        <span class="rank-top tier-${metric.tier}">${rankLabel(metric.percentile, metric.top_percent)}</span>
                    </div>
                    <div class="rank-label">${escapeAttr(metric.label)}</div>
                    <div class="rank-track">
                        <div class="rank-fill bg-${metric.tier}" style="width:${metric.percentile}%"></div>
                        <div class="rank-avg" title="Moyenne de la population"></div>
                    </div>
                    <div class="rank-foot">
                        <span class="tier-${metric.tier}">${escapeAttr(metric.tier_label)}</span>
                        <span>moy. ${average}</span>
                    </div>
                </div>`;
            })
            .join("");
    },

    /** Évolution entre deux relevés — ce que les stats à vie ne montrent pas. */
    renderDrift(drift) {
        const host = $("#player-drift");
        if (!drift?.recent) {
            host.innerHTML = "";
            return;
        }

        const recent = drift.recent;
        const delta = drift.delta || {};
        const notable = Math.abs(delta.headshot_rate || 0) > 0.05
            || Math.abs(delta.accuracy || 0) > 0.03;

        const line = (label, value, gap, asPercent) => {
            if (value === null || value === undefined) return "";
            const shown = asPercent ? pct(value) : dec(value);
            if (gap === null || gap === undefined) {
                return `<span>${label} <b>${shown}</b></span>`;
            }
            const { arrow, cls } = trendMark(gap);
            const amount = asPercent ? `${(gap * 100).toFixed(1)} pts` : gap.toFixed(2);
            return `<span>${label} <b>${shown}</b> <span class="${cls}">${arrow} ${amount}</span></span>`;
        };

        host.innerHTML = `
            <div class="drift ${notable ? "" : "calm"}">
                <span class="eyebrow">Depuis le releve precedent</span>
                ${int(recent.rounds)} manches jouees entre le
                ${shortDate(drift.from)} et le ${shortDate(drift.to)}.
                ${notable
                    ? "Le niveau sur cette periode s'ecarte nettement de l'historique du compte."
                    : "Le niveau sur cette periode reste conforme a l'historique du compte."}
                <div class="drift-grid">
                    ${line("Headshots", recent.headshot_rate, delta.headshot_rate, true)}
                    ${line("Precision", recent.accuracy, delta.accuracy, true)}
                    ${line("Kills/manche", recent.kills_per_round, delta.kills_per_round, false)}
                    ${line("K/D", recent.kd, null, false)}
                </div>
            </div>`;
    },

    renderOverview(profile) {
        const stats = profile.stats || {};
        const totals = stats.totals || {};
        const ratios = stats.ratios || {};
        const last = stats.last_match || {};
        const bans = profile.bans || {};
        const account = profile.account || {};
        const achievements = profile.achievements || {};

        const rows = [
            ["Eliminations", int(totals.kills)],
            ["Morts", int(totals.deaths)],
            ["Headshots", int(totals.headshot_kills)],
            ["Balles tirees", int(totals.shots_fired)],
            ["Balles au but", int(totals.shots_hit)],
            ["Degats infliges", int(totals.damage_done)],
            ["Argent gagne", `${int(totals.money_earned)} $`],
            ["Manches jouees", int(totals.rounds_played)],
            ["Manches gagnees", int(totals.rounds_won)],
            ["Matchs joues", int(totals.matches_played)],
            ["Matchs gagnes", int(totals.matches_won)],
            ["MVP", int(totals.assists_proxy_mvps)],
            ["Bombes posees", int(totals.bombs_planted)],
            ["Bombes desamorcees", int(totals.bombs_defused)],
            ["Manches pistolet gagnees", int(totals.pistol_rounds_won)],
            ["Impacts par kill", dec(ratios.hits_per_kill)],
            ["Balles par kill", dec(ratios.shots_per_kill, 1)],
            ["Degats par kill", dec(ratios.damage_per_kill, 1)],
            ["Kills par heure", dec(ratios.kills_per_hour, 1)],
            ["Taux de MVP", pct(ratios.mvp_rate, 2)],
            ["Manches gagnees", pct(ratios.round_win_rate, 2)],
            ["Matchs gagnes", pct(ratios.match_win_rate, 2)],
            ["Dernier match — K/D", dec(last.kd)],
            ["Dernier match — ADR", dec(last.adr, 1)],
            ["Dernier match — arme favorite", last.favourite_weapon || "—"],
            ["Succes", `${achievements.unlocked ?? 0} / ${achievements.total ?? 0}`],
            ["Bannissements VAC", int(bans.number_of_vac_bans)],
            ["Bannissements editeur", int(bans.number_of_game_bans)],
            ["Jours depuis la sanction", bans.total_bans ? int(bans.days_since_last_ban) : "—"],
            ["Part de CS2 dans le temps de jeu", pct(account.cs2_share_of_playtime)],
        ];
        renderTable($("#tbl-overview"), ["Indicateur", "Valeur"], rows);
    },

    async renderWeapons(fallback) {
        const headers = [
            "Arme", "Categorie", "Kills", "Tirs", "Impacts", "Precision",
            "Rang", "Balles/kill",
        ];
        let weapons = fallback;
        try {
            // L'endpoint dedie ajoute le classement de chaque arme dans sa
            // propre categorie ; sans lui on affiche quand meme les chiffres.
            const data = await api(`/api/players/${this.steamid}/weapons`);
            weapons = data.weapons || fallback;
        } catch {
            /* Profil restreint : on garde les donnees deja chargees. */
        }

        renderTable(
            $("#tbl-weapons"),
            headers,
            weapons.map((w) => [
                w.name, w.category, int(w.kills), int(w.shots_fired), int(w.shots_hit),
                pct(w.accuracy),
                weaponRank(w.ranking),
                dec(w.shots_per_kill, 1),
            ]),
            { emptyText: "Aucune statistique par arme sur ce profil." }
        );
    },

    renderMaps(maps) {
        renderTable(
            $("#tbl-maps"),
            ["Carte", "Manches", "Victoires", "Taux"],
            maps.map((m) => [m.name, int(m.rounds_played), int(m.wins), pct(m.win_rate)]),
            { emptyText: "Aucune statistique par carte." }
        );
    },

    async loadLibrary() {
        try {
            const data = await api(`/api/players/${this.steamid}/games`, { params: { limit: 40 } });
            renderTable(
                $("#tbl-library"),
                ["Jeu", "Heures", "2 semaines", "Derniere partie"],
                (data.top_games || []).map((g) => [
                    g.name || `App ${g.appid}`, dec(g.hours, 1), dec(g.hours_2weeks, 1),
                    g.last_played ? g.last_played.slice(0, 10) : "—",
                ])
            );
        } catch {
            renderTable($("#tbl-library"), ["Jeu", "Heures", "2 semaines", "Derniere partie"], [], {
                emptyText: "Bibliotheque non consultable (profil restreint).",
            });
        }
    },

    async loadHistory() {
        try {
            const data = await api(`/api/players/${this.steamid}/history`);
            const snapshots = data.snapshots || [];
            renderTable(
                $("#tbl-history"),
                ["Releve", "Kills", "Morts", "Manches", "K/D", "HS", "Precision"],
                snapshots.map((s) => [
                    shortDate(s.captured_at), int(s.kills), int(s.deaths), int(s.rounds_played),
                    dec(s.kd_ratio, 3), pct(s.headshot_rate), pct(s.accuracy),
                ]),
                { emptyText: "Premier releve enregistre. Reviens plus tard pour suivre la progression." }
            );
            this.renderCharts(snapshots);
        } catch (error) {
            toast(error.message, "bad");
        }
    },

    renderCharts(snapshots) {
        const host = $("#player-charts");
        // Les releves arrivent du plus recent au plus ancien : on remet dans
        // l'ordre chronologique pour que les courbes se lisent de gauche a droite.
        const ordered = [...snapshots].reverse();

        if (ordered.length < 2) {
            host.innerHTML = `
                <p class="paste-help" style="grid-column:1/-1">
                    Une seule mesure disponible. Consulte ce profil regulierement :
                    chaque visite enregistre un releve, et les courbes apparaitront
                    des le deuxieme.
                </p>`;
            return;
        }

        const series = [
            { key: "kd_ratio", label: "Ratio K/D", color: "var(--flash)", asPercent: false },
            { key: "headshot_rate", label: "Headshots", color: "var(--clean)", asPercent: true },
            { key: "accuracy", label: "Precision", color: "var(--ct)", asPercent: true },
        ];

        host.innerHTML = series
            .map((entry) => {
                const values = ordered.map((s) => Number(s[entry.key]) || 0);
                const current = values.at(-1);
                const shown = entry.asPercent ? pct(current) : dec(current, 3);
                return `
                <div class="chart">
                    <div class="chart-title">
                        <span class="eyebrow">${entry.label}</span>
                        <span class="chart-now" style="color:${entry.color}">${shown}</span>
                    </div>
                    ${sparkline(values, entry.color)}
                    <div class="chart-foot">
                        <span>${shortDate(ordered[0].captured_at)}</span>
                        <span>${ordered.length} releves</span>
                        <span>${shortDate(ordered.at(-1).captured_at)}</span>
                    </div>
                </div>`;
            })
            .join("");
    },
};

/**
 * Courbe compacte en SVG, sans aucune bibliotheque.
 *
 * L'echelle verticale est resserree autour des valeurs observees plutot que
 * fixee a zero : sur des metriques qui varient de quelques pourcents, partir
 * de zero ecraserait toute l'information.
 */
function sparkline(values, color) {
    const W = 300;
    const H = 96;
    const PAD = 8;

    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || Math.abs(max) || 1;
    const lo = min - span * 0.15;
    const hi = max + span * 0.15;

    const x = (i) => PAD + (i / Math.max(1, values.length - 1)) * (W - PAD * 2);
    const y = (v) => H - PAD - ((v - lo) / (hi - lo)) * (H - PAD * 2);

    const points = values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`);
    const line = `M${points.join(" L")}`;
    const area = `${line} L${x(values.length - 1).toFixed(1)},${H - PAD} L${x(0).toFixed(1)},${H - PAD} Z`;

    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const meanY = y(mean).toFixed(1);
    const lastX = x(values.length - 1).toFixed(1);
    const lastY = y(values.at(-1)).toFixed(1);

    return `
        <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img"
             aria-label="Evolution sur ${values.length} releves">
            <line class="chart-base" x1="${PAD}" y1="${meanY}" x2="${W - PAD}" y2="${meanY}"/>
            <path class="chart-area" d="${area}" fill="${color}"/>
            <path class="chart-line" d="${line}" stroke="${color}"/>
            <circle class="chart-dot" cx="${lastX}" cy="${lastY}" r="3" fill="${color}"/>
        </svg>`;
}

$("#player-search").addEventListener("submit", (event) => {
    event.preventDefault();
    const query = $("#player-query").value.trim();
    if (query) player.search(query);
});

$("#player-analyse").addEventListener("click", () => {
    showPage("anticheat");
    $("#ac-query").value = player.steamid;
    anticheat.run(player.steamid);
});

/* -------------------------------------------------- signature : nuage de points */

const CATEGORY_ANGLES = {
    visee: -90, armes: -26, progression: 38, regularite: 102, temps_reel: 166,
    compte: 230, sanctions: 294,
};
// Libelles courts : ils doivent tenir dans la marge du trace sans etre rognes.
const CATEGORY_LABELS = {
    visee: "Visee", armes: "Armes", progression: "Niveau", regularite: "Regularite",
    temps_reel: "Direct", compte: "Compte", sanctions: "Sanctions",
};
const SEVERITY_COLORS = {
    critique: "var(--critical)", eleve: "var(--high)", moyen: "var(--moderate)",
    faible: "var(--low)", info: "var(--dust)",
};

const SIGMA_MAX = 5;
//: La zone de dessin est plus large que le disque : la marge accueille les
//: libelles d'axes, qui seraient sinon rognes par le viewBox.
const PLOT_SIZE = 360;
const PLOT_R = 118;
const LABEL_OFFSET = 18;

/**
 * Trace les indicateurs comme un nuage de dispersion sur un reticule.
 * Rayon = ecart-type observe, angle = famille d'indicateurs.
 */
function drawScatter(signals) {
    const center = PLOT_SIZE / 2;
    const parts = [`<svg viewBox="0 0 ${PLOT_SIZE} ${PLOT_SIZE}" role="img" aria-label="Dispersion des indicateurs">`];

    for (let sigma = 1; sigma <= SIGMA_MAX; sigma++) {
        const radius = (sigma / SIGMA_MAX) * PLOT_R;
        // Le cercle a 2 sigma est le seuil au-dela duquel un ecart devient notable.
        const isThreshold = sigma === 2;
        parts.push(
            `<circle class="ring${isThreshold ? " threshold" : ""}" cx="${center}" ` +
            `cy="${center}" r="${radius.toFixed(1)}"/>`,
            `<text class="ring-label" x="${center + 4}" ` +
            `y="${(center - radius + 9).toFixed(1)}">${sigma}σ</text>`
        );
    }

    for (const [key, angle] of Object.entries(CATEGORY_ANGLES)) {
        const radians = (angle * Math.PI) / 180;
        const cos = Math.cos(radians);
        const sin = Math.sin(radians);
        const label = CATEGORY_LABELS[key] || key;
        const lx = center + cos * (PLOT_R + LABEL_OFFSET);
        const ly = center + sin * (PLOT_R + LABEL_OFFSET);
        parts.push(
            `<line class="axis" x1="${center}" y1="${center}" ` +
            `x2="${(center + cos * PLOT_R).toFixed(1)}" y2="${(center + sin * PLOT_R).toFixed(1)}"/>`,
            `<text class="axis-label" x="${lx.toFixed(1)}" y="${(ly + 3).toFixed(1)}" ` +
            `text-anchor="${textAnchorFor(cos)}">${label}</text>`
        );
    }

    const scored = signals.filter((s) => s.confidence > 0.02);
    scored
        .sort((a, b) => (a.contribution || 0) - (b.contribution || 0))
        .forEach((signal, index) => {
            const base = CATEGORY_ANGLES[signal.category] ?? 0;
            // Ecarte legerement les points d'une meme famille pour eviter le chevauchement.
            const spread = ((index % 5) - 2) * 7;
            const radians = ((base + spread) * Math.PI) / 180;

            const sigma = signal.z_score !== null && signal.z_score !== undefined
                ? Math.max(0, signal.z_score)
                : signal.score * SIGMA_MAX;
            const radius = (Math.min(sigma, SIGMA_MAX) / SIGMA_MAX) * PLOT_R;

            const x = center + Math.cos(radians) * radius;
            const y = center + Math.sin(radians) * radius;
            const size = 3 + Math.min(signal.weight || 1, 3) * 1.4;
            const color = SEVERITY_COLORS[signal.severity] || "var(--dust)";
            const opacity = 0.35 + signal.confidence * 0.65;

            parts.push(
                `<circle class="pip" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${size.toFixed(1)}" ` +
                `fill="${color}" opacity="${opacity.toFixed(2)}" ` +
                `style="animation-delay:${index * 24}ms"><title>${escapeAttr(signal.label)} — ` +
                `${sigma.toFixed(1)} ecart-type, confiance ${Math.round(signal.confidence * 100)}%</title></circle>`
            );
        });

    parts.push(`<circle cx="${center}" cy="${center}" r="1.6" fill="var(--line-2)"/>`);
    parts.push("</svg>");
    return parts.join("");
}

function escapeAttr(text) {
    return String(text).replace(/[<>&"]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[c]));
}

/* ------------------------------------------------------- page « anti-triche » */

const VERDICT_KIND = {
    CLEAN: "ok", LOW: "", MODERATE: "warn", HIGH: "hot", CRITICAL: "bad", INDETERMINE: "",
};
const VERDICT_VAR = {
    CLEAN: "var(--clean)", LOW: "var(--low)", MODERATE: "var(--moderate)",
    HIGH: "var(--high)", CRITICAL: "var(--critical)", INDETERMINE: "var(--dust)",
};

const anticheat = {
    async run(query) {
        const players = query.split(",").map((s) => s.trim()).filter(Boolean);
        if (!players.length) return;
        if (players.length > 1) return this.runBatch(players);

        const button = $("#ac-search .btn.go");
        button.disabled = true;
        button.innerHTML = '<i class="spinner"></i>';
        try {
            const result = await api(`/api/anticheat/${players[0]}`, { params: { use_live: true } });
            this.render(result);
            this.loadAdvice(players[0]);
        } catch (error) {
            toast(error.message, "bad");
        } finally {
            button.disabled = false;
            button.textContent = "Analyser";
        }
    },

    async runBatch(players) {
        try {
            const data = await api("/api/anticheat/batch", {
                method: "POST",
                body: { players, use_live_data: true, persist: true },
            });
            this.renderLobby(data);
            if (data.results?.length) this.render(data.results[0]);
        } catch (error) {
            toast(error.message, "bad");
        }
    },

    async runPastedLobby() {
        const text = $("#ac-paste-text").value.trim();
        if (!text) {
            toast("Colle d'abord la sortie de la commande status.", "bad");
            return;
        }
        const button = $("#ac-paste-run");
        button.disabled = true;
        button.innerHTML = '<i class="spinner"></i>';
        try {
            const data = await api("/api/anticheat/lobby/paste", {
                method: "POST",
                body: { text, analyse: true },
            });
            if (!data.analysed) {
                toast(data.message || "Aucun joueur exploitable dans ce collage.", "bad");
                return;
            }
            this.renderLobby(data);
            if (data.results?.length) this.render(data.results[0]);
            toast(`${data.analysed} joueur(s) analyse(s) sur ${data.found} repere(s).`, "ok");
        } catch (error) {
            toast(error.message, "bad");
        } finally {
            button.disabled = false;
            button.textContent = "Analyser ces joueurs";
        }
    },

    async runLiveLobby() {
        const button = $("#ac-lobby");
        button.disabled = true;
        try {
            const data = await api("/api/anticheat/lobby/live", { method: "POST" });
            if (!data.analysed) {
                toast(data.message || "Aucun joueur observe pour l'instant.");
                return;
            }
            this.renderLobby(data);
            if (data.results?.length) this.render(data.results[0]);
        } catch (error) {
            toast(error.message, "bad");
        } finally {
            button.disabled = false;
        }
    },

    render(result) {
        $("#ac-empty").hidden = true;
        $("#ac-body").hidden = false;

        const color = VERDICT_VAR[result.verdict] || "var(--dust)";
        const score = $("#ac-score");
        score.textContent = Math.round(result.suspicion_score);
        score.style.color = color;

        setTag($("#ac-verdict"), result.verdict, VERDICT_KIND[result.verdict] ?? "");
        const meter = $("#ac-meter");
        meter.style.width = `${result.suspicion_score}%`;
        meter.style.background = color;

        $("#ac-line").textContent =
            `${result.name} — ${result.verdict_label}. Confiance de l'analyse : ` +
            `${Math.round(result.global_confidence * 100)}${NUM_SPACE}%.`;

        $("#ac-scatter").innerHTML = drawScatter(result.signals || []);
        this.renderSignals(result.signals || []);
        $("#ac-disclaimer").textContent = result.disclaimer || "";
    },

    renderSignals(signals) {
        const shown = signals
            .filter((s) => s.confidence > 0.02)
            .sort((a, b) => (b.contribution || 0) - (a.contribution || 0))
            .slice(0, 14);

        $("#ac-signals").innerHTML = shown
            .map((signal) => {
                const color = SEVERITY_COLORS[signal.severity] || "var(--dust)";
                const measured = signal.observed !== null && signal.observed !== undefined
                    ? `${dec(signal.observed, 3)} vs ${dec(signal.expected, 3)}`
                    : "—";
                return `
                <div class="signal">
                    <div class="signal-bar" style="background:${color}"></div>
                    <div>
                        <div class="signal-name">${escapeAttr(signal.label)}</div>
                        <div class="signal-why">${escapeAttr(signal.explanation)}</div>
                    </div>
                    <div class="signal-num">
                        <b style="color:${color}">${Math.round(signal.score * 100)}</b>
                        ${measured}<br>${Math.round(signal.confidence * 100)}${NUM_SPACE}% sur
                        ${int(signal.sample_size)}
                    </div>
                </div>`;
            })
            .join("");
    },

    renderLobby(data) {
        $("#ac-lobby-body").hidden = false;
        const rows = (data.summary || []).map((entry) => ({
            cells: [
                entry.name, Math.round(entry.score), entry.verdict,
                `${Math.round(entry.confidence * 100)}${NUM_SPACE}%`,
                entry.has_confirmed_ban ? "oui" : "non", entry.top_reason,
            ],
            steamid: entry.steamid,
        }));
        renderTable(
            $("#tbl-lobby"),
            ["Joueur", "Score", "Verdict", "Confiance", "Sanction", "Indicateur principal"],
            rows,
            { onRowClick: (row) => this.run(row.steamid) }
        );
    },

    async loadAdvice(steamid) {
        try {
            const data = await api(`/api/anticheat/${steamid}/report`);
            const text = String(data.text || "");
            const marker = "--- Recommandation";
            if (!text.includes(marker)) return;
            const lines = text.split(marker)[1].split("\n").map((l) => l.trim()).filter(Boolean);
            if (lines.length > 1) {
                $("#ac-advice").hidden = false;
                $("#ac-advice-text").textContent = lines[1];
            }
        } catch {
            /* La recommandation est un complement : son absence n'est pas bloquante. */
        }
    },
};

$("#ac-search").addEventListener("submit", (event) => {
    event.preventDefault();
    anticheat.run($("#ac-query").value);
});
$("#ac-lobby").addEventListener("click", () => anticheat.runLiveLobby());

$("#ac-toggle-paste").addEventListener("click", () => {
    const zone = $("#ac-paste");
    zone.hidden = !zone.hidden;
    if (!zone.hidden) $("#ac-paste-text").focus();
});

$("#ac-paste-run").addEventListener("click", () => anticheat.runPastedLobby());

// Compteur d'identifiants reperes, mis a jour pendant la saisie : l'utilisateur
// voit immediatement si son collage est exploitable.
$("#ac-paste-text").addEventListener("input", debounce(async (event) => {
    const text = event.target.value.trim();
    const label = $("#ac-paste-found");
    if (text.length < 10) {
        label.textContent = "";
        return;
    }
    try {
        const data = await api("/api/players/extract", {
            method: "POST",
            body: { text, analyse: false },
        });
        label.textContent = data.found
            ? `${data.found} joueur(s) repere(s).`
            : "Aucun identifiant repere pour l'instant.";
    } catch {
        label.textContent = "";
    }
}, 400));

function debounce(fn, delay) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), delay);
    };
}

/* ------------------------------------------------------- page « temps reel » */

const EVENT_LABELS = {
    kill: ["Elimination", "var(--clean)"], headshot_kill: ["Headshot", "var(--flash)"],
    multi_kill: ["Multi-kill", "var(--flash)"], death: ["Mort", "var(--critical)"],
    assist: ["Assistance", "var(--low)"], mvp: ["MVP", "var(--moderate)"],
    round_start: ["Manche", "var(--ash)"], round_freeze: ["Achats", "var(--dust)"],
    round_end: ["Fin de manche", "var(--ash)"], bomb_planted: ["Bombe posee", "var(--moderate)"],
    bomb_defused: ["Desamorcee", "var(--ct)"], bomb_exploded: ["Explosion", "var(--critical)"],
    match_start: ["Debut de match", "var(--clean)"], match_end: ["Fin de match", "var(--low)"],
    map_change: ["Carte", "var(--low)"], damage_taken: ["Degats", "var(--moderate)"],
    flashed: ["Aveugle", "var(--t)"], low_health: ["Sante critique", "var(--critical)"],
    connection: ["Liaison etablie", "var(--clean)"], weapon_switch: ["Arme", "var(--dust)"],
};
const FEED_LIMIT = 120;
const POLL_MS = 1000;

const live = {
    timer: null,
    sequence: 0,
    steamids: [],

    start() {
        if (this.timer) return;
        this.tick();
        this.timer = setInterval(() => this.tick(), POLL_MS);
    },

    stop() {
        clearInterval(this.timer);
        this.timer = null;
    },

    async tick() {
        try {
            const [snapshot, board, events] = await Promise.all([
                api("/api/live/state"),
                api("/api/live/scoreboard"),
                api("/api/live/events", { params: { since: this.sequence, limit: 60 } }),
            ]);
            this.renderState(snapshot);
            this.renderBoard(board);
            this.renderEvents(events);
        } catch {
            /* Le jeu peut etre ferme : on garde le dernier etat affiche. */
        }
    },

    renderState(snapshot) {
        const state = snapshot.state || {};
        const map = state.map || {};
        const round = state.round || {};
        const bomb = state.bomb || {};

        setNum($("#live-ct"), (map.team_ct || {}).score ?? 0);
        setNum($("#live-t"), (map.team_t || {}).score ?? 0);
        $("#live-map").textContent = map.name || "En attente du jeu";
        $("#live-mode").textContent = map.mode
            ? `${map.mode} · ${map.phase || ""}`
            : "Lance CS2 avec la configuration installee.";
        $("#live-round").textContent = map.round ?? "—";
        $("#live-phase").textContent = round.phase || "—";

        const bombChip = $("#live-bomb-chip");
        if (bomb.state === "planted") {
            bombChip.hidden = false;
            $("#live-bomb").textContent = `${dec(bomb.countdown, 1)} s`;
        } else {
            bombChip.hidden = true;
        }

        const wins = map.round_wins || {};
        $("#live-rounds").innerHTML = Object.keys(wins)
            .sort((a, b) => Number(a) - Number(b))
            .map((key) => {
                const side = String(wins[key]).startsWith("ct") ? "ct" : "t";
                const title = escapeAttr(`Manche ${key} — ${wins[key]}`);
                return `<i class="round-pip ${side}" title="${title}"></i>`;
            })
            .join("");
    },

    renderBoard(rows) {
        this.steamids = rows.map((r) => r.steamid);
        renderTable(
            $("#tbl-scoreboard"),
            ["Joueur", "K", "D", "A", "MVP", "K/D", "ADR", "HS", "PV", "$", "Arme"],
            rows.map((r) => ({
                cells: [
                    r.name, r.kills, r.deaths, r.assists, r.mvps, dec(r.kd), dec(r.adr, 0),
                    pct(r.headshot_rate, 0), r.alive === false ? "mort" : (r.health ?? "—"),
                    r.money ?? "—", r.active_weapon || "—",
                ],
                steamid: r.steamid,
                team: r.team,
            })),
            {
                rowClass: (row) => teamClass(row.team),
                onRowClick: (row) => {
                    if (!row.steamid) return;
                    showPage("anticheat");
                    $("#ac-query").value = row.steamid;
                    anticheat.run(row.steamid);
                },
                emptyText: "Aucun joueur transmis. En partie normale, seul ton propre etat est envoye.",
            }
        );
    },

    renderEvents(payload) {
        this.sequence = payload.latest_sequence ?? this.sequence;
        const feed = $("#live-feed");
        for (const event of payload.events || []) {
            const [label, color] = EVENT_LABELS[event.type] || [event.type, "var(--ash)"];
            const item = document.createElement("li");
            item.innerHTML =
                `<time>R${String(event.round).padStart(2, "0")}</time>` +
                `<span class="what" style="color:${color}">${escapeAttr(label)}</span>` +
                `<span class="who">${escapeAttr(event.player || "")}</span>`;
            feed.prepend(item);
        }
        while (feed.children.length > FEED_LIMIT) feed.lastElementChild.remove();
    },
};

function setNum(node, value) {
    const next = String(value);
    if (node.textContent === next) return;
    node.textContent = next;
    node.classList.remove("flash-on-change");
    void node.offsetWidth; // force le redemarrage de l'animation
    node.classList.add("flash-on-change");
}

$("#live-analyse").addEventListener("click", () => {
    showPage("anticheat");
    anticheat.runLiveLobby();
});

/* ------------------------------------------------------------ page « matchs » */

const matches = {
    async load() {
        try {
            const list = await api("/api/matches", { params: { limit: 100 } });
            $("#matches-empty").hidden = list.length > 0;
            renderTable(
                $("#tbl-matches"),
                ["Debut", "Carte", "Mode", "CT", "T", "Manches", "Joueurs"],
                list.map((m) => ({
                    cells: [
                        shortDate(m.started_at), m.map_name || "—", m.mode || "—",
                        m.score_ct, m.score_t, m.rounds_total, (m.summary || {}).players ?? "—",
                    ],
                    id: m.id,
                })),
                {
                    onRowClick: (row, _i, tr) => {
                        $$("#tbl-matches tr").forEach((r) => r.classList.remove("is-selected"));
                        tr.classList.add("is-selected");
                        this.open(row.id);
                    },
                    emptyText: "",
                }
            );
        } catch (error) {
            toast(error.message, "bad");
        }
    },

    async open(matchId) {
        try {
            const match = await api(`/api/matches/${matchId}`);
            $("#match-detail").hidden = false;
            renderTable(
                $("#tbl-match-players"),
                ["Joueur", "K", "D", "A", "MVP", "ADR", "HS", "Manches"],
                (match.players || []).map((p) => ({
                    cells: [
                        p.name || p.steamid64, p.kills, p.deaths, p.assists, p.mvps,
                        dec(p.adr, 0), pct(p.headshot_rate, 0), p.rounds,
                    ],
                    steamid: p.steamid64,
                    team: p.team,
                })),
                {
                    rowClass: (row) => teamClass(row.team),
                    onRowClick: (row) => {
                        showPage("anticheat");
                        $("#ac-query").value = row.steamid;
                        anticheat.run(row.steamid);
                    },
                }
            );
            renderTable(
                $("#tbl-match-rounds"),
                ["#", "Vainqueur", "CT", "T"],
                (match.rounds || []).map((r) => [
                    r.round_number, r.winner || "—",
                    (r.details || {}).score_ct ?? "—", (r.details || {}).score_t ?? "—",
                ])
            );
        } catch (error) {
            toast(error.message, "bad");
        }
    },
};

/* --------------------------------------------------------- page « reglages » */

const settings = {
    async refresh() {
        try {
            const status = await api("/api/system/status");
            this.renderStatus(status);
            this.renderRig(status);
        } catch (error) {
            toast(error.message, "bad");
        }
    },

    async refreshOverlay() {
        const label = $("#overlay-state");
        const button = $("#start-overlay");
        try {
            const state = await api("/api/system/overlay");
            if (state.running) {
                label.textContent = "Overlay actif.";
                button.textContent = "Overlay deja lance";
            } else if (state.available) {
                label.textContent = "Pret a etre lance.";
                button.textContent = "Lancer l'overlay";
            } else {
                label.textContent =
                    "CS2TrackerOverlay.exe introuvable — telecharge-le et place-le "
                    + "a cote de CS2Tracker.exe.";
                button.textContent = "Lancer l'overlay";
            }
        } catch {
            label.textContent = "";
        }
    },

    renderRig(status) {
        const live_ = status.live || {};
        $("#rig-steam").className = `dot ${status.steam_api_configured ? "on" : "off"}`;
        $("#rig-cs2").className = `dot ${status.cs2_detected ? "on" : "warn"}`;
        $("#rig-gsi").className =
            `dot ${live_.connected ? "on" : status.gsi_config_installed ? "warn" : "off"}`;
    },

    renderStatus(status) {
        const paths = status.cs2_paths || {};
        const db = status.database || {};
        const rows = db.rows || {};
        const cache = status.cache || {};
        const live_ = status.live || {};

        renderTable($("#tbl-status"), ["Element", "Valeur"], [
            ["Version", status.version],
            ["API locale", status.api_base_url],
            ["Point de collecte du jeu", status.gsi_endpoint],
            ["Installation Steam", paths.steam_path || "introuvable"],
            ["Dossier de configuration CS2", paths.cfg_path || "introuvable"],
            ["Fichier de liaison installe", status.gsi_config_installed ? "oui" : "non"],
            ["Base de donnees", db.path],
            ["Taille de la base", `${Math.round((db.size_bytes || 0) / 1024)} Ko`],
            ["Joueurs suivis", int(rows.players)],
            ["Releves de statistiques", int(rows.stat_snapshots)],
            ["Analyses", int(rows.analyses)],
            ["Matchs archives", int(rows.matches)],
            ["Payloads recus du jeu", int(live_.payloads_received)],
            ["Requetes Steam", int(status.steam_requests)],
            ["Cache Steam", `${cache.entries ?? 0} entrees · ${pct(cache.hit_rate ?? 0, 0)} de reussite`],
        ]);
    },
};

/* ------------------------------------------------- enregistrement de la cle */

//: Longueur d'une cle API Steam. On previent avant l'appel plutot que de
//: laisser l'API refuser.
const STEAM_KEY_LENGTH = 32;

$("#save-key").addEventListener("click", async () => {
    const input = $("#steam-key");
    const key = input.value.trim();

    if (key.length < 16) {
        toast(
            `Cette cle semble trop courte : une cle Steam fait ${STEAM_KEY_LENGTH} caracteres.`,
            "bad"
        );
        input.focus();
        return;
    }

    const button = $("#save-key");
    button.disabled = true;
    try {
        const result = await api("/api/system/steam-key", {
            method: "POST",
            body: { key },
        });
        input.value = "";
        restartDialog.open(result);
        settings.refresh();
    } catch (error) {
        toast(error.message, "bad");
    } finally {
        button.disabled = false;
    }
});

/**
 * Dialogue de redemarrage.
 *
 * La cle n'est lue qu'au demarrage : le client Steam est construit une seule
 * fois, a l'ouverture. Plutot que de demander a l'utilisateur de fermer puis
 * rouvrir, l'application se relance elle-meme.
 */
const restartDialog = {
    //: Duree maximale d'attente avant de considerer le redemarrage perdu.
    MAX_WAIT_MS: 45000,
    POLL_MS: 700,

    /**
     * Presente le resultat de l'enregistrement.
     *
     * Trois issues possibles, chacune avec ses propres actions :
     *   - cle active et verifiee aupres de Steam : simple confirmation ;
     *   - cle active mais non verifiee : on avertit sans bloquer ;
     *   - bascule a chaud impossible : on propose le redemarrage.
     */
    open(result) {
        $("#restart-progress").hidden = true;

        const needsRestart = Boolean(result.restart_required);
        $("#restart-later").hidden = !needsRestart;
        $("#restart-now").hidden = !needsRestart;
        $("#restart-ok").hidden = needsRestart;
        $("#restart-later").disabled = false;
        $("#restart-now").disabled = false;

        $("#restart-title").textContent = result.verified
            ? "Cle activee"
            : "Cle enregistree";
        $("#restart-body").textContent = result.message;

        $("#restart-modal").showModal();
    },

    close() {
        $("#restart-modal").close();
    },

    async restart() {
        $("#restart-progress").hidden = false;
        $("#restart-later").disabled = true;
        $("#restart-now").disabled = true;

        try {
            await api("/api/system/restart", { method: "POST" });
        } catch {
            // L'API se coupe pendant la requete : la coupure EST le signe que
            // le redemarrage a bien demarre, ce n'est donc pas une erreur.
        }
        this.waitForApi();
    },

    /**
     * Attend le retour de l'API puis recharge la page.
     *
     * En fenetre native, le processus est remplace et une nouvelle fenetre
     * s'ouvre : ce code ne sera jamais atteint. Dans le navigateur en revanche,
     * l'onglet survit et doit se resynchroniser tout seul.
     */
    waitForApi() {
        const deadline = Date.now() + this.MAX_WAIT_MS;
        let wentDown = false;

        const probe = async () => {
            try {
                await api("/health");
                // Tant que l'API n'a pas disparu, c'est encore l'ancienne
                // instance qui repond : on attend sa coupure avant de conclure.
                if (wentDown) {
                    window.location.reload();
                    return;
                }
            } catch {
                wentDown = true;
            }

            if (Date.now() > deadline) {
                $("#restart-progress").hidden = true;
                $("#restart-later").disabled = false;
                toast(
                    "Le redemarrage prend plus longtemps que prevu. Ferme puis "
                    + "rouvre l'application si la cle n'est pas active.",
                    "bad"
                );
                return;
            }
            setTimeout(probe, this.POLL_MS);
        };

        setTimeout(probe, this.POLL_MS);
    },
};

$("#restart-now").addEventListener("click", () => restartDialog.restart());
$("#restart-ok").addEventListener("click", () => restartDialog.close());
$("#restart-later").addEventListener("click", () => {
    restartDialog.close();
    toast("Cle enregistree. Elle sera active au prochain demarrage.", "ok");
    settings.refresh();
});

$("#install-gsi").addEventListener("click", async () => {
    try {
        const result = await api("/api/system/gsi/install", {
            method: "POST",
            body: { throttle: Number($("#gsi-throttle").value) || 0.1 },
        });
        const out = $("#gsi-out");
        out.hidden = false;
        out.textContent = `${result.message}\n\n${result.config_path}\n→ ${result.endpoint}`;
        toast(result.message, result.installed ? "ok" : "bad");
        settings.refresh();
    } catch (error) {
        toast(error.message, "bad");
    }
});

$("#preview-gsi").addEventListener("click", async () => {
    try {
        const result = await api("/api/system/gsi/preview");
        const out = $("#gsi-out");
        out.hidden = false;
        out.textContent = result.content;
    } catch (error) {
        toast(error.message, "bad");
    }
});

$("#remove-gsi").addEventListener("click", async () => {
    try {
        const result = await api("/api/system/gsi/install", { method: "DELETE" });
        toast(result.removed ? "Fichier de liaison retire." : "Aucun fichier a retirer.");
        settings.refresh();
    } catch (error) {
        toast(error.message, "bad");
    }
});

$("#refresh-status").addEventListener("click", () => settings.refresh());

$("#start-overlay").addEventListener("click", async () => {
    const button = $("#start-overlay");
    button.disabled = true;
    try {
        const result = await api("/api/system/overlay", { method: "POST" });
        toast(result.message, result.started ? "ok" : "bad");
        settings.refreshOverlay();
    } catch (error) {
        toast(error.message, "bad");
    } finally {
        button.disabled = false;
    }
});

$("#clear-cache").addEventListener("click", async () => {
    try {
        const result = await api("/api/system/cache/clear", { method: "POST" });
        toast(`${result.cleared} entree(s) de cache supprimee(s).`, "ok");
    } catch (error) {
        toast(error.message, "bad");
    }
});

/* ------------------------------------------------------------------ demarrage */

settings.refresh();
setInterval(() => settings.refresh(), 6000);
$("#player-query").focus();
