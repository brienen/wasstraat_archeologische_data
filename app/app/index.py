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

        start_coords = (52.00667, 4.35556) # Delft
        foliummap = folium.Map(location=start_coords, zoom_start=12)
        #folium.TileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community', name='Esri Terrain').add_to(foliummap)
        #folium.TileLayer('https://mapwarper.net/maps/tile/35760/{z}/{x}/{y}.png', attr='Mapwarp', name='Delft 1652').add_to(foliummap)
        #folium.TileLayer('Stamen Terrain').add_to(foliummap)
        #folium.TileLayer('CartoDB positron').add_to(foliummap)


        feature_group_niet = folium.FeatureGroup(name='Niet Ingelezen Projecten')
        feature_group_ingl = folium.FeatureGroup(name='Ingelezen Projecten')
        dest_db_con = create_engine(config.SQLALCHEMY_DATABASE_URI, isolation_level='AUTOCOMMIT')
        try: 
            Session = sessionmaker(bind=dest_db_con)
            session = Session()

            stmt = (
                # Works directly on resultset
                session.query(Project.primary_key, Project.projectcd, Project.projectnaam, func.st_y(Project.location), func.st_x(Project.location),func.count(Artefact.primary_key))
                    .select_from(Artefact)
                    .join(Artefact.project, full=True)
                    .group_by(Project.primary_key, Project.projectcd, Project.projectnaam, Project.location)
                    .filter(Project.location != None).statement
                )
            # Works directly on resultset
            rs = dest_db_con.execute(stmt)
            [MyIndexView.addMarker(row[0],row[1],row[2],row[3],row[4],row[5], feature_group_niet,feature_group_ingl) for row in rs]

            feature_group_niet.add_to(foliummap)
            feature_group_ingl.add_to(foliummap)
            folium.LayerControl().add_to(foliummap)

            self.foliummap_str = foliummap._repr_html_()
            self.extra_args = {'foliummap':self.foliummap_str}     
        finally:
            session.close()

        return super(MyIndexView, self).render_template(template, **kwargs)
    

