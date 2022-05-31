from locust import HttpUser, task, between
from pyquery import PyQuery
import re

class QuickstartUser(HttpUser):
    host = "http://localhost:5000"
    # Wait between 5 and 9 seconds per request per user
    wait_time = between(5, 9)
    

    def on_start(self):
        response = self.client.get("/login")
        csrftoken = self.csrftoken = re.search(' name="csrf_token" .* value="(.+?)"', response.text).group(1)
        print("my token is:", csrftoken)    
        self.client.post("/login",
                         {"username": "brienen@e-space.nl", "password": "gsmb10ns", "csrf_token" : csrftoken})

    @task(1)
    def index_page(self):
        # Request /dashboard on your Host
        self.client.get("/")

    @task(1)
    def listprojecten(self):
        # Request /dashboard on your Host
        self.client.get("/archprojectview/list/")        

    @task(1)
    def listfotos(self):
        # Request /dashboard on your Host
        self.client.get("/archartefactfotoview/list/")        

    @task(1)
    def listaardewerk(self):
        # Request /dashboard on your Host
        self.client.get("/archaardewerkview/list/")                