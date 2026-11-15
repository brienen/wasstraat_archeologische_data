"""Hulpfuncties voor veilig loggen.

Verbindingsgegevens zoals SQLALCHEMY_DATABASE_URI en MONGO_URI bevatten een
wachtwoord. Log ze alleen via maskeerWachtwoord(), zodat het wachtwoord niet
in de logs van Flask en Airflow terechtkomt (issue 77).
"""

MASKER = "***"


def maskeerWachtwoord(uri):
    """Vervang het wachtwoord in een verbindings-URI door '***'.

    Werkt voor URI's van de vorm schema://gebruiker:wachtwoord@host/..., zoals
    'postgresql://wasstraat:geheim@postgres/wasstraat' of
    'mongodb://root:geheim@mongo/?authSource=admin'. Het wachtwoord loopt tot
    het laatste '@', zodat ook een wachtwoord met '@', '/' of ':' erin volledig
    gemaskeerd wordt. Gebruikersnaam, host, poort, database en opties blijven
    leesbaar.

    Args:
        uri: De verbindings-URI (tekst, of een object waarvan str() een URI geeft),
            of None.

    Returns:
        De URI met '***' in plaats van het wachtwoord. Een URI zonder wachtwoord
        komt ongewijzigd terug (als tekst); None en een lege tekst komen
        ongewijzigd terug.
    """
    if uri is None or uri == "":
        return uri
    tekst = str(uri)

    schema, scheiding, rest = tekst.partition("://")
    if not scheiding or "@" not in rest:
        return tekst

    gebruikersdeel, _, hostdeel = rest.rpartition("@")
    gebruiker, dubbelepunt, _ = gebruikersdeel.partition(":")
    if not dubbelepunt:
        # Alleen een gebruikersnaam, geen wachtwoord
        return tekst
    return f"{schema}://{gebruiker}:{MASKER}@{hostdeel}"
