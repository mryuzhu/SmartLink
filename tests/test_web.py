from __future__ import annotations


def test_dashboard_hides_music_actions(client):
    response = client.get("/")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "隐藏音乐动作" not in page
