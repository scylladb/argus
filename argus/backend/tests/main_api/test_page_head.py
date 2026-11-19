from html.parser import HTMLParser

import pytest

PAGES = [("api_client", "/releases"), ("anon_client", "/error/?type=404")]
ICON_STYLES = {"fas", "far"}


class PageTags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_head = False
        self.head_scripts: list[dict] = []
        self.head_links: list[dict] = []
        self.icons: list[dict] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "head":
            self.in_head = True
        elif tag == "script" and self.in_head and "src" in attributes:
            self.head_scripts.append(attributes)
        elif tag == "link" and self.in_head:
            self.head_links.append(attributes)
        elif tag == "i" and ICON_STYLES & set((attributes.get("class") or "").split()):
            self.icons.append(attributes)

    def handle_endtag(self, tag):
        if tag == "head":
            self.in_head = False


def render(request, client_fixture: str, path: str) -> PageTags:
    res = request.getfixturevalue(client_fixture).get(path)
    assert res.status_code == 200, res.text
    tags = PageTags()
    tags.feed(res.text)
    return tags


@pytest.mark.parametrize(("client_fixture", "path"), PAGES)
def test_page_head_loads_no_parser_blocking_script(request, client_fixture, path):
    tags = render(request, client_fixture, path)

    blocking = [
        script["src"] for script in tags.head_scripts
        if script.get("type") != "module" and "defer" not in script and "async" not in script
    ]
    assert tags.head_scripts
    assert blocking == []


@pytest.mark.parametrize(("client_fixture", "path"), PAGES)
def test_page_head_preloads_the_solid_icon_font(request, client_fixture, path):
    tags = render(request, client_fixture, path)

    preloads = [
        link for link in tags.head_links
        if link.get("rel") == "preload" and link.get("href") == "/s/dist/fa-solid-900.woff2"
    ]
    assert len(preloads) == 1
    assert preloads[0].get("as") == "font"
    assert preloads[0].get("type") == "font/woff2"
    assert "crossorigin" in preloads[0]


@pytest.mark.parametrize(("client_fixture", "path"), PAGES)
def test_template_icons_are_hidden_from_assistive_technology(request, client_fixture, path):
    tags = render(request, client_fixture, path)

    exposed = [icon["class"] for icon in tags.icons if icon.get("aria-hidden") != "true"]
    assert tags.icons
    assert exposed == []
