from locust import HttpUser, between, task
import re


class WebsiteUser(HttpUser):
    host = "http://localhost:5000"
    wait_time = between(5, 15)

    def on_start(self):
        """ on_start is called when a Locust start before any task is scheduled """
        self.client.verify = False
        self.get_token()
        response = self.login()
        print(f"Response {response}")

    def on_stop(self):
        """ on_stop is called when the TaskSet is stopping """
        self.logout()

    def get_token(self):
        response = self.client.get("/login")
        # Sample string from response:
        # <input id="csrf_token" name="csrf_token" type="hidden" value="REDACTED">
        self.csrftoken = re.search(' name="csrf_token" .* value="(.+?)"', response.text).group(1)
        print(f"DEBUG: self.csrftoken = {self.csrftoken}")

    def login(self):
        response = self.client.post("/login",
                                    {"username": "brienen@e-space.nl",
                                     "password": "gsmb10ns"
                                     },
                                    headers={"X-CSRFToken": self.csrftoken})
        print(f"DEBUG: login response.status_code = {response.status_code}")

    def logout(self):
        self.client.get("/logout")


    @task
    def index(self):
        self.client.get("/")
        self.client.get("/archprojectview/list/")