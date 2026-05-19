"""
Integration test: POST /chat and verify a flight query returns a 200 response.
Requires the FastAPI server to be running at http://localhost:8000.
"""

import requests


def test_chat_flight_query():
    url = "http://localhost:8000/chat"
    payload = {"query": "get flights from Hyderabad to Mumbai?"}
    response = requests.post(url, json=payload)
    assert response.status_code == 200, f"Unexpected status: {response.status_code} — {response.text}"
    data = response.json()
    assert "answer" in data, f"Response missing 'answer' key: {data}"
    print("Response from /chat endpoint:", data)


if __name__ == "__main__":
    test_chat_flight_query()
