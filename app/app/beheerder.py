"""
Aanmaken van de beheerder van de Flask App bij de eerste start.

Wordt aangeroepen door scripts/flask/init.sh. Het wachtwoord komt uit de
omgevingsvariabele FLASK_ADMIN_PASSWORD (config/flask.env), die
init-config.sh bij de installatie vult met een gegenereerd wachtwoord.
Een bestaande beheerder wordt nooit aangepast.
"""
from werkzeug.security import check_password_hash


GEBRUIKERSNAAM = "admin"
WACHTWOORD_VARIABELE = "FLASK_ADMIN_PASSWORD"
# Placeholder uit config/flask.env.example; init-config.sh vervangt deze
PLACEHOLDER_WACHTWOORD = "flask_admin_secret_42"
# Oud gedrag, alleen voor installaties waarvan flask.env de variabele nog mist
TERUGVAL_WACHTWOORD = "admin"


def bepaalWachtwoord(omgeving):
    """
    Bepaal het wachtwoord voor een nieuw aan te maken beheerder.

    Args:
        omgeving: Mapping met omgevingsvariabelen (meestal os.environ).

    Returns:
        str: Het wachtwoord uit FLASK_ADMIN_PASSWORD, of het oude
        standaardwachtwoord 'admin' als de variabele ontbreekt of leeg is.
    """
    wachtwoord = (omgeving.get(WACHTWOORD_VARIABELE) or "").strip()

    if not wachtwoord:
        print(f"==> WAARSCHUWING: {WACHTWOORD_VARIABELE} ontbreekt in config/flask.env. "
              f"De beheerder '{GEBRUIKERSNAAM}' krijgt het onveilige standaardwachtwoord "
              f"'{TERUGVAL_WACHTWOORD}'. Wijzig dit direct na het inloggen via het gebruikersmenu.")
        return TERUGVAL_WACHTWOORD

    if wachtwoord == PLACEHOLDER_WACHTWOORD:
        print(f"==> WAARSCHUWING: {WACHTWOORD_VARIABELE} staat nog op de voorbeeldwaarde uit "
              f"config/flask.env.example. Wijzig het wachtwoord van '{GEBRUIKERSNAAM}' direct "
              f"na het inloggen via het gebruikersmenu.")

    return wachtwoord


def maakBeheerder(sm, omgeving):
    """
    Maak de beheerder aan als die nog niet bestaat.

    Een bestaande beheerder houdt zijn wachtwoord: FLASK_ADMIN_PASSWORD geldt
    alleen bij het aanmaken. Wijkt het wachtwoord van de bestaande beheerder af
    van FLASK_ADMIN_PASSWORD, dan staat dat in de log.

    Args:
        sm: De security manager van Flask-AppBuilder (appbuilder.sm).
        omgeving: Mapping met omgevingsvariabelen (meestal os.environ).

    Returns:
        bool: True als de beheerder is aangemaakt, anders False.
    """
    bestaande = sm.find_user(username=GEBRUIKERSNAAM)
    if bestaande:
        print(f"==> Beheerder '{GEBRUIKERSNAAM}' bestaat al, wachtwoord blijft ongewijzigd")
        wachtwoord = (omgeving.get(WACHTWOORD_VARIABELE) or "").strip()
        if wachtwoord and not check_password_hash(bestaande.password or "", wachtwoord):
            print(f"==> LET OP: het wachtwoord van '{GEBRUIKERSNAAM}' wijkt af van "
                  f"{WACHTWOORD_VARIABELE} in config/flask.env. Deze variabele wordt alleen "
                  f"gebruikt bij het aanmaken van de beheerder. Log in met het bestaande "
                  f"wachtwoord en wijzig het via het gebruikersmenu.")
        return False

    wachtwoord = bepaalWachtwoord(omgeving)
    print(f"==> Beheerder '{GEBRUIKERSNAAM}' aanmaken")
    gebruiker = sm.add_user(
        username=GEBRUIKERSNAAM,
        first_name="Admin",
        last_name="User",
        email="admin@local",
        role=sm.find_role("Admin"),
        password=wachtwoord,
    )
    if not gebruiker:
        print(f"==> FOUT: beheerder '{GEBRUIKERSNAAM}' kon niet worden aangemaakt")
        return False
    return True
