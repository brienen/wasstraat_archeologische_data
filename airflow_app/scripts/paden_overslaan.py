#!/usr/bin/env python3
"""Filter de Access-databases van importMDB.sh met paden_overslaan uit correcties.yml (issue 84).

Gebruik (zie importMDB.sh)::

    printf '%s\\0' "${MDB_FILES[@]}" | python3 paden_overslaan.py <invoermap> > gefilterd.lst

Leest NUL-gescheiden paden van stdin en schrijft de paden die niet worden
overgeslagen NUL-gescheiden naar stdout, in dezelfde volgorde. Per
overgeslagen bestand komt er een regel op stderr (en daarmee in het log van
importMDB.sh), gevolgd door een telling. De patronen zijn relatief aan de
invoermap (het eerste argument van importMDB.sh).

Het correctiebestand is AIRFLOW_CORRECTIES_CONFIG, anders
/opt/airflow/config/correcties.yml. Ontbreekt het bestand of de sectie, dan
komen alle paden ongewijzigd terug. De logica staat in
airflow_app/dags/wasstraat/paden_overslaan.py, dezelfde module die de
registratie van bronbestanden en de selectie van afbeeldingen gebruiken.
"""
import logging
import os
import sys

# De module staat in de map dags naast deze map (/opt/airflow/dags in de container)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dags'))

from wasstraat import paden_overslaan  # noqa: E402


def main(argv):
    """Filter de paden van stdin; retourneert de exitcode."""
    if len(argv) != 2:
        print("Aanroepen met de invoermap als enig argument; paden NUL-gescheiden op stdin.", file=sys.stderr)
        return 2
    invoermap = argv[1]
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format='%(levelname)s: %(message)s')

    invoer = sys.stdin.buffer.read().decode('utf-8', 'surrogateescape')
    paden = [pad for pad in invoer.split('\0') if pad]
    pad_correcties = os.environ.get('AIRFLOW_CORRECTIES_CONFIG') or paden_overslaan.STANDAARD_CORRECTIES
    patronen = paden_overslaan.laadPatronen(paden_overslaan.leesCorrectiebestand(pad_correcties))
    behouden = paden_overslaan.filterPaden(paden, invoermap, patronen=patronen,
                                           omschrijving='MDB/ACCDB-bestand(en)')

    uit = sys.stdout.buffer
    for pad in behouden:
        uit.write(pad.encode('utf-8', 'surrogateescape') + b'\0')
    uit.flush()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
