import os, re, csv, io, ftplib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import plotly.graph_objects as go

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

TOT = f"Potenza totale utilizzata {PERIODO}"
GRIGIO = "#999999"
flussi = [
    ("Potenza importata dalla rete", F, TOT, "#ec1313"),
    ("Potenza esportata dal fotovoltaico", B, TOT, "#009900"),
    (TOT, D, "Potenza Ed. Principale", GRIGIO),
    (TOT, C, "Potenza Ed. Laboratorio", GRIGIO),
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

# 2) immagine (stessi parametri di SankeyMATIC, per quanto possibile)
nodi = []
for s, v, t, c in flussi:
    for n in (s, t):
        if n not in nodi:
            nodi.append(n)

# valore di ogni blocco = totale dei flussi che entrano o escono
entrata = {n: 0 for n in nodi}
uscita = {n: 0 for n in nodi}
for s, v, t, c in flussi:
    uscita[s] += v
    entrata[t] += v
# valore sopra, nome sotto (labelvalue position above)
etichette = [f"{max(entrata[n], uscita[n]):,.3f} kW<br>{n}" for n in nodi]


def rgba(hex_color, alpha):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# i flussi senza colore usano il colore di default di SankeyMATIC (#ec1313)
FLUSSO_DEFAULT = "#ec1313"
colori_link = [rgba(FLUSSO_DEFAULT if c == GRIGIO else c, 0.45)
               for *_, c in flussi]

# posizioni: colonna (x) e altezza (y) di base, a cui si somma lo "move"
# di SankeyMATIC. Valori da 0 a 1 (y=0 in alto).
BASE = {
    "Potenza importata dalla rete":       (0.001, 0.30),
    "Potenza esportata dal fotovoltaico": (0.001, 0.85),
    TOT:                                  (0.34, 0.55),
    "Potenza Ed. Principale":             (0.67, 0.30),
    "Potenza Ed. Laboratorio":            (0.67, 0.75),
    "Potenza UTA-Clima":                  (0.999, 0.65),
    "Potenza altre utenze":               (0.999, 0.95),
}
MOVE = {
    "Potenza esportata dal fotovoltaico": (-0.00232, -0.21948),
    "Potenza Ed. Laboratorio":            (0, -0.24171),
    "Potenza UTA-Clima":                  (-0.06257, -0.03342),
    "Potenza altre utenze":               (-0.0672, -0.18749),
    "Potenza Ed. Principale":             (0.08575, 0.01727),
}


def pos(n):
    x, y = BASE[n]
    dx, dy = MOVE.get(n, (0, 0))
    return (min(max(x + dx, 0.001), 0.999),
            min(max(y + dy, 0.001), 0.999))


xs = [pos(n)[0] for n in nodi]
ys = [pos(n)[1] for n in nodi]

fig = go.Figure(go.Sankey(
    arrangement="fixed",
    valueformat=",.3f",
    valuesuffix=" kW",
    node=dict(label=etichette, x=xs, y=ys, pad=50, thickness=7,
              color="#888888", line=dict(color="#888888", width=0)),
    link=dict(
        source=[nodi.index(s) for s, *_ in flussi],
        target=[nodi.index(t) for _, _, t, _ in flussi],
        value=[v for _, v, _, _ in flussi],
        color=colori_link,
    ),
))
fig.update_layout(
    title=dict(text=f"Flussi di potenza - {PERIODO}<br>"
                    f"<sup>Dati aggiornati al {ultimo}</sup>",
               x=0.02),
    font=dict(family="sans-serif", size=15, color="#000000"),
    width=800, height=700,
    margin=dict(l=4, r=40, t=83, b=0),
    paper_bgcolor="#ffffff",
)
fig.write_image("output/sankey.png", scale=2)

# 3) data e ora dell'aggiornamento
with open("output/ultimo_aggiornamento.txt", "w", encoding="utf-8") as fh:
    fh.write(ultimo + "\n")

if os.environ.get("GITHUB_OUTPUT"):
    with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
        fh.write(f"ultimo={ultimo}\n")

print("Immagine creata. Dati aggiornati al", ultimo)
