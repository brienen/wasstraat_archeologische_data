from models import Project, Artefact
import shared.config as config
#import geopandas

from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, func

from flask_appbuilder import IndexView
import folium
from flask import current_app


from caching import cache

class MyIndexView(IndexView):

    # Works directly on resultset
    @classmethod
    def addMarker(self, pkey, projectcd, projectnaam, location_y, location_x, count, grp_niet, grp_ingl): 
        
        folium.CircleMarker(
            location=[location_y, location_x],
            radius=4 if count == 0 else 8,
            popup=folium.Popup(html=f'<div><b>Projectcode: </b><a href="/archprojectview/show/{pkey}" target="_PARENT">{projectcd}</a><br/><b>Projectnaam: </b>{projectnaam}</div>'),
            color='blue' if count == 0 else 'red',
            fill=True,
            fill_color='#3186cc'
       ).add_to(grp_niet if count ==0 else grp_ingl)    



    foliummap_str = 'Reading map...'
    index_template = 'index.html'
    extra_args = {'foliummap':foliummap_str}     



    @cache.cached()
    def render_template(self, template, **kwargs):
        current_app.logger.info('Rendering template for index page: setting projectinfo...')

        # Standaard: centrum van Nederland; wordt overschreven als er projecten met locatie zijn
        default_coords = (52.15, 5.39)
        foliummap = folium.Map(location=default_coords, zoom_start=8)

        feature_group_niet = folium.FeatureGroup(name='Niet Ingelezen Projecten')
        feature_group_ingl = folium.FeatureGroup(name='Ingelezen Projecten')
        dest_db_con = create_engine(config.SQLALCHEMY_DATABASE_URI, isolation_level='AUTOCOMMIT')
        try:
            Session = sessionmaker(bind=dest_db_con)
            session = Session()

            stmt = (
                session.query(Project.primary_key, Project.projectcd, Project.projectnaam, func.st_y(Project.location), func.st_x(Project.location),func.count(Artefact.primary_key))
                    .select_from(Artefact)
                    .join(Artefact.project, full=True)
                    .group_by(Project.primary_key, Project.projectcd, Project.projectnaam, Project.location)
                    .filter(Project.location != None).statement
                )
            rs = dest_db_con.execute(stmt)

            lats = []
            lons = []
            for row in rs:
                MyIndexView.addMarker(row[0],row[1],row[2],row[3],row[4],row[5], feature_group_niet,feature_group_ingl)
                lats.append(row[3])
                lons.append(row[4])

            feature_group_niet.add_to(foliummap)
            feature_group_ingl.add_to(foliummap)
            folium.LayerControl().add_to(foliummap)

            # Zoom de kaart automatisch naar de bounding box van alle projecten
            if lats and lons:
                foliummap.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

            self.foliummap_str = foliummap._repr_html_()
            self.extra_args = {'foliummap':self.foliummap_str}     
        finally:
            session.close()

        return super(MyIndexView, self).render_template(template, **kwargs)
    

