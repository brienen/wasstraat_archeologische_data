import copy

from flask_appbuilder import GroupByChartView, MultipleView, AppBuilder, BaseView, expose, has_access
from flask_appbuilder.models.group import aggregate_count
from flask_appbuilder.models.sqla.filters import FilterEqual, FilterGreater, FilterStartsWith
from flask_appbuilder.fields import AJAXSelectField, QuerySelectField
from flask_appbuilder.fieldwidgets import Select2ManyWidget, Select2Widget
from flask_appbuilder import ModelView
from wtforms import StringField

from app import db, appbuilder
from models import Conserveringsproject, Bestand, Tekening, Rapportage , Aardewerk, Stelling, Doos, Artefact, Spoor, Project,Put, Vondst, Vlak, DiscrArtefactsoortEnum, Dierlijk_Bot, Glas, Hout, Bouwaardewerk, Kleipijp, Leer, Menselijk_Bot, Metaal, Munt, Schelp, Steen, Textiel, Vulling, Opgravingsfoto, Objectfoto, Veldtekening, Overige_foto, Monster, Monster_Botanie, Monster_Schelp, Objecttekening, Overige_tekening, ABR, Partij, Bruikleen
from widgets import MediaListWidget
from baseviews import WSModelView, WSGeoModelView, fieldDefinitionFactory, Select2Many400Widget, WSModelViewMixin
from interface import WSSQLAInterface, WSGeoSQLAInterface
from filters import HierarchicalABRFilter, FilterBestandIN, FulltextFilter
from validators import ABRCompare_Artefactsoort, ABRCompare_SUBArtefactsoort

import foto_util as foto_util
import util
import shared.const as const

from flask_appbuilder.actions import action
from flask import redirect, request, url_for
import flask_appbuilder.hooks as hooks
from wtforms import widgets
import wtforms.validators as validators


import logging



flds_migratie_info = ("Migratie-informatie", {"fields": ["soort","brondata","uuid"],"expanded": False})
abr_materiaalfilter = ['uri', HierarchicalABRFilter, const.ABR_URI_MATERIALEN]
abr_artefactsoortfilter = ['uri', HierarchicalABRFilter, const.ABR_URI_ARTEFACTEN]
abr_deventervormcodes = ['uri', HierarchicalABRFilter, const.ABR_URI_DEVENTERVORMCODES] 
abr_deventerbakselcodes = ['uri', HierarchicalABRFilter, const.ABR_URI_DEVENTERBAKSELCODES] 

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




class ArchBruikleenView(WSModelView):
    datamodel = WSSQLAInterface(Bruikleen)
    list_columns = ["project", "artefact", "partij", "datum_uitgeleend", 'datum_retour']
    list_title="Bruiklenen"
    search_exclude_columns = ['artefact']

    show_fieldsets = [
        ("Bruikleenvelden", {"fields": ["project", "artefact", "partij", "datum_uitgeleend", 'datum_retour']}),
        flds_migratie_info
    ]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets
    add_form_extra_fields = {
        "artefact": fieldDefinitionFactory('artefact', datamodel),
        }
    edit_form_extra_fields = add_form_extra_fields
    
    @hooks.before_request(only=["add", "edit"])
    def Request_Handler(self):
    #    '''
    #    Request mappert that makes sure the detail view and update view with all details of the inherited class are shown. 
    #    Necessary for inheritance.
    #    '''
        if '_flt_0_artefact' in request.args.keys():
            artefactid = int(request.args['_flt_0_artefact'])
            artf = db.session.query(Artefact).filter(Artefact.primary_key == artefactid).one()

            self.add_form_extra_fields['artefact'].kwargs['widget'].endpoint = f"/api/v1/artefacten?q=(artefactid:{artefactid})"
            self.add_form_extra_fields['project'].kwargs['widget'].endpoint = f"/api/v1/projecten?q=(projectid:{artf.projectID})"
            self.edit_form_extra_fields = self.add_form_extra_fields
        else:
            self.add_form_extra_fields['artefact'].kwargs['widget'].endpoint = "/api/v1/artefacten?q=(projectid:{{ID}})"
            self.add_form_extra_fields['project'].kwargs['widget'].endpoint = "/api/v1/projecten"
            self.edit_form_extra_fields = self.add_form_extra_fields

        return None

    
class ArchPartijView(WSModelView):
    datamodel = WSSQLAInterface(Partij)
    list_columns = ["naam", "adres", "contactpersoon", 'email', 'telefoon']
    list_title="Partijen (Bruiklenen/Conserveringsprojecten)"

    show_fieldsets = [
        ("Partijvelden", {"fields": ["naam", "adres", "contactpersoon", 'email', 'telefoon']}),
        flds_migratie_info
    ]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets
    related_views = [ArchBruikleenView]
    
    validators_columns = {
        'email':[validators.Email(message='Voer een geldig emailadres in.')],
        'telefoon':[validators.Regexp(r'^[\+\(\s.\-\/\d\)]{5,30}$', message='Voer een geldig telefoonnummer in.')]
    }



### Bestanden 
from models import bestand_tupels
lst_all_bestanden = [b for b in bestand_tupels] 
lst_opgravingsfoto = [const.FOTO_OPGRAVINGSFOTO]
lst_objectfoto = [const.FOTO_OBJECTFOTO]
lst_veldtekening = [const.TEK_VELDTEKENING, const.TEK_OVERZICHTSTEKENING]
lst_archrapportage = [const.RAPP_ARCHEOLOGISCHE_RAPPORTAGE, const.RAPP_ARCHEOLOGISCHE_NOTITIE]
lst_overigerapportage = [const.RAPP_CONSERVERINGSRAPPORT, const.RAPP_OVERIGE_RAPPORTAGE]
lst_objecttekening = [const.TEK_OBJECTTEKENING, const.TEK_OBJECTTEKENING_PUBL]
lst_overigetekeningen = [const.TEKENING,
    const.TEK_BOUWTEKENING, 
    const.TEK_UITWERKINGSTEKENING,
    const.TEK_OVERIGE, 
    const.TEK_VELDTEKENING_PUBL]
lst_all_getoond = lst_opgravingsfoto + lst_objectfoto + lst_veldtekening + lst_archrapportage + lst_overigerapportage + lst_objecttekening + lst_overigetekeningen
lst_overige = list(set(lst_all_bestanden) - set(lst_all_getoond))


class ArchBestandView(WSModelView):
    datamodel = WSSQLAInterface(Bestand)
    list_widget = MediaListWidget
    list_title = "Bestanden"
    list_columns = ["fileName", 'koppeling', 'show_bestand_thumbnail']
    show_columns = ["project", "fototype", "fileName", 'directory', 'koppeling', 'show_bestand']
    add_template = 'widgets/add_photo.html'
    show_fieldsets = [
        ("Projectvelden", {"columns": [
            {"fields": ["project", "bestandsoort"], "grid":6},        
            {"fields": ["fileName", "directory", "fileType", 'mime_type'], "grid":6},        
        ]}),        
        ("Afbeelding", {"fields": ["show_bestand"], "grid":12, "fulldisplay": True}),
        flds_migratie_info]
    base_order = ('fileName','asc')
    main_search_cols = ["fileName", 'project', 'projectcd', 'directory']
    search_exclude_columns = ['imageID', 'imageMiddleID', 'imageThumbID']


    @action("5linkskantelen", "Kantelen Linksom", "Geselecteerde foto's linksom kantelen?", "fa-rocket")
    def linkskantelen(self, items):
        if isinstance(items, list):
            for foto in items:
                foto = foto_util.rotateBestand(foto, 90)
                self.datamodel.edit(foto, raise_exception=True)

            self.update_redirect()
        else:
            foto = foto_util.rotateBestand(items, 90)
            self.datamodel.edit(foto)
        return redirect(self.get_redirect())

    @action("6rechtskantelen", "Kantelen Rechtsom", "Geselecteerde foto's rechtsom kantelen?", "fa-rocket")
    def rechtskantelen(self, items):
        if isinstance(items, list):
            for foto in items:
                foto = foto_util.rotateBestand(foto, -90)
                self.datamodel.edit(foto, raise_exception=True)

            self.update_redirect()
        else:
            foto = foto_util.rotateBestand(items, -90)
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

        bestand = db.session.query(Bestand).get(int(lst_path[2]))
        expected_route = self.view_mapper.get(bestand.bestandsoort)

        if expected_route and str(expected_route).lower() != lst_path[0]:
            return redirect(url_for(f'{expected_route}.{lst_path[1]}', pk=str(lst_path[2])))
        else:
            return None


class ArchOpgravingFotoView(ArchBestandView):
    datamodel = WSSQLAInterface(Opgravingsfoto)
    base_filters = [['bestandsoort', FilterBestandIN, [lst_opgravingsfoto]]]
    list_title = "Opgravingsfoto's"
    for typ in lst_opgravingsfoto:
        ArchBestandView.view_mapper.update({typ: 'ArchOpgravingFotoView'})

class ArchObjectFotoView(ArchBestandView):
    datamodel = WSSQLAInterface(Objectfoto)
    base_filters = [['bestandsoort', FilterBestandIN, [lst_objectfoto]]]
    list_title = "Objectfoto's"
    search_exclude_columns = ['artefact'] + ['imageID', 'imageMiddleID', 'imageThumbID']
    main_search_cols = ["fileName", 'directory', 'project', 'projectcd', 'putnr', 'vondstnr', 'subnr']
    show_columns = ["project", "fototype", 'omschrijving', 'materiaal', 'richting', 'datum', "vondstnr", "subnr", "fotonr", "artefact", "fileName", 'directory', 'show_bestand']
    show_fieldsets = [
        ("Projectvelden", {"columns": [
            {"fields": ["project", "bestandsoort", 'omschrijving', 'materiaal', 'richting', 'datum', 'putnr', "vondstnr", "subnr", "fotonr", "artefact"], "grid":6},        
            {"fields": ["fileName", "directory", "fileType", 'mime_type'], "grid":6},        
        ]}),        
        ("Foto", {"fields": ["show_bestand"], "grid":12, "fulldisplay": True}),
        flds_migratie_info]
    for typ in lst_objectfoto:
        ArchBestandView.view_mapper.update({typ: 'ArchObjectFotoView'})
    #edit_fieldsets = show_fieldsets
    #add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "bestandsoort")


class ArchVeldtekeningView(ArchBestandView):
    datamodel = WSSQLAInterface(Tekening)
    base_filters = [['bestandsoort', FilterBestandIN, [lst_veldtekening]]]
    list_title = "Veldtekeningen"
    for typ in lst_overige:
        ArchBestandView.view_mapper.update({typ: 'ArchVeldtekeningView'})




class ArchRapportageView(ArchBestandView):
    datamodel = WSSQLAInterface(Rapportage)
    base_filters = [['bestandsoort', FilterBestandIN, [lst_archrapportage]]]
    list_title = "Archeologische Notities en Rapportages"
    show_columns = ["project", "titel", "rapporttype", "type_onderzoek"]
    show_fieldsets = [
        ("Metadata rapport", {"columns": [
            {"fields": ["project", "titel", "rapporttype", 'type_onderzoek', 'periode_uitvoering', 'jaar_uitgave', 'auteur', "definitief", "rob", "kb", "archief", "ciscode"], "grid":6},        
            {"fields": ["fileName", "directory", "fileType", 'mime_type'], "grid":6},        
        ]}),        
        ("Rapport", {"fields": ["show_bestand"], "grid":12, "fulldisplay": True}),
        flds_migratie_info]
    for typ in lst_archrapportage:
        ArchBestandView.view_mapper.update({typ: 'ArchRapportageView'})

class ArchOverigeRapportageView(ArchBestandView):
    datamodel = WSSQLAInterface(Rapportage)
    base_filters = [['bestandsoort', FilterBestandIN, [lst_overigerapportage]]]
    list_title = "Overige Rapportages"



# Fields for tekening
tekeningvelden = ("Tekeningvelden", {"columns": [
            {"fields": ["volgnr", "datum", "soort"], "grid":6},        
            {"fields": ["materiaal", "omschrijving", "coupe", 'details', 'microfilm', 'periode', 'profiel','schaal'], "grid":6},        
        ]})        

class ArchObjecttekeningenView(ArchBestandView):
    datamodel = WSSQLAInterface(Objecttekening)
    base_filters = [['bestandsoort', FilterBestandIN, [lst_objecttekening]]]
    list_title = "Objecttekeningen"
    show_fieldsets = ArchBestandView.show_fieldsets.copy()
    show_fieldsets[1] = ('Tekening', show_fieldsets[1][1])
    show_fieldsets.insert(1, tekeningvelden)
    for typ in lst_objecttekening:
        ArchBestandView.view_mapper.update({typ: 'ArchObjecttekeningenView'})

class ArchOverigetekeningenView(ArchBestandView):
    datamodel = WSSQLAInterface(Tekening)
    base_filters = [['bestandsoort', FilterBestandIN, [lst_overigetekeningen]]]
    list_title = "Overige tekeningen"
    for typ in lst_overigetekeningen:
        ArchBestandView.view_mapper.update({typ: 'ArchOverigetekeningenView'})

class ArchOverigebestandenView(ArchBestandView):
    datamodel = WSSQLAInterface(Bestand)
    base_filters = [['bestandsoort', FilterBestandIN, [lst_overige]]]
    list_title = "Alle overige bestanden"
    for typ in lst_overige:
        ArchBestandView.view_mapper.update({typ: 'ArchOverigebestandenView'})



class ArchArtefactView_Abstr(WSModelView):
    datamodel = WSSQLAInterface(Artefact)

    def validate_abrmateriaal():
        message = 'Het klopt niet...'

        def _validate_abrmateriaal(form, field):
            if form.artefactsoort.data == 'Aardewerk':
                raise ValidationError("say somgthing")

        return _validate_abrmateriaal


    # base_permissions = ['can_add', 'can_show']
    artf_fieldset = None
    discrartefactsoort = None
    
    list_columns = ["artefactsoort", 'typevoorwerp', "datering", "subnr", "vondst", 'project','aantal_fotos']
    #list_widget = ListThumbnail
    label_columns = WSModelViewMixin.label_columns.update({'abr_materiaal':'Materiaalsoort hoofdmateriaal (ABR)', 'abr_submateriaal':'Sub-materiaalsoort (ABR)', 'abr_extras':'Materiaalsoort overige materialen (ABR)'})
    list_title = "Artefacten"
    related_views = [ArchObjectFotoView, ArchBruikleenView]
    search_exclude_columns = ['fotos', 'doos', 'vondst']
    show_fieldsets = [
        ("Projectvelden", {"columns": [
            {"fields": ["project", "vondst", "subnr", "aantal", "artefactsoort", "abr_materiaal", "abr_submateriaal", "abr_extras", "typevoorwerp", "typecd", "functievoorwerp", "versiering", "beschrijving", "opmerkingen", "doos", "conserveringsprojecten"], "grid":6},        
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
    edit_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "fotos")
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "artefactsoort")

    add_form_extra_fields = {
        "abr_materiaal": fieldDefinitionFactory('abr_materiaal', datamodel, validators=[ABRCompare_Artefactsoort('artefactsoort', message='Verkeerde waarde: ABR-materiaalsoort moet passen bij artefactsoort')]),
        "abr_submateriaal": fieldDefinitionFactory('abr_submateriaal', datamodel) #, validators=[ABRCompare_SUBArtefactsoort('artefactsoort', message='Verkeerde waarde: ABR-submateriaalsoort moet passen bij artefactsoort')]),
        }
    edit_form_extra_fields = add_form_extra_fields
    search_form_query_rel_fields = {'abr_extras': [abr_materiaalfilter]}
    add_form_query_rel_fields = search_form_query_rel_fields
    edit_form_query_rel_fields = search_form_query_rel_fields



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


    def _init_properties(self):
        """
            Init Properties. 
        """
        if self.discrartefactsoort:
            if self.base_filters:
                self.base_filters.append(0, ['artefactsoort', FilterEqual, self.discrartefactsoort])  
            else:
                self.base_filters = [['artefactsoort', FilterEqual, self.discrartefactsoort]] 
            ArchArtefactView_Abstr.view_mapper.update({self.discrartefactsoort: self.__class__.__name__})
            
        self.show_fieldsets = copy.deepcopy(ArchArtefactView_Abstr.show_fieldsets)   
        if self.artf_fieldset:
            self.show_fieldsets[len(self.show_fieldsets)-1:len(self.show_fieldsets)-1] = self.artf_fieldset

        #Remove fotos and give full width withou photo part
        self.edit_fieldsets = util.removeFieldFromFieldset(self.show_fieldsets, "fotos")
        projs = self.edit_fieldsets.pop(0)
        self.edit_fieldsets.insert(0, (projs[0], projs[1]['columns'][0])) 
        self.add_fieldsets = util.removeFieldFromFieldset(self.edit_fieldsets, "artefactsoort")
        self.add_form_extra_fields = copy.copy(ArchArtefactView_Abstr.add_form_extra_fields)    

        self.label_columns = {const.FULLTEXT_SEARCH_FIELD:'Zoeken in alle velden', 
            const.FULLTEXT_SCORE_FIELD:'Score Fulltext', 
            const.FULLTEXT_HIGHLIGHT_FIELD:'Highlight Fulltext', 
            'abr_materiaal':'Materiaalsoort hoofdmateriaal (ABR)', 
            'abr_submateriaal':'Sub-materiaalsoort (ABR)', 
            'abr_extras':'Materiaalsoort overige materialen (ABR)'}


        super(ArchArtefactView_Abstr, self)._init_properties()
       

class ArchArtefactView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Artefact)

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
    discrartefactsoort = DiscrArtefactsoortEnum.Aardewerk.value

    list_title = "Aardewerk"
    #related_views = [ArchObjectFotoView]
    artf_fieldset = [("Aardewerkvelden", {"columns": [
            {"fields": ["baksel", "bakseltype", "categorie", "decoratie", "glazuur", "kleur", "oor", "productiewijze"], "grid":6},        
            {"fields": ["bodem", "diameter", "grootste_diameter", "max_diameter", "rand", "rand_bodem", "rand_diameter", "vorm"], "grid":6},        
        ]},     
        )]

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
    discrartefactsoort = DiscrArtefactsoortEnum.Dierlijk_Bot.value

    list_title = "Dierlijk Bot"
    artf_fieldset = [("Botvelden", {"columns": [
            {"fields": ["diersoort", "bewerkingssporen", "brandsporen", "knaagsporen", "graf", "leeftijd", "pathologie", "symmetrie", "vergroeiing", "oriëntatie"], "grid":6},        
            {"fields": ["lengte", "maat1", "maat2", "maat3", "maat4", "skeletdeel", "slijtage", "slijtage_onderkaaks_DP4", "slijtage_onderkaaks_M1", "slijtage_onderkaaks_M2", "slijtage_onderkaaks_M3"], "grid":6},        
        ]},     
        )]




class ArchGlasView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Glas)
    discrartefactsoort = DiscrArtefactsoortEnum.Glas.value

    list_title = "Glas"
    artf_fieldset = [("Glasvelden", {"columns": [
            {"fields": ["decoratie", "glassoort", "kleur", "vorm_bodem_voet", "vorm_versiering_cuppa", "vorm_versiering_oor_stam"], "grid":6},        
            {"fields": ["diameter_bodem", "diameter_rand", "grootste", "hoogte", "percentage_rand"], "grid":6},        
        ]},     
        )]


class ArchHoutView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Hout)
    discrartefactsoort = DiscrArtefactsoortEnum.Hout.value

    list_title = "Hout"
    artf_fieldset = [("Houtvelden", {"columns": [
            {"fields": ["bewerkingssporen", "decoratie", "determinatieniveau", "gebruikssporen", "houtsoort", "houtsoortcd"], "grid":6},        
            {"fields": ["C14_datering", "dendrodatering", "jaarring_bast_spint", "puntlengte", "puntvorm", "stamcode"], "grid":6},        
        ]},     
        )]


class ArchBouwaardewerkView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Bouwaardewerk)
    discrartefactsoort = DiscrArtefactsoortEnum.Bouwaardewerk.value

    list_title = "Bouwaardewerk"
    artf_fieldset = [("Bouwaardewerkvelden", {"columns": [
            {"fields": ["baksel", "brandsporen", "gedraaid", "glazuur", "handgevormd", "kleur", "magering", "maker", "oor_steel", "productiewijze", "vorm"], "grid":6},        
            {"fields": ["bodem", "diameter_bodem", "grootste_diameter", "hoogte", "oppervlakte", "past_aan", "randdiameter", "randindex", "randpercentage", "subbaksel", "type_rand", "wanddikte"], "grid":6},        
        ]},     
        )]


class ArchKleipijpView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Kleipijp)
    discrartefactsoort = DiscrArtefactsoortEnum.Kleipijp.value
    list_title = "Kleipijp"



class ArchLeerView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Leer)
    discrartefactsoort = DiscrArtefactsoortEnum.Leer.value

    list_title = "Leer"
    artf_fieldset = [("Leervelden", {"columns": [
            {"fields": ["bewerkingssporen", "bewerking", "bovenleer", "decoratie", "kwaliteit", "leersoort", "toestand"], "grid":6},        
            {"fields": ["beschrijving_zool", "past_aan", "sluiting", "soort_sluiting", "type_bovenleer", "verbinding", "zool", "zoolvorm"], "grid":6},        
        ]},     
        )]


class ArchMenselijk_BotView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Menselijk_Bot)
    discrartefactsoort = DiscrArtefactsoortEnum.Menselijk_Bot.value

    list_title = "Menselijk Bot"
    artf_fieldset = [("Velden menselijk bot", {"columns": [
            {"fields": ["doos_delft", "doos_lumc", "linkerarm", "linkerbeen", "rechterarm", "rechterbeen", "schedel", "wervelkolom", "skeletelementen"], "grid":6},        
            {"fields": ["breedte_kist_hoofdeinde", "breedte_kist_voeteinde", "lengte_kist", "kist_waargenomen", "primair_graf", "secundair_graf", "plaats"], "grid":6},        
        ]},     
        )]



class ArchMetaalView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Metaal)
    discrartefactsoort = DiscrArtefactsoortEnum.Metaal.value

    list_title = "Metaal"
    artf_fieldset = [("Metaalvelden", {"columns": [
            {"fields": ["bewerking", "decoratie", "diverse"], "grid":6},        
            {"fields": ["metaalsoort", "oppervlak", "percentage"], "grid":6},        
        ]},     
        )]


class ArchMuntView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Munt)
    discrartefactsoort = DiscrArtefactsoortEnum.Munt.value

    list_title = "Munt"
    artf_fieldset = [("Muntvelden", {"columns": [
            {"fields": ["aard_verwerving", "verworven_van", "voorwaarden_verwerving", "ontwerper", "conditie", "inventaris", "kwaliteit", "plaats", "produktiewijze", "randafwerking", "rubriek", "signalement", "vindplaats", "vorm"], "grid":6},        
            {"fields": ["eenheid", "gelegenheid", "jaartal", "voorzijde_tekst", "keerzijde_tekst", "autoriteit", "land", "muntplaats", "muntsoort", "randschrift"], "grid":6},        
        ]},     
        )]


class ArchSchelpView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Schelp)
    discrartefactsoort = DiscrArtefactsoortEnum.Schelp.value
    list_title = "Schelp"


class ArchSteenlView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Steen)
    discrartefactsoort = DiscrArtefactsoortEnum.Steen.value

    list_title = "Steen"
    artf_fieldset = [("Steenvelden", {"columns": [
            {"fields": ["decoratie", "decoratie", "kleur", "steengroep", "steensoort", "subsoort"], "grid":6},        
            {"fields": ["diameter", "dikte", "grootste_diameter", "lengte", "past_aan"], "grid":6},        
        ]},     
        )]


class ArchTextielView(ArchArtefactView_Abstr):
    datamodel = WSSQLAInterface(Textiel)
    discrartefactsoort = DiscrArtefactsoortEnum.Textiel.value
    list_title = "Textiel"


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
    add_fieldsets = util.removeFieldFromFieldset(show_fieldsets, "aantalArtefacten")
    edit_fieldsets = add_fieldsets


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


class ArchMonster_BotanieView(WSModelView):
    datamodel = WSSQLAInterface(Monster_Botanie)
    # base_permissions = ['can_add', 'can_show']
    list_title = "Botaniedeterminaties Monsters"
    list_columns = ["soort", "aantal", 'deel', 'staat', 'monster']

    show_fieldsets = [
        ("Projectvelden", {"fields": ["monster"]}),
        ("Inhoudvelden", {"fields": ["soort", "aantal", "deel", "staat"]}),
        flds_migratie_info]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets


class ArchMonster_SchelpView(WSModelView):
    datamodel = WSSQLAInterface(Monster_Schelp)
    # base_permissions = ['can_add', 'can_show']
    list_title = "Schelpdeterminaties Monsters"
    list_columns = ["soort", "aantal", "monster"]

    show_fieldsets = [
        ("Projectvelden", {"fields": ["monster"]}),
        ("Inhoudvelden", {"fields": ["soort", "aantal"]}),
        flds_migratie_info]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets


class ArchMonsterView(WSModelView):
    datamodel = WSSQLAInterface(Monster)
    # base_permissions = ['can_add', 'can_show']
    list_title = "Monsters"
    list_columns = ["monstercd", "project", "put", "spoor", 'vondst', 'opmerkingen', 'karakterisering', 'omstandigheden']

    rwaarden_fieldset = [("R-waarden", {"columns": [
            {"fields": ["r_analysewaardig_zo", "r_analysewaardig_bo", "r_concentratie_zo", "r_concentratie_bo"], "grid":6},        
            {"fields": ["r_conservering_zo", "r_conservering_bo", "r_diversiteit_zo", "r_diversiteit_bo"], "grid":6},        
        ]})]
    waardering_fieldset = [("Waardering", {"columns": [
            {"fields": ['B_stengel_mineraaliseerd', 'B_stengel_onverkoold', 'B_stengel_recent', 'B_stengel_verkoold', 'B_wortel_mineraaliseerd', 'B_wortel_onverkoold', 'B_wortel_recent', 'B_wortel_verkoold', 'B_zaden_cultuur_mineraaliseerd', 'B_zaden_cultuur_onverkoold', 'B_zaden_cultuur_recent', 'B_zaden_cultuur_verkoold', 'B_zaden_kaf_mineraaliseerd', 'B_zaden_kaf_onverkoold', 'B_zaden_kaf_recent', 'B_zaden_kaf_verkoold', 'B_zaden_wild_mineraaliseerd','B_zaden_wild_onverkoold', 'B_zaden_wild_recent', 'B_zaden_wild_verkoold'], "grid":4},        
            {"fields": ['C_aardewerk', 'C_antraciet', 'C_bewerkt_hout', 'C_fabsteen', 'C_fosfaat', 'C_glas', 'C_huttenleem', 'C_kleipijp', 'C_lakzegel', 'C_leer', 'C_leisteen', 'C_metaal', 'C_mortel', 'C_natsteen', 'C_ovenslakken', 'C_overig', 'C_steenkool', 'C_textiel', 'C_turf', 'D_C14', 'D_hout', 'D_houtskool', 'D_tak_of_knop', 'D_te_determ', 'S_kokkel', 'S_molzoet_of_land', 'S_mossel', 'S_oester'], "grid":4},        
            {"fields": ['Z_amfibiebot_O', 'Z_amfibiebot_V', 'Z_anders', 'Z_bot_groot_O', 'Z_bot_groot_V', 'Z_bot_klein_O', 'Z_bot_klein_V', 'Z_eierschaal_of_vel_O', 'Z_eierschaal_of_vel_V', 'Z_insekten_O', 'Z_insekten_V', 'Z_visgraat_of_bot_O', 'Z_visgraat_of_bot_V', 'Z_visschub_O', 'Z_visschub_V', 'Z_viswervel_O', 'Z_viswervel_V', 'Z_vliegepop_O', 'Z_vliegepop_V', 'Z_vogelbot_O', 'Z_vogelbot_V', 'Z_watervlo_ei_O', 'Z_watervlo_ei_V', 'Z_wormei_O', 'Z_wormei_V'], "grid":4},        
        ]})]


    show_fieldsets = [
        ("Projectvelden", {"fields": ["monstercd", "project", "put", "spoor", "vondst", "doos"]}),
        ("Inhoudvelden", {"fields": ["gezeefd_volume", "zeefmaat", "restvolume", 'datum_zeven']}),
        ("Beschrijving", {"fields": ['opmerkingen', 'karakterisering', 'omstandigheden', "grondsoort"]}),
        flds_migratie_info]
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = rwaarden_fieldset
    show_fieldsets[len(show_fieldsets)-1:len(show_fieldsets)-1] = waardering_fieldset
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets
    related_views = [ArchMonster_BotanieView, ArchMonster_SchelpView]
    search_exclude_columns = ["artefacten"] 




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
    related_views = [ArchArtefactView, ArchMonsterView]
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
    related_views = [ArchVullingView, ArchVondstView, ArchMonsterView]
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
    # related_views = [ArchSpoorView, ArchVondstView, ArchArtefactView]
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
    related_views = [ArchVlakView, ArchSpoorView, ArchVondstView, ArchArtefactView, ArchMonsterView]
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
    main_search_cols = list_columns





class ArchProjectView(WSGeoModelView):
    datamodel = WSGeoSQLAInterface(Project)
    # base_permissions = ['can_add', 'can_show']
    list_columns = ["projectcd", "projectnaam", "jaar", "aantal_artefacten"]
    #related_views = [ArchPutView, ArchVondstView, ArchArtefactView]
    base_order = ("projectcd", "asc")
    list_title = "Projecten"
    related_views = [ArchArtefactView, ArchDoosView, ArchPutView, ArchSpoorView, ArchVondstView, ArchMonsterView, ArchOpgravingFotoView, ArchVeldtekeningView, ArchObjectFotoView, ArchObjecttekeningenView, ArchOverigetekeningenView, ArchRapportageView, ArchOverigebestandenView]
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




class ABRViewMixin(object):
    datamodel = WSSQLAInterface(ABR)
    list_columns = ["concept", "code", "parent", 'note', 'uri']
    list_title="Materialen uit Archeologisch Basisregister"
    base_filters = [abr_materiaalfilter]
    search_exclude_columns = ['artefacten', 'children', 'uris', 'uuid', 'herkomst', 'brondata']
    search_form_query_rel_fields = {'parent': base_filters}
    add_form_query_rel_fields = {'parent': base_filters}
    edit_form_query_rel_fields = {'parent': base_filters}

    show_fieldsets = [
        ("ABR-velden", {"fields": ["concept", "code", "parent", 'note', 'uri']}),
        flds_migratie_info
    ]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets
    validators_columns = {
        'uri':[validators.URL(message='Voer een geldige URL in.')],
    }


class ABRMaterialenView(ABRViewMixin, WSModelView):
    list_title="Materialen uit Archeologisch Basisregister"
    base_filters = [abr_materiaalfilter]

class ABRArtefactsoortenView(ABRViewMixin, WSModelView):
    list_title="Artefactsoorten uit Archeologisch Basisregister"
    base_filters = [abr_artefactsoortfilter]

class ABRDeventerVormcodesView(ABRViewMixin, WSModelView):
    list_title="Deventer Vormcodes uit Archeologisch Basisregister"
    base_filters = [abr_deventervormcodes]

class ABRDeventerBakselcodesView(ABRViewMixin, WSModelView):
    list_title="Deveter Bakselcodes uit Archeologisch Basisregister"
    base_filters = [abr_deventerbakselcodes]


class ConserveringsprojectView(WSModelView):
    datamodel = WSSQLAInterface(Conserveringsproject)
    list_columns = ["korte_omschrijving", "omschrijving", "begindatum", 'einddatum', 'uitvoerder']
    list_title="Conserveringsprojecten"
    related_views = [ArchArtefactView]
    search_exclude_columns = ['artefacten', 'uuid', 'herkomst', 'brondata']

    show_fieldsets = [
        ("Conserveringsprojectvelden", {"fields": ["korte_omschrijving", "omschrijving", "begindatum", 'einddatum', 'uitvoerder']}),
        flds_migratie_info
    ]
    edit_fieldsets = show_fieldsets
    add_fieldsets = show_fieldsets



db.create_all()

appbuilder.add_view(ABRMaterialenView,"Materialen uit ABR",icon="fa-dashboard",category="Beheer")
appbuilder.add_view(ABRArtefactsoortenView,"Artefactsoorten uit ABR",icon="fa-dashboard",category="Beheer")
appbuilder.add_view(ABRDeventerVormcodesView,"Deventer Vormcodes uit ABR",icon="fa-dashboard",category="Beheer")
appbuilder.add_view(ABRDeventerBakselcodesView,"Deventer Bakselcodes uit ABR",icon="fa-dashboard",category="Beheer")


appbuilder.add_view(ArchProjectView,"Projecten",icon="fa-dashboard",category="Projecten") #ArchTestProjectView
appbuilder.add_view(ArchPutView,"Putten",icon="fa-dashboard",category="Projecten")
appbuilder.add_view(ArchVlakView,"Vlakken",icon="fa-dashboard",category="Projecten")
appbuilder.add_view(ArchVondstView,"Vondsten",icon="fa-dashboard",category="Projecten")
appbuilder.add_view(ArchSpoorView,"Sporen",icon="fa-dashboard",category="Projecten")
appbuilder.add_view(ArchVullingView,"Vullingen",icon="fa-dashboard",category="Projecten")
appbuilder.add_view(ArchMonsterView,"Monsters",icon="fa-dashboard",category="Projecten")
appbuilder.add_view_no_menu(ArchMonster_BotanieView,"Botaniedeterminaties Monsters")
appbuilder.add_view_no_menu(ArchMonster_SchelpView,"Schelpdeterminaties Monsters")
 
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
appbuilder.add_view(ArchBruikleenView,"Bruiklenen",icon="fa-dashboard",category="Depot",)
appbuilder.add_view(ConserveringsprojectView,"Conserveringsprojecten",icon="fa-dashboard",category="Depot",)
appbuilder.add_view(ArchPartijView,"Partijen (Bruiklenen/Conserveringsprojecten)",icon="fa-dashboard",category="Depot",)


#### Media
appbuilder.add_view(ArchBestandView,"Alle Bestanden",icon="fa-dashboard",category="Media",)
appbuilder.add_view(ArchObjectFotoView,"Objectfoto's",icon="fa-dashboard",category="Media")
appbuilder.add_view(ArchOpgravingFotoView,"Opgravingsfoto's",icon="fa-dashboard",category="Media")
appbuilder.add_view(ArchVeldtekeningView,"Veldtekeningen",icon="fa-dashboard",category="Media")
appbuilder.add_view(ArchObjecttekeningenView,"Objecttekeningen",icon="fa-dashboard",category="Media")
appbuilder.add_view(ArchOverigetekeningenView,"Overige Tekeningen",icon="fa-dashboard",category="Media")
appbuilder.add_view(ArchRapportageView,"Archeologische Rapportages en Notities",icon="fa-dashboard",category="Media")
appbuilder.add_view(ArchOverigeRapportageView,"Overige Rapportages",icon="fa-dashboard",category="Media")
appbuilder.add_view(ArchOverigebestandenView,"Alle Overige Bestanden",icon="fa-dashboard",category="Media")
#appbuilder.add_view(MasterView,"Mappen Foto's",icon="fa-dashboard",category="Media")



#appbuilder.add_view(ArtefactChartView,"Telling Artefacten",icon="fa-dashboard",category="Statistieken")
#appbuilder.add_view(ArtefactLineChartView,"Datering Artefacten",icon="fa-dashboard",category="Statistieken")
