from contiguity import Contiguity

API_KEY = "contiguity_sk_3ac80c1eb8ed3daca87b7b5559befaa80bbc400b6fcef8944d81695a8ef19789"

c = Contiguity(token=API_KEY)
r = c.client.post("/send/text", json={"to": "+18103368755", "message": "raw test"})
print("STATUS:", r.status_code)
print("BODY:", r.text)