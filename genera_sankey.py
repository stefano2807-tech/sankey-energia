import os, re, csv, io, ftplib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path
from matplotlib.patches import PathPatch, FancyBboxPatch
from matplotlib.colors import to_rgb

HOST = os.environ["FTP_HOST"]
PORT = int(os.environ.get("FTP_PORT") or "21")
USER = os.environ["FTP_USER"]
PASSW = os.environ["FTP_PASS"]
FTP_DIR = os.environ.get("FTP_DIR") or "/"
PERIODO = os.environ.get("PERIODO") or "Ottobre 2026"


def connect():
    try:  # prima prova con TLS
        f = ftplib.FTP_TLS()
        f.connect(HOST, PORT, timeout=30)
        f.login(USER, PASSW)
        f.prot_p()
    except Exception:  # altrimenti FTP in chiaro
        f = ftplib.FTP()
        f.connect(HOST, PORT, timeout=30)
        f.login(USER, PASSW)
    f.set_pasv(True)
    if FTP_DIR not in ("", "/"):
        f.cwd(FTP_DIR)
    return f


def latest(ftp, prefix):
    pat = re.compile(rf"^{re.escape(prefix)}_.*\.csv$", re.I)
    cands = []
    try:
        for name, facts in ftp.mlsd(facts=["modify", "type"]):
            if facts.get("type") == "file" and pat.match(name):
                cands.append((facts.get("modify", "")[:14], name))
    except ftplib.error_perm:
        for name in ftp.nlst():
            if pat.match(name):
                try:
                    m = ftp.sendcmd("MDTM " + name)[4:].strip()
                except Exception:
                    m = "19700101000000"
                cands.append((m[:14], name))
    if not cands:
        raise SystemExit(f"Nessun file {prefix}_*.csv trovato")

    def stamp_nome(nome):
        m = re.search(r"(\d{14})", nome)
        return m.group(1) if m else "00000000000000"

    # ordina prima per data scritta nel nome, poi per data di modifica
    cands.sort(key=lambda c: (stamp_nome(c[1]), c[0]))
    print(f"Prefisso {prefix}: {len(cands)} file trovati, ultimi:")
    for mod, nome in cands[-3:]:
        print(f"   {nome} (modifica server {mod})")

    scelto = cands[-1]
    stamp = stamp_nome(scelto[1])
    return (stamp if stamp != "00000000000000" else scelto[0]), scelto[1]


def col_idx(letters):
    n = 0
    for ch in letters.upper():
        n = n * 26 + ord(ch) - 64
    return n - 1


def to_num(s):
    s = s.strip().replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s)


def leggi_cella(ftp, prefix, riga, col):
    modify, nome = latest(ftp, prefix)
    buf = io.BytesIO()
    ftp.retrbinary("RETR " + nome, buf.write)
    raw = buf.getvalue()
    try:
        txt = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        txt = raw.decode("latin-1")
    try:
        dialect = csv.Sniffer().sniff(txt[:4096], delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";"
    rows = list(csv.reader(io.StringIO(txt), dialect))
    val = to_num(rows[riga - 1][col_idx(col)])
    dt = (datetime.strptime(modify[:14], "%Y%m%d%H%M%S")
          .replace(tzinfo=timezone.utc)
          .astimezone(ZoneInfo("Europe/Rome")))
    print(f"{nome} ({dt:%d/%m/%Y %H:%M}) -> {col}{riga} = {val}")
    return val, dt


ftp = connect()
A, d1 = leggi_cella(ftp, "1_1", 12, "Z")
B, d2 = leggi_cella(ftp, "1_2", 12, "AD")
C, d3 = leggi_cella(ftp, "1_3", 12, "Z")
D, d4 = leggi_cella(ftp, "1_4", 12, "Z")
E, d5 = leggi_cella(ftp, "100_301", 12, "Z")
ftp.quit()

ultimo = max(d1, d2, d3, d4, d5).strftime("%d/%m/%Y %H:%M")

F = E - B
G = C - A
for nome, v in (("F", F), ("G", G)):
    if v < 0:
        print(f"ATTENZIONE: {nome} negativo ({v}), impostato a 0")
F, G = max(F, 0), max(G, 0)

TOT_TXT = f"Potenza totale utilizzata {PERIODO}"
GRIGIO = "#999999"
flussi = [
    ("Potenza importata dalla rete", F, TOT_TXT, "#ec1313"),
    ("Potenza esportata dal fotovoltaico", B, TOT_TXT, "#009900"),
    (TOT_TXT, D, "Potenza Ed. Principale", GRIGIO),
    (TOT_TXT, C, "Potenza Ed. Laboratorio", GRIGIO),
    ("Potenza Ed. Laboratorio", A, "Potenza UTA-Clima", GRIGIO),
    ("Potenza Ed. Laboratorio", G, "Potenza altre utenze", GRIGIO),
]

os.makedirs("output", exist_ok=True)

# 1) testo nel formato SankeyMATIC (flussi + impostazioni + spostamenti)
IMPOSTAZIONI = """
size w 800
  h 700
margin l 4
  r 40
  t 83
  b 0
bg color #ffffff
  transparent N
node w 7
  h 49
  spacing 50.5
  border 10
  theme c
  color #888888
  opacity 0
flow curvature 0.5
  inheritfrom none
  color #ec1313
  opacity 0.45
layout order automatic
  justifyorigins N
  justifyends N
  reversegraph N
  attachincompletesto nearest
labels color #000000
  hide N
  highlight 0.55
  fontface sans-serif
  linespacing 0.2
  relativesize 115
  magnify 110
labelname appears Y
  size 15
  weight 400
labelvalue appears Y
  fullprecision Y
  position above
  weight 400
labelposition autoalign 1
  scheme auto
  first before
  breakpoint 5
value format ',.'
  prefix ''
  suffix ' kW'
themeoffset a 5
  b 6
  c 0
  d 0
meta mentionsankeymatic N
  listimbalances Y

// === Moved Nodes ===

move Potenza esportata dal fotovoltaico -0.00232, -0.21948
move Potenza Ed. Laboratorio 0, -0.24171
move Potenza UTA-Clima -0.06257, -0.03342
move Potenza altre utenze -0.0672, -0.18749
move Potenza Ed. Principale 0.08575, 0.01727
"""

with open("output/sankeymatic.txt", "w", encoding="utf-8") as fh:
    for s, v, t, c in flussi:
        colore = f" {c}" if c != GRIGIO else ""
        fh.write(f"{s} [{v:g}] {t}{colore}\n")
    fh.write("\n" + IMPOSTAZIONI.strip() + "\n")

# ===================== IMMAGINE =====================
# ---- impostazioni (pixel su una tela di 1600 x 1400) ----
W, H, DPI = 1600, 1400, 100
LARG_NODO = 34          # larghezza dei blocchi
MARGINE_NODO = 10       # spazio sopra/sotto i flussi dentro il blocco
ALTEZZA_FLUSSO_TOT = 606  # altezza (px) del flusso del blocco "totale"
OPACITA_FLUSSI = 0.45
COLORE_NODI = "#0f4d3c"
COLORE_ROSSO = "#ec1313"
MOSTRA_DATA = True       # metti False per togliere la scritta in alto
CARATTERE = ["Arial", "Liberation Sans", "Helvetica", "DejaVu Sans"]

NOME_IMG = {TOT_TXT: "Potenza totale utilizzata"}   # nome mostrato nel blocco

# posizione di ogni blocco: (x del lato sinistro, y del centro), in pixel
POS = {
    "Potenza importata dalla rete":       (382, 592),
    "Potenza esportata dal fotovoltaico": (382, 960),
    TOT_TXT:                              (670, 680),
    "Potenza Ed. Principale":             (1032, 515),
    "Potenza Ed. Laboratorio":            (958, 867),
    "Potenza UTA-Clima":                  (1191, 754),
    "Potenza altre utenze":               (1187, 999),
}
SINISTRA = {"Potenza importata dalla rete", "Potenza esportata dal fotovoltaico"}
CON_RIQUADRO = {TOT_TXT, "Potenza Ed. Laboratorio"}

nodi = list(POS)
entrata = {n: 0.0 for n in nodi}
uscita = {n: 0.0 for n in nodi}
for s, v, t, c in flussi:
    uscita[s] += v
    entrata[t] += v
valore = {n: max(entrata[n], uscita[n]) for n in nodi}

tot = valore[TOT_TXT] or 1.0
k = ALTEZZA_FLUSSO_TOT / tot                      # pixel per kW
alt = {n: valore[n] * k + 2 * MARGINE_NODO for n in nodi}
top = {n: POS[n][1] - alt[n] / 2 for n in nodi}
xl = {n: POS[n][0] for n in nodi}

# posizione verticale di ogni flusso dentro i blocchi (dall'alto in basso)
y_out, y_in = {}, {}
for n in nodi:
    cur = top[n] + MARGINE_NODO
    for i in sorted((i for i, f in enumerate(flussi) if f[0] == n),
                    key=lambda i: POS[flussi[i][2]][1]):
        y_out[i] = cur
        cur += flussi[i][1] * k
    cur = top[n] + MARGINE_NODO
    for i in sorted((i for i, f in enumerate(flussi) if f[2] == n),
                    key=lambda i: POS[flussi[i][0]][1]):
        y_in[i] = cur
        cur += flussi[i][1] * k

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = CARATTERE
fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor="white")
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(H, 0)
ax.axis("off")


def pt(px):
    return px * 72 / DPI


# flussi
for i, (s, v, t, c) in enumerate(flussi):
    col = to_rgb(COLORE_ROSSO if c == GRIGIO else c)
    x0, x1 = xl[s] + LARG_NODO, xl[t]
    xm = (x0 + x1) / 2
    ys, yt, th = y_out[i], y_in[i], v * k
    verts = [(x0, ys), (xm, ys), (xm, yt), (x1, yt),
             (x1, yt + th),
             (xm, yt + th), (xm, ys + th), (x0, ys + th),
             (x0, ys)]
    codes = [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4,
             Path.LINETO,
             Path.CURVE4, Path.CURVE4, Path.CURVE4,
             Path.CLOSEPOLY]
    ax.add_patch(PathPatch(Path(verts, codes), facecolor=col + (OPACITA_FLUSSI,),
                           edgecolor="none", zorder=2))

# blocchi
for n in nodi:
    ax.add_patch(plt.Rectangle((xl[n], top[n]), LARG_NODO, alt[n],
                               facecolor=COLORE_NODI, edgecolor="none", zorder=3))

# etichette: valore grande sopra, nome sotto
etichette = []
for n in nodi:
    yc = POS[n][1]
    if n in SINISTRA:
        x, ha = xl[n] - 12, "right"
    else:
        x, ha = xl[n] + LARG_NODO + 12, "left"
    tv = ax.text(x, yc - 16, f"{valore[n]:.3f} kW", ha=ha, va="center",
                 fontsize=pt(36), color="black", zorder=6)
    tn = ax.text(x, yc + 19, NOME_IMG.get(n, n), ha=ha, va="center",
                 fontsize=pt(26), color="black", zorder=6)
    if n in SINISTRA:  # se il nome e' troppo lungo, rimpicciolisci il carattere
        spazio = x - 18
        larg = tn.get_window_extent(fig.canvas.get_renderer()).width
        if larg > spazio:
            tn.set_fontsize(pt(26) * spazio / larg)
    etichette.append((n, tv, tn))

# riquadro chiaro dietro le etichette dei blocchi centrali
fig.canvas.draw()
rend = fig.canvas.get_renderer()
inv = ax.transData.inverted()
for n, tv, tn in etichette:
    if n not in CON_RIQUADRO:
        continue
    pts = []
    for t_ in (tv, tn):
        bb = t_.get_window_extent(rend)
        pts += [inv.transform((bb.x0, bb.y0)), inv.transform((bb.x1, bb.y1))]
    x0 = min(p[0] for p in pts) - 9
    x1 = max(p[0] for p in pts) + 9
    y0 = min(p[1] for p in pts) - 8
    y1 = max(p[1] for p in pts) + 8
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0,
                                boxstyle="round,pad=0,rounding_size=10",
                                facecolor=(1, 1, 1, 0.65), edgecolor="none",
                                zorder=2.5))

if MOSTRA_DATA:
    ax.text(30, 50, f"Mappa distribuzione di Potenza attiva - dati aggiornati al {ultimo}",
            ha="left", va="center", fontsize=pt(26), color="#555555")

fig.savefig("output/sankey.png", dpi=DPI, facecolor="white")
plt.close(fig)

# 3) data e ora dell'aggiornamento
with open("output/ultimo_aggiornamento.txt", "w", encoding="utf-8") as fh:
    fh.write(ultimo + "\n")

if os.environ.get("GITHUB_OUTPUT"):
    with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
        fh.write(f"ultimo={ultimo}\n")

print("Immagine creata. Dati aggiornati al", ultimo)
