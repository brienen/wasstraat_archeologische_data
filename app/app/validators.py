from wtforms.validators import ValidationError
from models import ABR, DiscrArtefactsoortEnum
import shared.const as const


class ABRCompare_Artefactsoort:
    """
    Compares the values of two fields.
    :param artefactsoort:
        The name of the artefactsoort field to compare to.
    :param message:
        Error message to raise in case of a validation error. Can be
        interpolated with `%(other_label)s` and `%(other_name)s` to provide a
        more helpful error.
    """

    def __init__(self, artefactsoort, message=None):
        self.artefactsoort = artefactsoort
        self.message = message

    def __call__(self, form, field):
        try:
            artefactsoort = form[self.artefactsoort]
        except KeyError as exc:
            raise ValidationError(
                field.gettext("Invalid field name '%s'.") % self.artefactsoort
            ) from exc
        if (field.data.uri == const.ABR_URI_ORGANISCH #Organisch
            and artefactsoort.data in [DiscrArtefactsoortEnum.Dierlijk_Bot, DiscrArtefactsoortEnum.Hout, DiscrArtefactsoortEnum.Leer, 
                DiscrArtefactsoortEnum.Menselijk_Bot, DiscrArtefactsoortEnum.Schelp, DiscrArtefactsoortEnum.Textiel]):
            return
        elif (field.data.uri == const.ABR_URI_KARAMIEK #Keramiek
            and artefactsoort.data in [DiscrArtefactsoortEnum.Aardewerk, DiscrArtefactsoortEnum.Bouwaardewerk, DiscrArtefactsoortEnum.Kleipijp]): 
            return
        elif (field.data.uri == const.ABR_URI_STEEN #Steen
            and artefactsoort.data in [DiscrArtefactsoortEnum.Steen]): 
            return
        elif (field.data.uri == const.ABR_URI_GLAS #Glas
            and artefactsoort.data in [DiscrArtefactsoortEnum.Glas]): 
            return
        elif (field.data.uri == const.ABR_URI_METAAL #Metaal
            and artefactsoort.data in [DiscrArtefactsoortEnum.Metaal, DiscrArtefactsoortEnum.Munt]): 
            return
        elif artefactsoort.data in [DiscrArtefactsoortEnum.Onbekend]:
            return
            
        d = {
            "artefactsoort_label": hasattr(artefactsoort, "label")
            and artefactsoort.label.text
            or self.artefactsoort,
            "artefactsoort_name": self.artefactsoort,
        }
        message = self.message
        if message is None:
            message = field.gettext("Field must be equal to %(other_name)s.")

        raise ValidationError(message % d)



class ABRCompare_SUBArtefactsoort:
    """
    Compares the values of two fields.
    :param artefactsoort:

    ABR_URI_HOUT = 'https://data.cultureelerfgoed.nl/term/id/abr/eb8d8e6b-c5e1-4ec5-950b-be8b9b799f20'
    ABR_URI_LEER = 'https://data.cultureelerfgoed.nl/term/id/abr/1d2d66f1-de58-4082-8aa9-53a67599faf0'
    ABR_URI_AARDEWERK = 'https://data.cultureelerfgoed.nl/term/id/abr/1d2d66f1-de58-4082-8aa9-53a67599faf0'
    ABR_URI_MENSELIJK_BOT = 'https://data.cultureelerfgoed.nl/term/id/abr/52ec1556-fa45-4e04-9fca-32f36c20d763'
    ABR_URI_DIERLIJK_BOT = 'https://data.cultureelerfgoed.nl/term/id/abr/87a15ea6-0ed9-4bab-85bc-c0e32281e7ee'
    ABR_URI_BOUWAARDEWERK= 'https://data.cultureelerfgoed.nl/term/id/abr/e9c85dbc-f215-4249-ba1f-7d84a22eaa82'
    ABR_URI_SCHELP = 'https://data.cultureelerfgoed.nl/term/id/abr/ea0bcd79-31b9-4645-9783-add79577de3e'
    ABR_URI_TEXTIEL = 'https://data.cultureelerfgoed.nl/term/id/abr/d386b3f4-7aa9-4fe6-a64d-2b659fe6b197'    :param message:

            Error message to raise in case of a validation error. Can be
        interpolated with `%(other_label)s` and `%(other_name)s` to provide a
        more helpful error.
    """

    def __init__(self, artefactsoort, message=None):
        self.artefactsoort = artefactsoort
        self.message = message

    def __call__(self, form, field):
        try:
            artefactsoort = form[self.artefactsoort]
        except KeyError as exc:
            raise ValidationError(
                field.gettext("Invalid field name '%s'.") % self.artefactsoort
            ) from exc
        if (field.data.uri == const.ABR_URI_HOUT 
            and artefactsoort.data in [DiscrArtefactsoortEnum.Hout]):
            return
        elif (field.data.uri == const.ABR_URI_LEER 
            and artefactsoort.data in [DiscrArtefactsoortEnum.Leer]): 
            return
        elif (field.data.uri == const.ABR_URI_AARDEWERK #Steen
            and artefactsoort.data in [DiscrArtefactsoortEnum.Aardewerk]): 
            return
        elif (field.data.uri == const.ABR_URI_MENSELIJK_BOT #Glas
            and artefactsoort.data in [DiscrArtefactsoortEnum.Menselijk_Bot]): 
            return
        elif (field.data.uri == const.ABR_URI_DIERLIJK_BOT #Metaal
            and artefactsoort.data in [DiscrArtefactsoortEnum.Dierlijk_Bot]): 
            return
        elif (field.data.uri == const.ABR_URI_BOUWAARDEWERK #Metaal
            and artefactsoort.data in [DiscrArtefactsoortEnum.Bouwaardewerk]): 
            return
        elif (field.data.uri == const.ABR_URI_SCHELP #Metaal
            and artefactsoort.data in [DiscrArtefactsoortEnum.Schelp]): 
            return
        elif (field.data.uri == const.ABR_URI_TEXTIEL #Metaal
            and artefactsoort.data in [DiscrArtefactsoortEnum.Textiel]): 
            return
            
        d = {
            "artefactsoort_label": hasattr(artefactsoort, "label")
            and artefactsoort.label.text
            or self.artefactsoort,
            "artefactsoort_name": self.artefactsoort,
        }
        message = self.message
        if message is None:
            message = field.gettext("Field must be equal to %(other_name)s.")

        raise ValidationError(message % d)
