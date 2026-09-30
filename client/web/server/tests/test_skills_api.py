from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile


def _skill_zip(path: str = "demo/SKILL.md") -> BytesIO:
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        archive.writestr(path, "---\nname: demo\ndescription: Demo skill\n---\n\nUse demo.\n")
    stream.seek(0)
    return stream


def test_skills_list_reads_database_and_refresh_imports_zip(client):
    response = client.get("/api/settings/skills")
    assert response.status_code == 200
    assert response.json()["items"] == []

    response = client.post(
        "/api/settings/skills/import",
        files={"file": ("demo.zip", _skill_zip(), "application/zip")},
    )
    assert response.status_code == 200
    assert response.json()["added"] == 1
    assert response.json()["items"][0]["name"] == "demo"

    response = client.post("/api/settings/skills/refresh")
    assert response.status_code == 200
    assert response.json()["unchanged"] == 1


def test_skill_import_rejects_path_traversal(client):
    response = client.post(
        "/api/settings/skills/import",
        files={"file": ("bad.zip", _skill_zip("../escape/SKILL.md"), "application/zip")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SKILL_IMPORT_INVALID"
