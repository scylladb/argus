def test_issue_page_renders_for_a_key(api_client):
    res = api_client.get("/issues/SCT-1234")

    assert res.status_code == 200, res.text
    assert "/s/dist/issueLinks.bundle.js" in res.text
    assert '"SCT-1234"' in res.text


def test_issue_page_escapes_the_key(api_client):
    res = api_client.get("/issues/%3Cb%3Ex-1")

    assert res.status_code == 200, res.text
    assert "<b>x-1" not in res.text
    assert "\\u003cb\\u003ex-1" in res.text
    assert "&lt;b&gt;x-1" in res.text
