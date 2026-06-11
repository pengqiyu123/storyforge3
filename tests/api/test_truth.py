from __future__ import annotations


def test_get_latest_truth_returns_data(client):
    resp = client.get("/api/books/truth-api/truth/latest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["chapter_no"] == 2
    assert body["data"]["fact_assertions"] == ["林默进入检测中心。"]
    assert body["data"]["character_updates"] == [{"summary": "林默保持谨慎。"}]


def test_get_latest_truth_returns_null(client, mock_truth_store):
    mock_truth_store.latest = None
    resp = client.get("/api/books/truth-api/truth/latest")
    assert resp.status_code == 200
    assert resp.json()["data"] is None


def test_get_truth_by_chapter_returns_data_and_null(client):
    found = client.get("/api/books/truth-api/truth/1")
    assert found.status_code == 200
    assert found.json()["data"]["fact_assertions"] == ["林默发现存在感异常。"]

    missing = client.get("/api/books/truth-api/truth/99")
    assert missing.status_code == 200
    assert missing.json()["data"] is None


def test_get_truth_history_returns_sorted_data(client):
    resp = client.get("/api/books/truth-api/truth/history")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [item["chapter_no"] for item in data] == [1, 2]
    assert data[1]["fact_assertions"] == ["林默进入检测中心。"]


def test_extract_truth_saves_result_with_previous_truth(client, mock_truth_store, mock_truth_extractor):
    resp = client.post(
        "/api/books/truth-api/truth/extract",
        json={"chapter_no": 3, "text": "林默在检测中心走廊停下。"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["fact_assertions"] == ["第3章 truth 已提取。"]
    assert mock_truth_extractor.last_previous_truth is mock_truth_store.latest
    assert mock_truth_store.saved[0] == "truth-api"
    assert mock_truth_store.saved[1].chapter_no == 3


def test_extract_truth_failure_returns_500(client, mock_truth_extractor):
    mock_truth_extractor.should_fail = True
    resp = client.post(
        "/api/books/truth-api/truth/extract",
        json={"chapter_no": 3, "text": "失败样例"},
    )
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "INTERNAL_ERROR"
