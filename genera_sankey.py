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

# 1) testo nel formato SankeyMATIC
with open("output/sankeymatic.txt", "w", encoding="utf-8") as fh:
    for s, v, t, c in flussi:
        colore = f" {c}" if c != GRIGIO else ""
        fh.write(f"{s} [{v:g}] {t}{colore}\n")

# 2) immagine
nodi = []
for s, v, t, c in flussi:
    for n in (s, t):
        if n not in nodi:
            nodi.append(n)

def rgba(hex_color, alpha):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"

colori_link = [rgba(c, 0.6) if c != GRIGIO else rgba(c, 0.4) for *_, c in flussi]

fig = go.Figure(go.Sankey(
    arrangement="snap",
    node=dict(label=nodi, pad=25, thickness=20),
    link=dict(
        source=[nodi.index(s) for s, *_ in flussi],
        target=[nodi.index(t) for _, _, t, _ in flussi],
        value=[v for _, v, _, _ in flussi],
        color=colori_link,
    ),
))
fig.update_layout(
    title=f"Flussi di potenza - {PERIODO} - Dati aggiornati al {ultimo}",
    font_size=14, width=1400, height=700, paper_bgcolor="white",
)
fig.write_image("output/sankey.png", scale=2)

# 3) data e ora dell'aggiornamento
with open("output/ultimo_aggiornamento.txt", "w", encoding="utf-8") as fh:
    fh.write(ultimo + "\n")

if os.environ.get("GITHUB_OUTPUT"):
    with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
        fh.write(f"ultimo={ultimo}\n")

print("Immagine creata. Dati aggiornati al", ultimo)
