from locust import HttpUser, between, task


class WebsiteUser(HttpUser):
    wait_time = between(1, 5)

    @task
    def view_home(self):
        self.client.get("/")

    @task
    def register(self):
        self.client.post("/api/v1/user/register/", json={
            "username": "shop123",
            "email": "shop@example.com",
            "password": "strongpass123",
            "phone_number": "79991234567",
            "company": "ООО Техника",
            "position": "Менеджер",
            "type": "shop"
        })

    @task
    def login(self):
        self.client.post("/api/v1/user/login/", json={
            "email": "testuser@example.com",
            "password": "password"
        })