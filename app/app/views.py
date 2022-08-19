import copy

from flask_appbuilder import GroupByChartView, MultipleView
from flask_appbuilder.models.group import aggregate_count
from flask_appbuilder.models.sqla.filters import FilterEqual, FilterGreater

from app import db, appbuilder
from models import Aardewerk, Stelling, Doos, Artefact, Foto, Spoor, Project,Put, Vondst, Vlak, DiscrArtefactsoortEnum, DiscrFotosoortEnum, Dierlijk_Bot, Glas, Hout, Bouwaardewerk, Kleipijp, Leer, Menselijk_Bot, Metaal, Munt, Schelp, Steen, Textiel, Vulling, Opgravingsfoto, Objectfoto, Velddocument, Overige_afbeelding, Monster, Monster_Botanie, Monster_Schelp
from widgets import MediaListWidget
from baseviews import WSModelView, WSGeoModelView
from interface import WSSQLAInterface, WSGeoSQLAInterface

import util as util

from flask_appbuilder.actions import action
from flask import redirect, request, url_for
import flask_appbuilder.hooks as hooks

import logging
logger = logging.getLogger()


flds_migratie_info = ("Migratie-informatie", {"fields": ["soort","brondata","uuid"],"expanded": False})

class ArtefactChartView(GroupByChartView):
    datamodel = WSSQLAInterface(Artefact)
    chart_title = 'Telling Artefacten'

    definitions = [
    {
        'label': 'Soorten Artefact',
        'group': 'artefactsoort',
        'series': [(aggregate_count,'primary_key')],
        'group_by_label': 'Telling'
    },
    {
        'label': 'Origine Artefact',
        'group': 'origine',
        'series': [(aggregate_count,'primary_key')],
        'group_by_label': 'Telling'
    }
]

class ArtefactLineChartView(GroupByChartView):
    datamodel = WSSQLAInterface(Artefact)
    chart_title = 'Datering Artefacten'
    chart_type = 'LineChart'

    definitions = [
    {
        'label': 'Datering Vanaf',
        'group': 'datering_vanaf',
        'series': [(aggregate_count,'primary_key')],
        'group_by_label': 'Datum vanaf'
    },
    {
        'label': 'Datering Tot',
        'group': 'datering_tot',
        'series': [(aggregate_count,'primary_key')],
        'group_by_label': 'Datum tot'
    }
]


class ArchFotoView(WSModelView):
    datamodel = WSSQLAInterface(Foto)
    list_widget = MediaListWidget
    list_title = "Foto's"
    list_columns = ["fileName", 'koppeling', 'photo_img_thumbnail']
    show_columns = ["project", "fototype", "fileName", 'directory', 'koppeling', 'photo_img']
    add_template = 'widgets/add_photo.html'
    show_fieldsets = [
        ("Projectvelden", {"columns": [
            {"fields": ["project", "fotosoort"], "grid":6},        
            {"fields": ["fileName", "directory", "fileType", 'mime_type'], "grid":6},        
        ]}),        
        ("Foto", {"fields": ["photo_img"], "grid":12, "fulldisplay": True}),
        flds_migratie_info]
    base_order = ('fileName','asc')



    @action("5linkskantelen", "Kantelen Linksom", "Geselecteerde foto's linksom kantelen?", "fa-rocket")
    def linkskantelen(self, items):
        if isinstance(items, list):
            for foto in items:
                foto = util.rotateImage(foto, 90)
                self.datamodel.edit(foto, raise_exception=True)

            self.update_redirect()
        else:
            foto = util.rotateImage(items, 90)
            self.datamodel.edit(foto)
        return redirect(self.get_redirect())

    @action("6rechtskantelen", "Kantelen Rechtsom", "Geselecteerde foto's rechtsom kantelen?", "fa-rocket")
    def rechtskantelen(self, items):
        if isinstance(items, list):
            for foto in items:
                foto = util.rotateImage(foto, -90)
                self.datamodel.edit(foto, raise_exception=True)

            self.update_redirect()
        else:
            foto = util.rotateImage(items, -90)
            self.datamodel.edit(foto)
        return redirect(self.get_redirect())


    view_mapper = dict()
    @hooks.before_request(only=["edit", "show"])
    def Request_Handler(self):
        '''
        Request mappert that makes sure the detail view and update view with all details of the inherited class are shown. 
        Necessary for inheritance.
        '''
        path = request.path 
        lst_path = path[1:].split('/')

        foto = db.session.query(Foto).get(int(lst_path[2]))
        expected_route = self.view_mapper.get(foto.fotosoort.value)

        if expected_route and str(expected_route).lower() != lst_path[0]:
            return redirect(url_for(f'{expected_route}.{lst_path[1]}', pk=str(lst_path[2])))
        else:
            return None


class ArchOpgravingFotoView(ArchFotoView):
    datamodel = WSSQLAInterface(Opgravingsfoto)
    base_filters = [['fotosoort', FilterEqual, DiscrFotosoortEnum.Opgravingsfoto.value]]
    list_title = "Opgravingsfoto's"
    ArchFotoView.view_mapper.update({DiscrFotosoortEnum.Opgravingsfoto.value: 'ArchOpgravingFotoView'})

class ArchObjectFotoView(ArchFotoView):
    datamodel = WSSQLAInterface(Objectfoto)
    base_filters = [['fotosoort', FilterEqual, DiscrFotosoortEnum.Objectfoto.value]]
    list_title = "Artefactfoto's"
    search_exclude_columns = ['artefact']
    show_columns = ["project", "fototype", 'omschrijving', 'materiaal', 'richting', 'datum', "vondstnr", "subnr", "fotonr", "artefact", "fileName", 'directory', 'photo_img']
    show_fieldsets = [
        ("Projectvelden", {"columns": [
            {"fields": ["project", "fotosoort", 'omschrijving', 'materiaal', 'richting', 'datum', "vondstnr", "subnr", "fotonr", "artefact"], "grid":6},        
            {"fields": ["fileName", "directory", "fileType", 'mime_type'], "grid":6},        
        ]}),        
        ("Foto", {"fields": ["photo_img"], "grid":12, "fulldisplay": True}),
        flds_migratie_info]

    ArchFotoView.view_mapper.update({DiscrFotosoortEnum.Objectfoto.value: 'ArchObjectFotoView'})
    #edit_fieldsets = show_fieldsets
    #add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "fotosoort")


class ArchVelddocumentView(ArchFotoView):
    datamodel = WSSQLAInterface(Velddocument)
    base_filters = [['fotosoort', FilterEqual, DiscrFotosoortEnum.Velddocument.value]]
    list_title = "Velddocumenten"
    ArchFotoView.view_mapper.update({DiscrFotosoortEnum.Velddocument.value: 'ArchVelddocumentView'})


class ArchOverigeAfbeeldingenView(ArchFotoView):
    datamodel = WSSQLAInterface(Overige_afbeelding)
    base_filters = [['fotosoort', FilterEqual, DiscrFotosoortEnum.Overige_afbeelding.value]]
    list_title = "Overige Afbeeldingen"
    ArchFotoView.view_mapper.update({DiscrFotosoortEnum.Overige_afbeelding.value: 'ArchOverigeAfbeeldingenView'})




class ArchArtefactView_Abstr(WSModelView):
    datamodel = WSSQLAInterface(Artefact)
    # base_permissions = ['can_add', 'can_show']
    list_columns = ["artefactsoort", 'typevoorwerp', "datering", "subnr", "vondst", 'aantal_fotos']
    #list_widget = ListThumbnail
    list_title = "Artefacten"
    related_views = [ArchObjectFotoView]
    search_exclude_columns = ['vondst', 'fotos', 'doos']
    show_fieldsets = [
        ("Projectvelden", {"columns": [
            {"fields": ["project", "vondst", "subnr", "aantal", "abr_materiaal", "artefactsoort", "typevoorwerp", "typecd", "functievoorwerp", "versiering", "beschrijving", "opmerkingen", "doos"], "grid":6},        
            {"fields": ["fotos"], "grid":6, "fulldisplay": True},        
        ]}),        
        ("Algemene Artefactvelden", {"columns": [
            {"fields": ["origine", "conservering", "exposabel", "restauratie", "literatuur", "publicatiecode", "catalogus", "weggegooid"], "grid":6},        
            {"fields": ["aantal", "gewicht", "afmetingen", "formaat_horizontaal", "formaat_vericaal", "compleetheid", "mai", "diversen"], "grid":6},        
        ]}),
        ("Datering", {"columns": [
            {"fields": ["datering_vanaf", "datering_tot", "artefactdatering_vanaf", "artefactdatering_tot"], "grid":6},        
            {"fields": ["vondstdatering_vanaf", "vondstdatering_tot", "spoordatering_vanaf", "spoordatering_tot"], "grid":6},        
        ]}),
    flds_migratie_info]
    edit_fieldsets = show_fieldsets
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")

    view_mapper = dict()
    @hooks.before_request(only=["edit", "show"])
    def Request_Handler(self):
        '''
        Request mappert that makes sure the detail view and update view with all details of the inherited class are shown. 
        Necessary for inheritance.
        '''
        path = request.path 
        lst_path = path[1:].split('/')

        artf = db.session.query(Artefact).get(int(lst_path[2]))
        expected_route = self.view_mapper.get(artf.artefactsoort.value)

        if expected_route and str(expected_route).lower() != lst_path[0]:
            return redirect(url_for(f'{expected_route}.{lst_path[1]}', pk=str(lst_path[2])))
        else:
            return None

       

class ArchArtefactView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Artefact)
    #related_views = [ArchObjectFotoView]


class ArchArtefactMetFotoView(ArchArtefactView_Abstr):
    base_filters = [['aantal_fotos', FilterGreater, 0]]
    list_title = "Artefacten met foto"
    #related_views = [ArchObjectFotoView]


'''
Nog niet
    groep = Column(String(200))
    materiaal = Column(String(200))
    naam_voorwerp = Column(String(200))
    plek = Column(String(200))
    vondstomstandigheden = Column(String(200))
    '''
class ArchAardewerkView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Aardewerk)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Aardewerk.value]]

    list_title = "Aardewerk"
    #related_views = [ArchObjectFotoView]
    aardewerk_fieldset = [("Aardewerkvelden", {"columns": [
            {"fields": ["baksel", "bakseltype", "categorie", "decoratie", "glazuur", "kleur", "oor", "productiewijze"], "grid":6},        
            {"fields": ["bodem", "diameter", "grootste_diameter", "max_diameter", "rand", "rand_bodem", "rand_diameter", "vorm"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView_Abstr.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = aardewerk_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets
    ArchArtefactView_Abstr.view_mapper.update({DiscrArtefactsoortEnum.Aardewerk.value: 'ArchAardewerkView'})

'''
Nog niet
    codes = Column(String(200), comment="codes van type")
    materiaal = Column(String(200), comment="materiaal")
    materiaalsoort = Column(String(200), comment="materiaalsoort")
    past_aan = Column(String(200), comment="vondstnummer waar scherf aan past")
    percentage = Column(String(200), comment="aanwezig percentage van een pot")

'''

class ArchDierlijk_BotView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Dierlijk_Bot)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Dierlijk_Bot.value]]

    list_title = "Dierlijk Bot"
    aardewerk_fieldset = [("Botvelden", {"columns": [
            {"fields": ["diersoort", "bewerkingssporen", "brandsporen", "knaagsporen", "graf", "leeftijd", "pathologie", "symmetrie", "vergroeiing", "oriëntatie"], "grid":6},        
            {"fields": ["lengte", "maat1", "maat2", "maat3", "maat4", "skeletdeel", "slijtage", "slijtage_onderkaaks_DP4", "slijtage_onderkaaks_M1", "slijtage_onderkaaks_M2", "slijtage_onderkaaks_M3"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView_Abstr.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = aardewerk_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets
    ArchArtefactView_Abstr.view_mapper.update({DiscrArtefactsoortEnum.Dierlijk_Bot.value: 'ArchDierlijk_BotView'})




class ArchGlasView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Glas)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Glas.value]]

    list_title = "Glas"
    aardewerk_fieldset = [("Glasvelden", {"columns": [
            {"fields": ["decoratie", "glassoort", "kleur", "vorm_bodem_voet", "vorm_versiering_cuppa", "vorm_versiering_oor_stam"], "grid":6},        
            {"fields": ["diameter_bodem", "diameter_rand", "grootste", "hoogte", "percentage_rand"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView_Abstr.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = aardewerk_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets
    ArchArtefactView_Abstr.view_mapper.update({DiscrArtefactsoortEnum.Glas.value: 'ArchGlasView'})



class ArchHoutView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Hout)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Hout.value]]

    list_title = "Hout"
    hout_fieldset = [("Houtvelden", {"columns": [
            {"fields": ["bewerkingssporen", "decoratie", "determinatieniveau", "gebruikssporen", "houtsoort", "houtsoortcd"], "grid":6},        
            {"fields": ["C14_datering", "dendrodatering", "jaarring_bast_spint", "puntlengte", "puntvorm", "stamcode"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView_Abstr.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = hout_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets
    ArchArtefactView_Abstr.view_mapper.update({DiscrArtefactsoortEnum.Hout.value: 'ArchHoutView'})



class ArchBouwaardewerkView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Bouwaardewerk)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Bouwaardewerk.value]]

    list_title = "Bouwaardewerk"
    Bouwaardewerk_fieldset = [("Bouwaardewerkvelden", {"columns": [
            {"fields": ["baksel", "brandsporen", "gedraaid", "glazuur", "handgevormd", "kleur", "magering", "maker", "oor_steel", "productiewijze", "vorm"], "grid":6},        
            {"fields": ["bodem", "diameter_bodem", "grootste_diameter", "hoogte", "oppervlakte", "past_aan", "randdiameter", "randindex", "randpercentage", "subbaksel", "type_rand", "wanddikte"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView_Abstr.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = Bouwaardewerk_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets
    ArchArtefactView_Abstr.view_mapper.update({DiscrArtefactsoortEnum.Bouwaardewerk.value: 'ArchBouwaardewerkView'})


class ArchKleipijpView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Kleipijp)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Kleipijp.value]]

    list_title = "Kleipijp"
    kleipijp_fieldset = []
    show_fieldsets = copy.deepcopy(ArchArtefactView_Abstr.show_fieldsets)    
    #show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = kleipijp_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets
    ArchArtefactView_Abstr.view_mapper.update({DiscrArtefactsoortEnum.Kleipijp.value: 'ArchKleipijpView'})



class ArchLeerView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Leer)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Leer.value]]

    list_title = "Leer"
    leer_fieldset = [("Leervelden", {"columns": [
            {"fields": ["bewerkingssporen", "bewerking", "bovenleer", "decoratie", "kwaliteit", "leersoort", "toestand"], "grid":6},        
            {"fields": ["beschrijving_zool", "past_aan", "sluiting", "soort_sluiting", "type_bovenleer", "verbinding", "zool", "zoolvorm"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView_Abstr.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = leer_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets
    ArchArtefactView_Abstr.view_mapper.update({DiscrArtefactsoortEnum.Leer.value: 'ArchLeerView'})


class ArchMenselijk_BotView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Menselijk_Bot)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Menselijk_Bot.value]]

    list_title = "Menselijk Bot"
    menselijk_materiaal_fieldset = [("Velden menselijk bot", {"columns": [
            {"fields": ["doos_delft", "doos_lumc", "linkerarm", "linkerbeen", "rechterarm", "rechterbeen", "schedel", "wervelkolom", "skeletelementen"], "grid":6},        
            {"fields": ["breedte_kist_hoofdeinde", "breedte_kist_voeteinde", "lengte_kist", "kist_waargenomen", "primair_graf", "secundair_graf", "plaats"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView_Abstr.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = menselijk_materiaal_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets
    ArchArtefactView_Abstr.view_mapper.update({DiscrArtefactsoortEnum.Menselijk_Bot.value: 'ArchMenselijk_BotView'})



class ArchMetaalView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Metaal)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Metaal.value]]

    list_title = "Metaal"
    metaal_fieldset = [("Metaalvelden", {"columns": [
            {"fields": ["bewerking", "decoratie", "diverse"], "grid":6},        
            {"fields": ["metaalsoort", "oppervlak", "percentage"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView_Abstr.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = metaal_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets
    ArchArtefactView_Abstr.view_mapper.update({DiscrArtefactsoortEnum.Metaal.value: 'ArchMetaalView'})


class ArchMuntView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Munt)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Munt.value]]

    list_title = "Munt"
    munt_fieldset = [("Muntvelden", {"columns": [
            {"fields": ["aard_verwerving", "verworven_van", "voorwaarden_verwerving", "ontwerper", "conditie", "inventaris", "kwaliteit", "plaats", "produktiewijze", "randafwerking", "rubriek", "signalement", "vindplaats", "vorm"], "grid":6},        
            {"fields": ["eenheid", "gelegenheid", "jaartal", "voorzijde_tekst", "keerzijde_tekst", "autoriteit", "land", "muntplaats", "muntsoort", "randschrift"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView_Abstr.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = munt_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets
    ArchArtefactView_Abstr.view_mapper.update({DiscrArtefactsoortEnum.Munt.value: 'ArchMuntView'})


class ArchSchelpView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Schelp)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Schelp.value]]

    list_title = "Schelp"
    schelp_fieldset = []
    show_fieldsets = copy.deepcopy(ArchArtefactView_Abstr.show_fieldsets)    
    #show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = schelp_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets
    ArchArtefactView_Abstr.view_mapper.update({DiscrArtefactsoortEnum.Schelp.value: 'ArchSchelpView'})


class ArchSteenlView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Steen)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Steen.value]]

    list_title = "Steen"
    steen_fieldset = [("Steenvelden", {"columns": [
            {"fields": ["decoratie", "decoratie", "kleur", "steengroep", "steensoort", "subsoort"], "grid":6},        
            {"fields": ["diameter", "dikte", "grootste_diameter", "lengte", "past_aan"], "grid":6},        
        ]},     
        )]
    show_fieldsets = copy.deepcopy(ArchArtefactView_Abstr.show_fieldsets)    
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = steen_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets
    ArchArtefactView_Abstr.view_mapper.update({DiscrArtefactsoortEnum.Steen.value: 'ArchSteenlView'})


class ArchTextielView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Textiel)
    base_filters = [['artefactsoort', FilterEqual, DiscrArtefactsoortEnum.Textiel.value]]

    list_title = "Textiel"
    textiel_fieldset = []
    show_fieldsets = copy.deepcopy(ArchArtefactView_Abstr.show_fieldsets)    
    #show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = textiel_fieldset
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")
    edit_fieldsets = show_fieldsets
    ArchArtefactView_Abstr.view_mapper.update({DiscrArtefactsoortEnum.Textiel.value: 'ArchTextielView'})


class ArchDoosView(WSModelView):
    datamodel = WSSQLAInterface(Doos)
    # base_permissions = ['can_add', 'can_show']
    list_columns = ["project", "doosnr", "inhoud", 'stelling', 'vaknr', "aantalArtefacten"]
    search_exclude_columns = ['artefacten']
    base_order = ("doosnr", "asc")
    related_views = [ArchArtefactView_Abstr]
    list_title = "Dozen"
    show_fieldsets = [
        ("Hoofdvelden", {"fields": ["project", "doosnr", "inhoud", "aantalArtefacten"]}),
        ("Locatie", {"fields": ["stelling", "vaknr", "volgletter", "uitgeleend"]}),
        flds_migratie_info]

class ArchStellingView(WSModelView):
    datamodel = WSSQLAInterface(Stelling)
    # base_permissions = ['can_add', 'can_show']
    list_columns = ["stelling", "inhoud"]
    base_order = ("stelling", "asc")
    list_title = "Stellingen"
    related_views = [ArchDoosView]
    show_fieldsets = [
        ("Hoofdvelden", {"fields": ["stelling", "inhoud"]}),
        flds_migratie_info]
    add_fieldsets = show_fieldsets
    edit_fieldsets = show_fieldsets



class ArchVondstView(WSModelView):
    datamodel = WSSQLAInterface(Vondst)
    # base_permissions = ['can_add', 'can_show']
    list_title = "Vondsten"
    list_columns = ["project", "put", 'spoor', 'vondstnr', 'inhoud', 'omstandigheden', 'vullingnr']


    show_fieldsets = [
        ("Projectvelden", {"fields": ["project", "put", "vlaknr", "spoor", "vondstnr"]}),
        ("inhoudvelden", {"fields": ["opmerkingen", "omstandigheden", "segment", "vaknummer"]}),
        ("Datering", {"fields": ["vondstdatering_vanaf", "vondstdatering_tot"]}),
        flds_migratie_info]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets
    related_views = [ArchArtefactView]
    search_exclude_columns = ["artefacten"] 




class ArchVullingView(WSModelView):
    datamodel = WSSQLAInterface(Vulling)
    # base_permissions = ['can_add', 'can_show']
    list_title = "Vullingen"
    list_columns = ["project", "put", 'vlaknr', 'spoor', "vullingnr"]
    show_fieldsets = [
        ("Hoofdvelden", {"fields": list_columns + ["opmerkingen"]}),
        ("Vullingvelden", {"fields": ["bioturbatie", "textuur", "mediaan", "textuurbijmenging", "sublaag", "kleur", "reductie", "gevlekt", "laaginterpretatie", "schelpenresten", "grondsoort"]}),
        ("Muurvelden", {"fields": ["lengte_baksteen1", "lengte_baksteen2", "lengte_baksteen3", "hoogte_baksteen1", "hoogte_baksteen2", "hoogte_baksteen3", "breedte_baksteen1", "breedte_baksteen2", "breedte_baksteen3"]}),
        flds_migratie_info
    ]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets

class ArchSpoorView(WSModelView):
    datamodel = WSSQLAInterface(Spoor)
    related_views = [ArchVullingView, ArchVondstView]
    list_columns = ["project", "put", "vlaknr", "spoornr", 'beschrijving']
    list_title = "Sporen"
    show_fieldsets = [
        ("Hoofdvelden", {"fields": ["project", "put", "vlaknr", "spoornr"]}),
        ("Spoorvelden", {"fields": ["aard", "beschrijving", "vorm", "richting", "gecoupeerd", "coupnrs", "afgewerkt"]}),
        ("Stenen", {"fields": ["steenformaat", "metselverband"]}),
        ("Maten", {"fields": ["hoogte_bovenkant", "breedte_bovenkant", "lengte_bovenkant", "hoogte_onderkant", "breedte_onderkant", "diepte"]}),
        ("Andere sporen", {"fields": ["jonger_dan", "ouder_dan", "sporen_zelfde_periode"]}),
        ("Datering", {"fields": ["spoordatering_vanaf", "spoordatering_tot"]}),
        flds_migratie_info
    ]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets




class ArchVlakView(WSModelView):
    datamodel = WSSQLAInterface(Vlak)
    # base_permissions = ['can_add', 'can_show']
    related_views = [ArchSpoorView, ArchVondstView, ArchArtefactView]
    list_title = "Vlakken"
    list_columns = ["project", "put", 'vlaknr', 'beschrijving']
    show_fieldsets = [
        ("Hoofdvelden", {"fields": list_columns}),
        ("Vlakvelden", {"fields": ["datum_aanleg", "vlaktype"]}),
        flds_migratie_info
    ]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets

class ArchPutView(WSModelView):
    datamodel = WSSQLAInterface(Put)
    # base_permissions = ['can_add', 'can_show']
    related_views = [ArchVlakView, ArchSpoorView, ArchVondstView, ArchArtefactView]
    list_title = "Putten"
    list_columns = ["project", "putnr", 'beschrijving']
    show_fieldsets = [
        ("Hoofdvelden", {"fields": ["project", "putnr", "beschrijving"]}),
        ("Putvelden", {"fields": ["beschrijving", "aangelegd", "datum_ingevoerd", "datum_gewijzigd"]}),
        flds_migratie_info
    ]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets
    search_exclude_columns = ["artefacten", "vondsten"] 


class ArchMonster_BotanieView(WSModelView):
    datamodel = WSSQLAInterface(Monster_Botanie)
    # base_permissions = ['can_add', 'can_show']
    list_title = "Botaniedeterminaties Monsters"
    list_columns = ["aantal", 'deel', 'staat', 'monster']

    show_fieldsets = [
        ("Projectvelden", {"fields": ["monster"]}),
        ("Inhoudvelden", {"fields": ["aantal", "deel", "staat"]}),
        flds_migratie_info]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets


class ArchMonster_SchelpView(WSModelView):
    datamodel = WSSQLAInterface(Monster_Schelp)
    # base_permissions = ['can_add', 'can_show']
    list_title = "Schelpdeterminaties Monsters"
    list_columns = ["aantal", "monster"]

    show_fieldsets = [
        ("Projectvelden", {"fields": ["monster"]}),
        ("Inhoudvelden", {"fields": ["aantal"]}),
        flds_migratie_info]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets



class ArchMonsterView(WSModelView):
    datamodel = WSSQLAInterface(Monster)
    # base_permissions = ['can_add', 'can_show']
    list_title = "Monsters"
    list_columns = ["project", "put", 'vondst', 'opmerkingen', 'karakterisering', 'omstandigheden']

    show_fieldsets = [
        ("Projectvelden", {"fields": ["project", "put", "vondst"]}),
        ("Inhoudvelden", {"fields": ["gezeefd_volume", "zeefmaat"]}),
        ("Datering", {"fields": ['opmerkingen', 'karakterisering', 'omstandigheden']}),
        flds_migratie_info]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets
    related_views = [ArchMonster_BotanieView, ArchMonster_SchelpView]
    search_exclude_columns = ["artefacten"] 



class ArchProjectView(WSGeoModelView):
    datamodel = WSGeoSQLAInterface(Project)
    # base_permissions = ['can_add', 'can_show']
    list_columns = ["projectcd", "projectnaam", "jaar", "aantal_artefacten"]
    #related_views = [ArchPutView, ArchVondstView, ArchArtefactView]
    base_order = ("projectcd", "asc")
    list_title = "Projecten"
    related_views = [ArchArtefactView, ArchDoosView, ArchPutView, ArchSpoorView, ArchVondstView, ArchMonsterView, ArchOpgravingFotoView, ArchVelddocumentView, ArchObjectFotoView, ArchOverigeAfbeeldingenView]
    search_exclude_columns = ["location", "artefacten", "fotos"] 

    show_fieldsets = [
        ("Projectvelden", {"fields": ["projectcd", "projectnaam", "jaar", "toponiem", "trefwoorden", "location"]}),
        flds_migratie_info
    ]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets


class MasterView(MultipleView):
    #datamodel = WSSQLAInterface(Artefact)
    views = [ArchArtefactView]





db.create_all()

appbuilder.add_view(ArchProjectView,"Projecten",icon="fa-dashboard",category="Projecten")
appbuilder.add_view(ArchPutView,"Putten",icon="fa-dashboard",category="Projecten")
appbuilder.add_view(ArchVlakView,"Vlakken",icon="fa-dashboard",category="Projecten")
appbuilder.add_view(ArchVondstView,"Vondsten",icon="fa-dashboard",category="Projecten")
appbuilder.add_view(ArchSpoorView,"Sporen",icon="fa-dashboard",category="Projecten")
appbuilder.add_view(ArchVullingView,"Vullingen",icon="fa-dashboard",category="Projecten")
appbuilder.add_view(ArchMonsterView,"Monsters",icon="fa-dashboard",category="Projecten")
appbuilder.add_view(ArchMonster_BotanieView,"Botaniedeterminaties Monsters",icon="fa-dashboard",category="Projecten")
appbuilder.add_view(ArchMonster_SchelpView,"Schelpdeterminaties Monsters",icon="fa-dashboard",category="Projecten")
 
#### Artefacten
appbuilder.add_view(ArchArtefactView,"Alle Artefacten",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchArtefactMetFotoView,"Alle Artefacten met foto",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchAardewerkView,"Aardewerk",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchBouwaardewerkView,"Bouwaardewerk",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchKleipijpView,"Kleipijp",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchLeerView,"Leer",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchDierlijk_BotView,"Dierlijk Bot",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchMenselijk_BotView,"Menselijk Bot",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchMetaalView,"Metaal",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchMuntView,"Munt",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchSchelpView,"Schelp",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchSteenlView,"Steen",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchTextielView,"Textiel",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchGlasView,"Glas",icon="fa-dashboard",category="Artefacten")
appbuilder.add_view(ArchHoutView,"Hout",icon="fa-dashboard",category="Artefacten")


#### Depot
appbuilder.add_view(ArchDoosView, "Dozen", icon="fa-dashboard",category="Depot",)
appbuilder.add_view(ArchStellingView,"Stellingen",icon="fa-dashboard",category="Depot",)


#### Media
appbuilder.add_view(ArchFotoView,"Alle Foto's",icon="fa-dashboard",category="Media",)
appbuilder.add_view(ArchObjectFotoView,"Artefactfoto's",icon="fa-dashboard",category="Media")
appbuilder.add_view(ArchOpgravingFotoView,"Opgravingsfoto's",icon="fa-dashboard",category="Media")
appbuilder.add_view(ArchVelddocumentView,"Velddocumenten",icon="fa-dashboard",category="Media")
appbuilder.add_view(ArchOverigeAfbeeldingenView,"Overige Afbeeldingen",icon="fa-dashboard",category="Media")
appbuilder.add_view(MasterView,"Mappen Foto's",icon="fa-dashboard",category="Media")

appbuilder.add_view(ArtefactChartView,"Telling Artefacten",icon="fa-dashboard",category="Statistieken")
appbuilder.add_view(ArtefactLineChartView,"Datering Artefacten",icon="fa-dashboard",category="Statistieken")
