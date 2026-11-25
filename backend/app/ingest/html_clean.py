"""Strip site chrome from saved web pages before Docling parses them.

Every lpu.in page carries the same menus, pop-up modals (admissions counselling,
call-back forms, rankings, reserved seats) and footer. Left in, they would be
indexed once per page and crowd out the policy text in search results.
"""

from bs4 import BeautifulSoup

# Elements that never hold policy text.
CHROME_TAGS = [
    "script",
    "style",
    "noscript",
    "template",
    "iframe",
    "svg",
    "form",
    "button",
    "header",
    "nav",
    "footer",
    "aside",
]
# Bootstrap pop-ups and other dialogs, hidden until a visitor clicks something.
CHROME_SELECTORS = [".modal", "[role=dialog]", ".offcanvas", ".breadcrumb"]


def clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup.find_all(CHROME_TAGS):
        element.decompose()
    for element in soup.select(", ".join(CHROME_SELECTORS)):
        element.decompose()
    return str(soup)
