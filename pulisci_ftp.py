import os, re, ftplib
from collections import defaultdict

HOST = os.environ["FTP_HOST"]
PORT = int(os.environ.get("FTP_PORT") or "21")
USER = os.environ["FTP_USER"]
PASSW = os.environ["FTP_PASS"]
FTP_DIR = os.environ.get("FTP_DIR") or "/"
TENERE = int(os.environ.get("TENERE") or "5")
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"

if TENERE < 1:
    raise SystemExit("TENERE deve essere almeno 1")


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


ftp = connect()
try:
    nomi = [n for n, fa in ftp.mlsd(facts=["type"]) if fa.get("type") == "file"]
except ftplib.error_perm:
    nomi = ftp.nlst()

# nome gruppo = parte prima della data di 14 cifre (es. 1_1_20261116135208.csv -> 1_1)
pat = re.compile(r"^(.+)_(\d{14})\.csv$", re.I)
gruppi = defaultdict(list)
for n in nomi:
    m = pat.match(n)
    if m:
        gruppi[m.group(1)].append((m.group(2), n))

if not gruppi:
    raise SystemExit("Nessun file CSV riconosciuto: non cancello nulla.")

print("MODALITA' SIMULAZIONE: non cancello nulla" if DRY_RUN
      else "MODALITA' REALE: cancello i file vecchi")

totale = 0
for gruppo, lista in sorted(gruppi.items()):
    lista.sort()  # dal piu' vecchio al piu' recente (data nel nome)
    vecchi = lista[:-TENERE]
    print(f"\nGruppo {gruppo}: {len(lista)} file, ne tengo {min(TENERE, len(lista))}, "
          f"da cancellare {len(vecchi)}")
    for _, nome in vecchi:
        if DRY_RUN:
            print("   [simulazione] cancellerei", nome)
        else:
            try:
                ftp.delete(nome)
                print("   cancellato", nome)
                totale += 1
            except Exception as e:
                print("   ERRORE su", nome, "->", e)

ftp.quit()
print(f"\nFine. File cancellati: {totale}")
